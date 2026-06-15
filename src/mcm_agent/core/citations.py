from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from mcm_agent.utils.json_io import read_json


PLACEHOLDER_SOURCE_IDS = {"missing", "none", "unknown"}


class CitationSource(BaseModel):
    source_id: str
    title: str = ""
    source_rank: str = ""
    bibtex_key: str = ""


class CitationContext(BaseModel):
    sources: dict[str, CitationSource] = Field(default_factory=dict)

    def bibtex_key_for_source(self, source_id: str) -> str:
        source = self.sources.get(source_id)
        return source.bibtex_key if source else ""

    def source_title(self, source_id: str) -> str:
        source = self.sources.get(source_id)
        return source.title if source else ""

    def cite_command(self, source_ids: list[str]) -> str:
        keys = []
        for source_id in source_ids:
            key = self.bibtex_key_for_source(source_id)
            if key and key not in keys:
                keys.append(key)
        return "\\cite{" + ",".join(keys) + "}" if keys else ""

    def citation_keys_for_sources(self, source_ids: list[str]) -> list[str]:
        keys = []
        for source_id in source_ids:
            key = self.bibtex_key_for_source(source_id)
            if key and key not in keys:
                keys.append(key)
        return keys


def build_citation_context(workspace_root: Path) -> CitationContext:
    source_rows = _rows(read_json(workspace_root / "data" / "source_registry.json", []))
    candidate_rows = _rows(read_json(workspace_root / "data" / "citation_candidates.json", []))
    candidate_keys = {
        str(row["source_id"]): str(row.get("bibtex_key") or row["source_id"])
        for row in candidate_rows
        if row.get("source_id")
    }
    sources: dict[str, CitationSource] = {}
    for row in source_rows:
        source_id = str(row.get("source_id", "")).strip()
        if not source_id or source_id in PLACEHOLDER_SOURCE_IDS:
            continue
        sources[source_id] = CitationSource(
            source_id=source_id,
            title=str(row.get("title", "")),
            source_rank=str(row.get("source_rank", "")),
            bibtex_key=candidate_keys.get(source_id, source_id),
        )
    return CitationContext(sources=sources)


def _rows(value: object) -> list[dict[str, object]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []
