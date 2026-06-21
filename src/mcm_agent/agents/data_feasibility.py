from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.models import RetrievalLogEntry
from mcm_agent.core.stage_policy import DataAvailabilityDecision, route_data_availability
from mcm_agent.providers.search import SearchProvider, SearchResult
from mcm_agent.utils.json_io import append_jsonl, read_json, write_json


PRIVATE_DATA_MARKERS = [
    "salary",
    "salaries",
    "bonus",
    "bonuses",
    "contract",
    "compensation",
    "wage",
    "wages",
    "payroll",
]

# Tabular data the contest may ship with. If any of these are present in the
# workspace, the modeling data is available by definition and we must NOT reframe
# to a proxy model (doing so poisons the whole paper's framing — see the DWTS bug
# where a single word "bonus" in the prompt triggered a false unavailable verdict
# even though the data CSV was provided).
PROVIDED_DATA_EXTS = {".csv", ".xlsx", ".xls", ".parquet", ".tsv"}


class DataFeasibilityScoutAgent:
    def __init__(self, search_provider: SearchProvider) -> None:
        self.search_provider = search_provider

    def run(self, workspace_root: Path) -> None:
        problem_report = workspace_root / "reports" / "problem_understanding.md"
        if not problem_report.exists():
            raise FileNotFoundError("missing reports/problem_understanding.md")

        problem_text = problem_report.read_text(encoding="utf-8")

        # Short-circuit: if the problem ships with data files, the modeling data is
        # available by definition. Skip the brittle web-probe (a single word like
        # "bonus" in the prompt could otherwise mark it private) and never reframe.
        provided = self._provided_data_files(workspace_root)
        if provided:
            self._emit_provided_available(workspace_root, provided)
            return

        target_datasets = self._target_datasets(workspace_root, problem_text)
        matrix = []
        all_results = []
        for index, target_dataset in enumerate(target_datasets, start=1):
            query = f"{target_dataset} public dataset official"
            results = self.search_provider.search(query, max_results=5)
            all_results.extend(results)
            append_jsonl(
                workspace_root / "data" / "retrieval_log.jsonl",
                RetrievalLogEntry(
                    time=datetime.now(UTC),
                    provider=self.search_provider.__class__.__name__,
                    query=query,
                    top_urls=[result.url for result in results],
                    decision="data_feasibility_probe",
                ).model_dump(mode="json"),
            )
            availability = self._classify_availability(problem_text, results, target_dataset)
            row = self._matrix_row(index, availability, query, results)
            matrix.append(row)

        write_json(workspace_root / "data" / "data_feasibility_matrix.json", matrix)

        availability = self._aggregate_availability(matrix)
        route = route_data_availability(availability)

        report_path = workspace_root / "reports" / "data_feasibility_report.md"
        report_path.write_text(
            self._build_report(availability, route.recommendation, all_results, matrix),
            encoding="utf-8",
        )
        write_json(
            workspace_root / "reports" / "data_feasibility_decision.json",
            {
                "availability": availability.model_dump(mode="json"),
                "route": route.model_dump(mode="json"),
                "matrix": matrix,
                "top_results": [result.model_dump(mode="json") for result in all_results],
            },
        )

        event_type = (
            "data.feasibility.reframe_required"
            if route.next_stage == "research_reframing"
            else "data.feasibility.ready"
        )
        Coordinator(workspace_root).emit(
            event_type,
            payload={"next_stage": route.next_stage},
            source="DataFeasibilityScoutAgent",
        )

    def _provided_data_files(self, workspace_root: Path) -> list[Path]:
        """Return tabular data files the contest shipped with (uploads / raw data)."""
        found: list[Path] = []
        for directory in (
            workspace_root / "input" / "attachments",
            workspace_root / "data" / "raw",
        ):
            if directory.is_dir():
                for path in sorted(directory.iterdir()):
                    if path.is_file() and path.suffix.lower() in PROVIDED_DATA_EXTS:
                        found.append(path)
        return found

    def _emit_provided_available(self, workspace_root: Path, provided: list[Path]) -> None:
        """Record an 'available' decision (no web-probe, no proxy reframe) because the
        problem already ships with data, and route forward to user_discussion."""
        names = ", ".join(path.name for path in provided)
        availability = DataAvailabilityDecision(
            target_dataset="provided contest data",
            availability="available",
            confidence=0.95,
            reason=(
                f"The problem ships with {len(provided)} provided data file(s): {names}. "
                "The modeling data is available; no proxy reframing is needed."
            ),
        )
        route = route_data_availability(availability)
        provided_row = self._matrix_row(1, availability, "provided contest data files", [])
        # The shipped data IS the source: mark the need covered so search_data /
        # source_verifier do not treat it as a searchable need needing web coverage.
        provided_row["covered_by_attachment"] = True
        matrix = [provided_row]
        write_json(workspace_root / "data" / "data_feasibility_matrix.json", matrix)
        (workspace_root / "reports" / "data_feasibility_report.md").write_text(
            self._build_report(availability, route.recommendation, [], matrix),
            encoding="utf-8",
        )
        write_json(
            workspace_root / "reports" / "data_feasibility_decision.json",
            {
                "availability": availability.model_dump(mode="json"),
                "route": route.model_dump(mode="json"),
                "matrix": matrix,
                "top_results": [],
            },
        )
        Coordinator(workspace_root).emit(
            "data.feasibility.ready",
            payload={"next_stage": route.next_stage},
            source="DataFeasibilityScoutAgent",
        )

    def _infer_target_dataset(self, problem_text: str) -> str:
        lowered = problem_text.lower()
        if "football" in lowered and any(marker in lowered for marker in PRIVATE_DATA_MARKERS):
            return "football player salary and bonus contracts"
        if "climate" in lowered:
            return "public climate data"
        if "population" in lowered:
            return "public population data"
        return "problem-specific modeling data"

    def _target_datasets(self, workspace_root: Path, problem_text: str) -> list[str]:
        discussion_needs = self._target_datasets_from_discussion(workspace_root)
        if discussion_needs:
            return discussion_needs
        return [self._infer_target_dataset(problem_text)]

    def _target_dataset_from_discussion(self, workspace_root: Path) -> str | None:
        datasets = self._target_datasets_from_discussion(workspace_root)
        if not datasets:
            return None
        return datasets[0]

    def _target_datasets_from_discussion(self, workspace_root: Path) -> list[str]:
        questions = read_json(workspace_root / "discussion" / "data_questions.json", [])
        if not isinstance(questions, list):
            return []
        return [str(question).strip() for question in questions if str(question).strip()]

    def _classify_availability(
        self,
        problem_text: str,
        results: list[SearchResult],
        target_dataset: str | None = None,
    ) -> DataAvailabilityDecision:
        target_dataset = target_dataset or self._infer_target_dataset(problem_text)
        lowered = f"{problem_text} {target_dataset}".lower()
        private_signal = any(marker in lowered for marker in PRIVATE_DATA_MARKERS)
        official_result = any(
            marker in result.url for result in results for marker in [".gov", "data.gov", ".edu"]
        )
        if private_signal and not official_result:
            return DataAvailabilityDecision(
                target_dataset=target_dataset,
                availability="private_or_unavailable",
                confidence=0.9,
                reason="The problem appears to require salary, bonus, contract, or compensation data.",
            )
        if official_result:
            return DataAvailabilityDecision(
                target_dataset=target_dataset,
                availability="available",
                confidence=0.75,
                reason="At least one official or institutional result was found in the early probe.",
            )
        return DataAvailabilityDecision(
            target_dataset=target_dataset,
            availability="unknown",
            confidence=0.55,
            reason="The early probe did not find an official source, but the data need is not clearly private.",
        )

    def _matrix_row(
        self,
        index: int,
        availability: DataAvailabilityDecision,
        query: str,
        results: list[SearchResult],
    ) -> dict[str, object]:
        route = route_data_availability(availability)
        return {
            "need_id": f"need_{index:03d}",
            "target_dataset": availability.target_dataset,
            "query": query,
            "availability": availability.availability,
            "confidence": availability.confidence,
            "reason": availability.reason,
            "top_urls": [result.url for result in results],
            "proxy_variables": self._proxy_variables(availability),
            "recommended_action": route.recommendation,
        }

    def _aggregate_availability(self, matrix: list[dict[str, object]]) -> DataAvailabilityDecision:
        decisions = [
            DataAvailabilityDecision(
                target_dataset=str(row["target_dataset"]),
                availability=row["availability"],
                confidence=float(row["confidence"]),
                reason=str(row["reason"]),
            )
            for row in matrix
        ]
        for decision in decisions:
            if decision.availability == "private_or_unavailable" and decision.confidence >= 0.8:
                return decision
        for decision in decisions:
            if decision.availability == "proxy_required":
                return decision
        for decision in decisions:
            if decision.availability == "unknown":
                return decision
        return decisions[0]

    def _proxy_variables(self, availability: DataAvailabilityDecision) -> list[str]:
        if availability.availability != "private_or_unavailable":
            return []
        return [
            "Player performance statistics",
            "Market value or transfer fee",
            "Age, position, league strength, injury history, and playing time",
            "Team revenue, ranking, attendance, or budget class",
        ]

    def _build_report(
        self,
        availability: DataAvailabilityDecision,
        recommendation: str,
        results: list[SearchResult],
        matrix: list[dict[str, object]] | None = None,
    ) -> str:
        lines = [
            "# Data Feasibility Report",
            "",
            "## Target Dataset",
            availability.target_dataset,
            "",
            "## Availability",
            availability.availability,
            "",
            "## Reason",
            availability.reason,
            "",
            "## Recommendation",
            recommendation,
            "",
        ]
        matrix = matrix or []
        if matrix:
            lines.extend(["## Feasibility Matrix", ""])
            for row in matrix:
                lines.extend(
                    [
                        f"### {row['need_id']}: {row['target_dataset']}",
                        f"- Availability: {row['availability']}",
                        f"- Confidence: {row['confidence']}",
                        f"- Query: `{row['query']}`",
                        f"- Reason: {row['reason']}",
                        f"- Recommended action: {row['recommended_action']}",
                    ]
                )
                proxy_variables = row.get("proxy_variables", [])
                if isinstance(proxy_variables, list) and proxy_variables:
                    lines.append("- Proxy variables:")
                    lines.extend(f"  - {proxy}" for proxy in proxy_variables)
                lines.append("")
        if availability.availability == "private_or_unavailable":
            lines.extend(
                [
                    "## Proxy Variables",
                    *[f"- {proxy}" for proxy in self._proxy_variables(availability)],
                    "",
                ]
            )
        lines.extend(["## Early Search Results", ""])
        if results:
            for result in results:
                lines.append(f"- {result.title}: {result.url}")
        else:
            lines.append("- No usable early search result.")
        return "\n".join(lines) + "\n"
