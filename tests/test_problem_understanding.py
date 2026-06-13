from pathlib import Path

import pytest

from mcm_agent.agents.discussion import UserDiscussionAgent
from mcm_agent.agents.problem_understanding import (
    REQUIRED_HEADINGS,
    ProblemUnderstandingAgent,
    validate_required_headings,
)
from mcm_agent.core.events import EventLog
from mcm_agent.core.registry import ArtifactRegistry
from mcm_agent.core.workspace import create_workspace


def test_validate_required_headings_rejects_missing_heading() -> None:
    with pytest.raises(ValueError, match="problem understanding report missing heading"):
        validate_required_headings("# 题意理解报告\n\n## 题目背景\n")


def test_problem_understanding_agent_writes_report_checkpoint(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "parsed" / "problem.md").write_text(
        "# Problem\n\nBuild a predictive and optimization model.",
        encoding="utf-8",
    )
    (workspace.root / "input_manifest.json").write_text("{}", encoding="utf-8")
    (workspace.root / "reports" / "attachment_inventory.md").write_text(
        "# Attachment Inventory\n",
        encoding="utf-8",
    )

    ProblemUnderstandingAgent().run(workspace.root)

    report = (workspace.root / "reports" / "problem_understanding.md").read_text(
        encoding="utf-8"
    )
    registry = ArtifactRegistry(workspace.root / "artifact_registry.json")
    events = EventLog(workspace.root / "event_log.jsonl").read_all()
    for heading in REQUIRED_HEADINGS:
        assert heading in report
    assert registry.get("problem_understanding_v1").status.value == "review_required"
    assert events[-1].event_type == "problem.understanding.ready"


def test_user_discussion_agent_writes_confirmed_direction(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")

    UserDiscussionAgent().confirm_direction(
        workspace.root,
        mode="ai_led",
        user_idea_summary="Prefer explainable models.",
        selected_route="Baseline forecasting plus constrained optimization.",
        paper_outline="Abstract, assumptions, model, results, sensitivity, conclusion.",
        decisions_to_preserve=["Keep figures vector-first."],
    )

    content = (workspace.root / "discussion" / "confirmed_direction.md").read_text(
        encoding="utf-8"
    )
    events = EventLog(workspace.root / "event_log.jsonl").read_all()
    assert "## User Mode" in content
    assert "Baseline forecasting" in content
    assert events[-1].event_type == "user.direction.confirmed"
