from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from mcm_agent.core.lineage import (
    append_citation_candidate,
    append_lineage_record,
    find_unbound_external_data,
)
from mcm_agent.core.models import CitationCandidate, DataLineageRecord
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json, write_json


NOW = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)


def test_data_lineage_record_requires_source_binding() -> None:
    with pytest.raises(ValidationError):
        DataLineageRecord(
            datum_id="datum_001",
            name="population",
            value=123,
            unit="people",
            entity="City A",
            time_period="2024",
            source_id="",
            source_url="",
            source_title="",
            accessed_at=NOW,
            local_path="data/external/source_001.md",
            extraction_method="web_extract",
            confidence=0.8,
        )


def test_citation_candidate_generates_bibtex_key_and_entry() -> None:
    candidate = CitationCandidate(
        citation_id="cite_001",
        source_id="web_001",
        title="Official Population Dataset",
        url="https://data.gov/example",
        accessed_at=NOW,
    )

    assert candidate.bibtex_key == "web_001"
    assert "Official Population Dataset" in candidate.bibtex
    assert "https://data.gov/example" in candidate.bibtex


def test_workspace_initializes_lineage_files(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")

    assert read_json(workspace.root / "data" / "data_lineage.json", None) == []
    assert read_json(workspace.root / "data" / "citation_candidates.json", None) == []


def test_append_lineage_and_citation_records(tmp_path: Path) -> None:
    lineage_path = tmp_path / "data_lineage.json"
    citation_path = tmp_path / "citation_candidates.json"

    append_lineage_record(
        lineage_path,
        DataLineageRecord(
            datum_id="datum_001",
            name="population",
            value=123,
            unit="people",
            entity="City A",
            time_period="2024",
            source_id="web_001",
            source_url="https://data.gov/example",
            source_title="Official Population Dataset",
            accessed_at=NOW,
            local_path="data/external/source_001.md",
            extraction_method="web_extract",
            confidence=0.8,
        ),
    )
    append_citation_candidate(
        citation_path,
        CitationCandidate(
            citation_id="cite_001",
            source_id="web_001",
            title="Official Population Dataset",
            url="https://data.gov/example",
            accessed_at=NOW,
        ),
    )

    assert read_json(lineage_path, [])[0]["source_id"] == "web_001"
    assert read_json(citation_path, [])[0]["bibtex_key"] == "web_001"


def test_find_unbound_external_data_reports_sources_without_lineage(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "data" / "source_registry.json",
        [
            {
                "source_id": "web_001",
                "title": "Official source",
                "url": "https://data.gov/example",
                "accessed_at": NOW.isoformat(),
                "license": "unknown",
                "provider": "FakeSearch",
                "source_rank": "official",
                "used_for": "external data discovery",
                "citation": "Official source",
                "local_path": "data/external/source_001.md",
            }
        ],
    )

    unbound = find_unbound_external_data(workspace.root)

    assert unbound == ["web_001"]
