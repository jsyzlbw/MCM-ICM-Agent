from pathlib import Path
from zipfile import ZipFile

from mcm_agent.agents.reference_manager import ReferenceManager
from mcm_agent.agents.reviewer import ReviewerAgent
from mcm_agent.agents.submission import SubmissionPackager
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json, write_json


def test_reference_manager_writes_bibtex_and_registered_citations(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    _write_registered_source(workspace.root)
    write_json(
        workspace.root / "data" / "citation_candidates.json",
        [
            {
                "citation_id": "cite_web_001",
                "source_id": "web_001",
                "title": "Official data",
                "url": "https://data.gov/example",
                "accessed_at": "2026-06-13T12:00:00Z",
            },
            {
                "citation_id": "cite_unknown",
                "source_id": "unknown",
                "title": "Unknown",
                "url": "https://example.com",
                "accessed_at": "2026-06-13T12:00:00Z",
            },
        ],
    )
    section = workspace.root / "paper" / "sections" / "results.tex"
    section.parent.mkdir(parents=True, exist_ok=True)
    section.write_text("\\section{Results}\nUses source_id=web_001.\n", encoding="utf-8")

    ReferenceManager().run(workspace.root)

    bibtex = (workspace.root / "paper" / "references.bib").read_text(encoding="utf-8")
    updated_section = section.read_text(encoding="utf-8")
    report = (workspace.root / "review" / "reference_audit_report.md").read_text(encoding="utf-8")
    assert "@misc{web_001" in bibtex
    assert "unknown" not in bibtex
    assert "\\cite{web_001}" in updated_section
    assert "Missing references: 0" in report


def test_citation_context_maps_sources_to_bibtex_keys(tmp_path: Path) -> None:
    from mcm_agent.core.citations import build_citation_context

    workspace = create_workspace(tmp_path / "run_001")
    _write_registered_source(workspace.root)
    write_json(
        workspace.root / "data" / "citation_candidates.json",
        [
            {
                "citation_id": "cite_web_001",
                "source_id": "web_001",
                "title": "Official data",
                "url": "https://data.gov/example",
                "accessed_at": "2026-06-13T12:00:00Z",
                "bibtex_key": "official_data_2026",
            }
        ],
    )

    context = build_citation_context(workspace.root)

    assert context.bibtex_key_for_source("web_001") == "official_data_2026"
    assert context.cite_command(["web_001"]) == "\\cite{official_data_2026}"
    assert context.source_title("web_001") == "Official data"


def test_reference_audit_reports_source_to_bibkey_mapping(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    _write_registered_source(workspace.root)
    write_json(
        workspace.root / "data" / "citation_candidates.json",
        [
            {
                "citation_id": "cite_web_001",
                "source_id": "web_001",
                "title": "Official data",
                "url": "https://data.gov/example",
                "accessed_at": "2026-06-13T12:00:00Z",
                "bibtex_key": "official_data_2026",
            }
        ],
    )
    section = workspace.root / "paper" / "sections" / "results.tex"
    section.parent.mkdir(parents=True, exist_ok=True)
    section.write_text("\\section{Results}\nUses source_id=web_001.\n", encoding="utf-8")

    ReferenceManager().run(workspace.root)

    report = (workspace.root / "review" / "reference_audit_report.md").read_text(
        encoding="utf-8"
    )
    assert "## Source To Bibliography Mapping" in report
    assert "- `web_001` -> `official_data_2026`" in report


def test_reviewer_blocks_used_source_missing_from_references(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    _write_registered_source(workspace.root)
    write_json(
        workspace.root / "data" / "data_lineage.json",
        [
            {
                "datum_id": "datum_web_001",
                "source_id": "web_001",
            }
        ],
    )

    ReviewerAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "final_gate.json", {})
    assert gate["status"] == "fail"
    assert any("missing from references" in item for item in gate["blocking_findings"])


def test_reference_manager_ignores_missing_source_placeholder(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    section = workspace.root / "paper" / "sections" / "results.tex"
    section.parent.mkdir(parents=True, exist_ok=True)
    section.write_text("\\section{Results}\nUses source_id=missing.\n", encoding="utf-8")

    ReferenceManager().run(workspace.root)

    report = (workspace.root / "review" / "reference_audit_report.md").read_text(
        encoding="utf-8"
    )
    assert "Missing references: 0" in report


def test_submission_packager_blocks_reference_audit_failures(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    _write_submission_ready_workspace(workspace.root)
    (workspace.root / "review" / "reference_audit_report.md").write_text(
        "# Reference Audit Report\n\nMissing references: 1\n",
        encoding="utf-8",
    )

    result = SubmissionPackager().package(workspace.root)

    assert result is False
    blocked = (workspace.root / "final_submission" / "submission_blocked.md").read_text(
        encoding="utf-8"
    )
    assert "Reference audit has missing references" in blocked


def test_submission_package_includes_audit_registries_and_checklist(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    _write_submission_ready_workspace(workspace.root)
    (workspace.root / "review" / "reference_audit_report.md").write_text(
        "# Reference Audit Report\n\nMissing references: 0\n",
        encoding="utf-8",
    )

    result = SubmissionPackager().package(workspace.root)

    assert result is True
    checklist = workspace.root / "final_submission" / "submission_checklist.md"
    assert checklist.exists()
    with ZipFile(workspace.root / "final_submission" / "source_code.zip") as archive:
        names = set(archive.namelist())
    assert "data/source_registry.json" in names
    assert "data/data_lineage.json" in names
    assert "results/evidence_registry.json" in names
    assert "review/reference_audit_report.md" in names


def _write_registered_source(workspace_root: Path) -> None:
    write_json(
        workspace_root / "data" / "source_registry.json",
        [
            {
                "source_id": "web_001",
                "title": "Official data",
                "url": "https://data.gov/example",
                "accessed_at": "2026-06-13T12:00:00Z",
                "license": "unknown",
                "provider": "FakeSearch",
                "source_rank": "official",
                "used_for": "external data discovery",
                "citation": "Official data",
                "local_path": "data/external/source_001.md",
            }
        ],
    )


def _write_submission_ready_workspace(workspace_root: Path) -> None:
    (workspace_root / "paper" / "main.pdf").write_bytes(b"%PDF")
    (workspace_root / "review" / "fact_regression_report.md").write_text(
        "# Fact Regression Report\n\n- No fact regression detected.",
        encoding="utf-8",
    )
    (workspace_root / "review" / "reviewer_report.md").write_text(
        "# Review\n\nNo blocking issue.",
        encoding="utf-8",
    )
    write_json(workspace_root / "figures" / "figure_registry.json", [])
    write_json(workspace_root / "data" / "source_registry.json", [])
    write_json(workspace_root / "data" / "data_lineage.json", [])
    write_json(workspace_root / "results" / "evidence_registry.json", [])
