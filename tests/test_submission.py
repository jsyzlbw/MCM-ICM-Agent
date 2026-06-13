from pathlib import Path
from zipfile import ZipFile

from mcm_agent.agents.submission import SubmissionPackager
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json
from mcm_agent.utils.json_io import write_json


def test_submission_packager_blocks_unresolved_placeholders(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "unresolved_issues.md").write_text("[[UNRESOLVED:\n]]")

    result = SubmissionPackager().package(workspace.root)

    assert result is False
    assert (workspace.root / "final_submission" / "submission_blocked.md").exists()


def test_submission_packager_writes_ai_report_and_source_zip(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "paper" / "main.pdf").write_bytes(b"%PDF")
    (workspace.root / "review" / "fact_regression_report.md").write_text(
        "# Fact Regression Report\n\n- No fact regression detected.",
        encoding="utf-8",
    )
    (workspace.root / "review" / "reviewer_report.md").write_text(
        "# Review\n\nNo blocking issue.",
        encoding="utf-8",
    )
    write_json(workspace.root / "figures" / "figure_registry.json", [])

    result = SubmissionPackager().package(workspace.root)

    assert result is True
    assert (workspace.root / "final_submission" / "AI_use_report.md").exists()
    assert (workspace.root / "final_submission" / "source_code.zip").exists()
    assert (workspace.root / "final_submission" / "submission_package.zip").exists()


def test_submission_packager_writes_manifest_with_route_and_audit_files(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "paper" / "main.pdf").write_bytes(b"%PDF")
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {"selected_routes": ["multi_criteria_evaluation"], "route_metrics": {}},
    )
    write_json(workspace.root / "results" / "evidence_registry.json", [])
    write_json(workspace.root / "figures" / "figure_registry.json", [])
    write_json(workspace.root / "data" / "source_registry.json", [])
    write_json(workspace.root / "data" / "data_lineage.json", [])
    (workspace.root / "review" / "reference_audit_report.md").write_text(
        "# Reference Audit Report\n\nMissing references: 0\n",
        encoding="utf-8",
    )

    result = SubmissionPackager().package(workspace.root)

    manifest = read_json(workspace.root / "final_submission" / "submission_manifest.json", {})
    assert result is True
    assert manifest["model_routes"] == ["multi_criteria_evaluation"]
    assert "results/model_route_summary.json" in manifest["audit_files"]
    with ZipFile(workspace.root / "final_submission" / "source_code.zip") as archive:
        assert "results/model_route_summary.json" in set(archive.namelist())
