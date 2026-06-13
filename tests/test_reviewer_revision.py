from pathlib import Path

from mcm_agent.agents.reviewer import ReviewerAgent
from mcm_agent.agents.revision import RevisionAgent
from mcm_agent.core.events import EventLog
from mcm_agent.core.models import ArtifactRecord, ArtifactStatus
from mcm_agent.core.registry import ArtifactRegistry
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import write_json


def test_reviewer_writes_reports_and_passes_clean_workspace(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "paper" / "main.tex").write_text("\\begin{document}x\\end{document}")
    (workspace.root / "paper" / "compile_log.txt").write_text("ok", encoding="utf-8")
    (workspace.root / "review" / "fact_regression_report.md").write_text(
        "# Fact Regression Report\n\n- No fact regression detected.",
        encoding="utf-8",
    )
    write_json(workspace.root / "figures" / "figure_registry.json", [])
    write_json(workspace.root / "results" / "evidence_registry.json", [])

    ReviewerAgent().run(workspace.root)

    events = EventLog(workspace.root / "event_log.jsonl").read_all()
    assert (workspace.root / "review" / "reviewer_report.md").exists()
    assert events[-1].event_type == "paper.review.passed"


def test_reviewer_fails_with_unresolved_placeholder(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "unresolved_issues.md").write_text("[[UNRESOLVED:\n]]")

    ReviewerAgent().run(workspace.root)

    events = EventLog(workspace.root / "event_log.jsonl").read_all()
    assert events[-1].event_type == "paper.review.failed"


def test_revision_marks_artifacts_stale_for_result_request(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    registry = ArtifactRegistry(workspace.root / "artifact_registry.json")
    registry.add(
        ArtifactRecord(
            artifact_id="figure_v1",
            type="figure",
            path="figures/figure.pdf",
            producer="VisualizationAgent",
            depends_on=["model_decision_v1"],
            status=ArtifactStatus.APPROVED,
            created_at="2026-06-13T12:00:00Z",
        )
    )

    RevisionAgent().apply_revision_request(workspace.root, "Please rerun the model results.")

    assert (workspace.root / "review" / "revision_requests.md").exists()
    assert registry.get("figure_v1").status == ArtifactStatus.STALE
