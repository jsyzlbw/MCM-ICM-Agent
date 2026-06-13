from pathlib import Path

from mcm_agent.agents.modeling import COUNCIL_ROLES, ModelJudge, ModelingCouncil
from mcm_agent.core.events import EventLog
from mcm_agent.core.registry import ArtifactRegistry
from mcm_agent.core.workspace import create_workspace


def test_modeling_council_writes_all_role_sections(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    problem_report = workspace.root / "reports" / "problem_understanding.md"
    direction = workspace.root / "discussion" / "confirmed_direction.md"
    problem_report.write_text("# 题意理解报告\n", encoding="utf-8")
    direction.parent.mkdir(parents=True, exist_ok=True)
    direction.write_text("# Confirmed Direction\n", encoding="utf-8")

    ModelingCouncil().run(workspace.root, problem_report, direction)

    content = (workspace.root / "reports" / "model_candidates.md").read_text(encoding="utf-8")
    for role in COUNCIL_ROLES:
        assert f"## {role}" in content
    assert EventLog(workspace.root / "event_log.jsonl").read_all()[-1].event_type == (
        "model.candidates.ready"
    )


def test_model_judge_writes_decision_and_experiment_plan(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    candidates = workspace.root / "reports" / "model_candidates.md"
    candidates.write_text("# Model Candidates\n", encoding="utf-8")

    ModelJudge().run(workspace.root, candidates)

    decision = (workspace.root / "reports" / "model_decision.md").read_text(encoding="utf-8")
    plan = (workspace.root / "reports" / "experiment_plan.md").read_text(encoding="utf-8")
    registry = ArtifactRegistry(workspace.root / "artifact_registry.json")
    events = EventLog(workspace.root / "event_log.jsonl").read_all()
    assert "## Selected Route" in decision
    assert "## Expected Code Outputs" in plan
    assert registry.get("model_decision_v1").status.value == "review_required"
    assert events[-1].event_type == "model.decision.ready"
