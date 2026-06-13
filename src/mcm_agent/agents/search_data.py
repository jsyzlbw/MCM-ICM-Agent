from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.models import RetrievalLogEntry, SourceRecord
from mcm_agent.providers.search import ExtractProvider, SearchProvider
from mcm_agent.utils.json_io import append_jsonl, read_json, write_json


class SearchDataAgent:
    def __init__(self, search_provider: SearchProvider, extract_provider: ExtractProvider) -> None:
        self.search_provider = search_provider
        self.extract_provider = extract_provider

    def run(self, workspace_root: Path) -> None:
        experiment_plan = workspace_root / "reports" / "experiment_plan.md"
        if not experiment_plan.exists():
            raise FileNotFoundError("missing reports/experiment_plan.md")

        queries = self._queries_from_plan(experiment_plan.read_text(encoding="utf-8"))
        source_records: list[SourceRecord] = []
        registry_path = workspace_root / "data" / "source_registry.json"
        log_path = workspace_root / "data" / "retrieval_log.jsonl"

        for query in queries:
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
                page = self.extract_provider.extract(result.url)
                extracted_path = workspace_root / "data" / "external" / f"source_{len(source_records)+1:03d}.md"
                extracted_path.parent.mkdir(parents=True, exist_ok=True)
                extracted_path.write_text(page.markdown, encoding="utf-8")
                source_rank = self._rank_source(result.url)
                record = SourceRecord(
                    source_id=f"web_{len(source_records)+1:03d}",
                    title=result.title,
                    url=result.url,
                    accessed_at=datetime.now(UTC),
                    license="unknown",
                    provider=self.search_provider.__class__.__name__,
                    source_rank=source_rank,
                    used_for="external data discovery" if source_rank == "official" else "background",
                    citation=result.title,
                    local_path=str(extracted_path.relative_to(workspace_root)),
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
        Coordinator(workspace_root).emit("data.ready", source="SearchDataAgent")

    def _queries_from_plan(self, plan: str) -> list[str]:
        for line in plan.splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                return [stripped[2:]]
        return ["external data for math modeling problem"]

    def _rank_source(self, url: str) -> str:
        official_markers = ["data.gov", ".gov", "worldbank.org", "oecd.org", "un.org"]
        if any(marker in url for marker in official_markers):
            return "official"
        return "background_only"
