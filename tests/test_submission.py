from pathlib import Path

from mcm_agent.agents.submission import SubmissionPackager
from mcm_agent.core.workspace import create_workspace
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
