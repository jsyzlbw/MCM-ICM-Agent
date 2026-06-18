from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.gate_decision import GateDecision, record_gate_decision
from mcm_agent.core.lineage import append_citation_candidate, append_lineage_record
from mcm_agent.core.models import CitationCandidate, DataLineageRecord, RetrievalLogEntry, SourceRecord
from mcm_agent.providers.search import ExtractProvider, SearchProvider
from mcm_agent.utils.json_io import append_jsonl, read_json, write_json


class OfficialDataRepairProvider(Protocol):
    def repair(self, workspace_root: Path, need: dict[str, str]) -> list[dict[str, str]]:
        raise NotImplementedError


class SearchDataAgent:
    def __init__(
        self,
        search_provider: SearchProvider,
        extract_provider: ExtractProvider,
        official_data_provider: OfficialDataRepairProvider | None = None,
    ) -> None:
        self.search_provider = search_provider
        self.extract_provider = extract_provider
        self.official_data_provider = official_data_provider

    def run(self, workspace_root: Path) -> None:
        experiment_plan = workspace_root / "reports" / "experiment_plan.md"
        if not experiment_plan.exists():
            raise FileNotFoundError("missing reports/experiment_plan.md")

        selected_routes = self._selected_routes(workspace_root)
        plan_queries = self._queries_from_plan(experiment_plan.read_text(encoding="utf-8"))
        data_needs = self._route_data_needs(selected_routes)
        feasibility_needs = self._feasibility_data_needs(workspace_root)
        data_needs.extend(feasibility_needs)
        searchable_needs = [
            item
            for item in data_needs
            if item.get("status") not in {"skipped_private_or_unavailable", "covered_by_attachment"}
        ]
        queries = self._dedupe(plan_queries + [item["query"] for item in searchable_needs])
        query_context = self._query_context(searchable_needs)
        write_json(
            workspace_root / "data" / "search_plan.json",
            {
                "selected_routes": selected_routes,
                "queries": queries,
                "data_needs": data_needs,
            },
        )
        source_records: list[SourceRecord] = []
        registry_path = workspace_root / "data" / "source_registry.json"
        log_path = workspace_root / "data" / "retrieval_log.jsonl"

        for query in queries:
            context = query_context.get(query, {})
            results = self.search_provider.search(query, max_results=5)
            append_jsonl(
                log_path,
                RetrievalLogEntry(
                    time=datetime.now(UTC),
                    provider=self.search_provider.__class__.__name__,
                    query=query,
                    top_urls=[result.url for result in results],
                    decision="send_results_to_extractor",
                ).model_dump(mode="json"),
            )

            for index, result in enumerate(results, 1):
                if not result.title or not result.url:
                    continue
                try:
                    page = self.extract_provider.extract(result.url)
                except Exception as exc:  # noqa: BLE001 - one blocked URL must not crash data collection
                    append_jsonl(
                        log_path,
                        RetrievalLogEntry(
                            time=datetime.now(UTC),
                            provider=self.extract_provider.__class__.__name__,
                            url=result.url,
                            decision=f"extraction_failed: {str(exc)[:120]}",
                        ).model_dump(mode="json"),
                    )
                    continue
                extracted_path = workspace_root / "data" / "external" / f"source_{len(source_records)+1:03d}.md"
                extracted_path.parent.mkdir(parents=True, exist_ok=True)
                extracted_path.write_text(page.markdown, encoding="utf-8")
                source_rank = self._rank_source(result.url)
                accessed_at = datetime.now(UTC)
                record = SourceRecord(
                    source_id=f"web_{len(source_records)+1:03d}",
                    title=result.title,
                    url=result.url,
                    accessed_at=accessed_at,
                    license="unknown",
                    provider=self.search_provider.__class__.__name__,
                    source_rank=source_rank,
                    used_for="external data discovery" if source_rank == "official" else "background",
                    citation=result.title,
                    local_path=str(extracted_path.relative_to(workspace_root)),
                    data_need_id=context.get("need_id"),
                    target_dataset=context.get("target_dataset"),
                    source_query=query,
                )
                source_records.append(record)
                append_jsonl(
                    log_path,
                    RetrievalLogEntry(
                        time=datetime.now(UTC),
                        provider=self.extract_provider.__class__.__name__,
                        url=result.url,
                        output=str(extracted_path.relative_to(workspace_root)),
                        decision="accepted" if source_rank == "official" else "accepted_background_only",
                    ).model_dump(mode="json"),
                )
                self._record_provenance(
                    workspace_root,
                    record,
                    accessed_at,
                    query=query,
                )

        existing = read_json(registry_path, [])
        existing.extend(record.model_dump(mode="json") for record in source_records)
        write_json(registry_path, existing)

        notes = ["# External Data Notes", ""]
        for record in source_records:
            notes.append(f"- `{record.source_id}` {record.title}: {record.source_rank}")
        (workspace_root / "data" / "external_data_notes.md").write_text(
            "\n".join(notes) + "\n",
            encoding="utf-8",
        )
        source_issues = self._source_gate_issues(workspace_root, source_records)
        if source_issues and self.official_data_provider is not None:
            source_records.extend(
                self._repair_with_official_apis(workspace_root, source_records)
            )
            existing = read_json(registry_path, [])
            write_json(registry_path, existing + [
                record.model_dump(mode="json")
                for record in source_records
                if record.source_id not in {item.get("source_id") for item in existing}
            ])
            source_issues = self._source_gate_issues(workspace_root, source_records)
        if source_issues:
            self._write_search_repair_report(workspace_root, source_issues, source_records)
        record_gate_decision(
            workspace_root,
            "source_gate.json",
            GateDecision(
                gate_id="source_verifier",
                status="fail" if source_issues else "pass",
                failure_reason="source_unreliable" if source_issues else None,
                repair_stage="search_data" if source_issues else None,
                blocking_findings=source_issues,
            ),
        )
        Coordinator(workspace_root).emit(
            "data.failed" if source_issues else "data.ready",
            source="SearchDataAgent",
        )

    def _record_provenance(
        self,
        workspace_root: Path,
        record: SourceRecord,
        accessed_at: datetime,
        *,
        query: str,
    ) -> None:
        append_citation_candidate(
            workspace_root / "data" / "citation_candidates.json",
            CitationCandidate(
                citation_id=f"cite_{record.source_id}",
                source_id=record.source_id,
                title=record.title,
                url=record.url,
                accessed_at=accessed_at,
                citation_note=f"Retrieved for query: {query}",
            ),
        )
        if record.source_rank not in {"official", "academic", "reputable"}:
            return
        append_lineage_record(
            workspace_root / "data" / "data_lineage.json",
            DataLineageRecord(
                datum_id=f"datum_{record.source_id}",
                name=record.title,
                value="source-level dataset",
                unit="source",
                entity="external_source",
                time_period="unknown",
                source_id=record.source_id,
                source_url=record.url,
                source_title=record.title,
                accessed_at=accessed_at,
                local_path=record.local_path or "",
                extraction_method=self.extract_provider.__class__.__name__,
                confidence=0.7,
                used_in=self._lineage_used_in(record),
            ),
        )

    def _repair_with_official_apis(
        self,
        workspace_root: Path,
        source_records: list[SourceRecord],
    ) -> list[SourceRecord]:
        if self.official_data_provider is None:
            return []
        search_plan = read_json(workspace_root / "data" / "search_plan.json", {})
        data_needs = search_plan.get("data_needs", []) if isinstance(search_plan, dict) else []
        repaired_records = []
        for need in self._uncovered_searchable_needs(data_needs, source_records):
            for payload in self.official_data_provider.repair(workspace_root, need):
                record = self._source_record_from_official_payload(payload, need)
                repaired_records.append(record)
                self._record_provenance(
                    workspace_root,
                    record,
                    record.accessed_at,
                    query=record.source_query or need["query"],
                )
        return repaired_records

    def _source_record_from_official_payload(
        self,
        payload: dict[str, str],
        need: dict[str, str],
    ) -> SourceRecord:
        return SourceRecord(
            source_id=payload["source_id"],
            title=payload["title"],
            url=payload["url"],
            accessed_at=datetime.now(UTC),
            license=payload.get("license", "unknown"),
            provider=payload.get("provider", "official_data_api"),
            source_rank="official",
            used_for="official data repair",
            citation=payload["title"],
            local_path=payload.get("local_path"),
            data_need_id=need["need_id"],
            target_dataset=need["target_dataset"],
            source_query=need["query"],
        )

    def _queries_from_plan(self, plan: str) -> list[str]:
        queries = []
        for line in plan.splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                queries.append(stripped[2:])
        return queries or ["external data for math modeling problem"]

    def _selected_routes(self, workspace_root: Path) -> list[str]:
        text = (workspace_root / "reports" / "model_decision.md").read_text(
            encoding="utf-8"
        ) if (workspace_root / "reports" / "model_decision.md").exists() else ""
        route_ids = [
            "multi_criteria_evaluation",
            "constrained_optimization",
            "forecasting_model",
            "monte_carlo_simulation",
            "network_flow_graph",
            "multi_objective_decision",
        ]
        return [route_id for route_id in route_ids if route_id in text]

    def _route_data_needs(self, selected_routes: list[str]) -> list[dict[str, str]]:
        templates = {
            "multi_criteria_evaluation": [
                (
                    "indicator_table",
                    "official priority indicator dataset for evaluation model",
                ),
                (
                    "normalization_context",
                    "official benchmark indicator definitions for priority scoring",
                ),
            ],
            "constrained_optimization": [
                (
                    "resource_constraints",
                    "official resource allocation constraint data budget capacity",
                ),
                (
                    "policy_limits",
                    "official policy limits for resource allocation constraint",
                ),
            ],
            "forecasting_model": [
                ("historical_observations", "official historical time series data forecast demand"),
            ],
            "monte_carlo_simulation": [
                ("uncertainty_ranges", "official parameter uncertainty ranges scenario analysis"),
            ],
            "network_flow_graph": [
                ("network_edges", "official road network nodes edges capacity data"),
            ],
            "multi_objective_decision": [
                ("objective_weights", "official multi objective decision criteria weights data"),
            ],
        }
        needs = []
        for route_id in selected_routes:
            for need_id, query in templates.get(route_id, []):
                needs.append({"route_id": route_id, "need_id": need_id, "query": query})
        return needs

    def _feasibility_data_needs(self, workspace_root: Path) -> list[dict[str, str]]:
        matrix = read_json(workspace_root / "data" / "data_feasibility_matrix.json", [])
        if not isinstance(matrix, list):
            return []
        needs = []
        for row in matrix:
            if not isinstance(row, dict):
                continue
            target = str(row.get("target_dataset", "")).strip()
            query = str(row.get("query", "")).strip()
            availability = str(row.get("availability", "unknown"))
            if not target:
                continue
            status = "searchable"
            if availability == "private_or_unavailable":
                status = "skipped_private_or_unavailable"
            elif availability == "unknown" and self._has_attachments(workspace_root):
                status = "covered_by_attachment"
            needs.append(
                {
                    "route_id": "data_feasibility",
                    "need_id": str(row.get("need_id", target)),
                    "query": query or f"{target} public dataset official",
                    "target_dataset": target,
                    "availability": availability,
                    "status": status,
                    "source": "data_feasibility_matrix",
                }
            )
        return needs

    def _dedupe(self, values: list[str]) -> list[str]:
        seen = set()
        deduped = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                deduped.append(normalized)
        return deduped

    def _has_attachments(self, workspace_root: Path) -> bool:
        return any((workspace_root / "input" / "attachments").glob("*"))

    def _query_context(self, data_needs: list[dict[str, str]]) -> dict[str, dict[str, str]]:
        context = {}
        for need in data_needs:
            query = need.get("query", "").strip()
            if not query or query in context:
                continue
            context[query] = {
                "need_id": need.get("need_id", ""),
                "target_dataset": need.get("target_dataset", ""),
            }
        return context

    def _lineage_used_in(self, record: SourceRecord) -> list[str]:
        used_in = ["data/source_registry.json"]
        if record.data_need_id or record.target_dataset:
            used_in.append("data/data_feasibility_matrix.json")
        return used_in

    def _rank_source(self, url: str) -> str:
        official_markers = ["data.gov", ".gov", "worldbank.org", "oecd.org", "un.org"]
        if any(marker in url for marker in official_markers):
            return "official"
        return "background_only"

    def _source_gate_issues(
        self,
        workspace_root: Path,
        source_records: list[SourceRecord],
    ) -> list[str]:
        coverage_issues = self._data_need_coverage_issues(workspace_root, source_records)
        if coverage_issues:
            return coverage_issues
        if not source_records:
            if any((workspace_root / "input" / "attachments").glob("*")):
                return []
            return ["No external sources were retrieved."]
        trusted = [
            record
            for record in source_records
            if record.source_rank in {"official", "academic", "reputable"}
        ]
        if not trusted:
            # When the discussion stage locked user-provided assumptions, the team
            # proceeds by stating assumptions for unobtainable data; a lack of
            # trusted web sources must not then block a modeling-only paper.
            direction_lock = read_json(workspace_root / "discussion" / "direction_lock.json", {})
            if (
                isinstance(direction_lock, dict)
                and direction_lock.get("adopted_reframing_strategy") == "user_provided_assumptions"
            ):
                return []
            return ["No official, academic, or reputable source was retrieved."]
        return []

    def _data_need_coverage_issues(
        self,
        workspace_root: Path,
        source_records: list[SourceRecord],
    ) -> list[str]:
        search_plan = read_json(workspace_root / "data" / "search_plan.json", {})
        data_needs = search_plan.get("data_needs", []) if isinstance(search_plan, dict) else []
        if not isinstance(data_needs, list):
            return []
        direction_lock = read_json(workspace_root / "discussion" / "direction_lock.json", {})
        user_assumptions = (
            isinstance(direction_lock, dict)
            and direction_lock.get("adopted_reframing_strategy") == "user_provided_assumptions"
        )
        trusted_need_ids = {
            record.data_need_id
            for record in source_records
            if record.data_need_id
            and record.source_rank in {"official", "academic", "reputable"}
        }
        issues = []
        for need in data_needs:
            if not isinstance(need, dict):
                continue
            if need.get("source") != "data_feasibility_matrix":
                continue
            if need.get("status") == "skipped_private_or_unavailable":
                continue
            if need.get("status") == "covered_by_attachment":
                continue
            # When the discussion stage locked user-provided assumptions for an
            # otherwise-uncovered/unknown data need, the team proceeds by stating
            # assumptions, so that need is exempted (mirrors modeling_quality_gate).
            if user_assumptions:
                availability = need.get("availability")
                if availability in {None, "unknown"} and not need.get("proxy_variables"):
                    continue
            need_id = str(need.get("need_id", "")).strip()
            if not need_id or need_id in trusted_need_ids:
                continue
            target = str(need.get("target_dataset", "unknown dataset"))
            issues.append(
                f"Searchable data need `{need_id}` for `{target}` has no trusted source coverage."
            )
        return issues

    def _write_search_repair_report(
        self,
        workspace_root: Path,
        source_issues: list[str],
        source_records: list[SourceRecord],
    ) -> None:
        search_plan = read_json(workspace_root / "data" / "search_plan.json", {})
        data_needs = search_plan.get("data_needs", []) if isinstance(search_plan, dict) else []
        uncovered = self._uncovered_searchable_needs(data_needs, source_records)
        actions = [self._repair_action(need, source_records) for need in uncovered]
        write_json(workspace_root / "data" / "search_repair_actions.json", actions)
        lines = [
            "# Search Repair Report",
            "",
            "## Blocking Findings",
            *[f"- {issue}" for issue in source_issues],
            "",
            "## Repair Actions",
            "",
        ]
        if not actions:
            lines.append("- No data-need-specific repair action was generated.")
        for action in actions:
            lines.extend(
                [
                    f"### {action['data_need_id']}: {action['target_dataset']}",
                    f"- Attempted query: `{action['attempted_query']}`",
                    f"- Recommended action: `{action['recommended_action']}`",
                    "- Official API candidates: "
                    + ", ".join(action["official_api_candidates"]),
                    "- Untrusted sources seen:",
                ]
            )
            untrusted_urls = action["untrusted_urls"]
            if untrusted_urls:
                lines.extend(f"  - {url}" for url in untrusted_urls)
            else:
                lines.append("  - None.")
            lines.append("")
        (workspace_root / "reports" / "search_repair_report.md").write_text(
            "\n".join(lines),
            encoding="utf-8",
        )

    def _uncovered_searchable_needs(
        self,
        data_needs: object,
        source_records: list[SourceRecord],
    ) -> list[dict[str, str]]:
        if not isinstance(data_needs, list):
            return []
        trusted_need_ids = {
            record.data_need_id
            for record in source_records
            if record.data_need_id
            and record.source_rank in {"official", "academic", "reputable"}
        }
        uncovered = []
        for need in data_needs:
            if not isinstance(need, dict):
                continue
            if need.get("source") != "data_feasibility_matrix":
                continue
            if need.get("status") in {"skipped_private_or_unavailable", "covered_by_attachment"}:
                continue
            need_id = str(need.get("need_id", "")).strip()
            if need_id and need_id not in trusted_need_ids:
                uncovered.append(
                    {
                        "need_id": need_id,
                        "target_dataset": str(need.get("target_dataset", "")),
                        "query": str(need.get("query", "")),
                    }
                )
        return uncovered

    def _repair_action(
        self,
        need: dict[str, str],
        source_records: list[SourceRecord],
    ) -> dict[str, object]:
        need_id = need["need_id"]
        untrusted_urls = [
            record.url
            for record in source_records
            if record.data_need_id == need_id
            and record.source_rank not in {"official", "academic", "reputable"}
        ]
        return {
            "data_need_id": need_id,
            "target_dataset": need["target_dataset"],
            "attempted_query": need["query"],
            "recommended_action": "try_official_api_or_reframe",
            "official_api_candidates": self._official_api_candidates(need["target_dataset"]),
            "untrusted_urls": untrusted_urls,
        }

    def _official_api_candidates(self, target_dataset: str) -> list[str]:
        lowered = target_dataset.lower()
        candidates = []
        if "population" in lowered:
            candidates.extend(["World Bank", "UNData", "US Census"])
        if "climate" in lowered or "weather" in lowered:
            candidates.extend(["NOAA", "NASA", "Open-Meteo"])
        if "economic" in lowered or "gdp" in lowered:
            candidates.extend(["World Bank", "OECD", "FRED"])
        return candidates or ["World Bank", "OECD", "UNData", "OpenAlex"]
