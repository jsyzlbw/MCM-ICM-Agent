from __future__ import annotations

from pathlib import Path

from mcm_agent.core.models import CitationCandidate, DataLineageRecord
from mcm_agent.utils.json_io import read_json, write_json


def append_lineage_record(path: Path, record: DataLineageRecord) -> None:
    records = read_json(path, [])
    records.append(record.model_dump(mode="json"))
    write_json(path, records)


def append_citation_candidate(path: Path, candidate: CitationCandidate) -> None:
    records = read_json(path, [])
    records.append(candidate.model_dump(mode="json"))
    write_json(path, records)


def find_unbound_external_data(workspace_root: Path) -> list[str]:
    sources = read_json(workspace_root / "data" / "source_registry.json", [])
    lineage = read_json(workspace_root / "data" / "data_lineage.json", [])
    bound_source_ids = {record.get("source_id") for record in lineage}
    unbound: list[str] = []
    for source in sources:
        source_id = source.get("source_id")
        if source.get("used_for") == "background":
            continue
        if source_id and source_id not in bound_source_ids:
            unbound.append(str(source_id))
    return unbound
