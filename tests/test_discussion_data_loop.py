from pathlib import Path

from mcm_agent.agents.data_feasibility import DataFeasibilityScoutAgent
from mcm_agent.agents.discussion import UserDiscussionAgent
from mcm_agent.core.discussion_state import DiscussionDecision
from mcm_agent.core.events import EventLog
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.search import SearchResult
from mcm_agent.utils.json_io import read_json


class EmptySearchProvider:
    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        return []


def test_discussion_with_new_data_need_writes_unlocked_direction(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")

    UserDiscussionAgent().confirm_direction(
        workspace.root,
        mode="hybrid",
        user_idea_summary="Use real salary bonuses if possible.",
        selected_route="Compensation strategy with public proxy fallback.",
        paper_outline="Abstract, model, results.",
        decisions_to_preserve=["Avoid unsupported salary claims."],
        new_data_needs=["football player salary and bonus contracts"],
    )

    decision = read_json(workspace.root / "discussion" / "direction_lock.json", {})
    questions = read_json(workspace.root / "discussion" / "data_questions.json", [])
    events = EventLog(workspace.root / "event_log.jsonl").read_all()

    assert decision["status"] == "needs_data_scout"
    assert decision["requires_data_scout"] is True
    assert questions == ["football player salary and bonus contracts"]
    assert not (workspace.root / "discussion" / "confirmed_direction.md").exists()
    assert events[-1].event_type == "discussion.new_data_requested"


def test_discussion_without_new_data_need_locks_direction(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")

    UserDiscussionAgent().confirm_direction(
        workspace.root,
        mode="ai_led",
        user_idea_summary="Use public climate data.",
        selected_route="Public-data route.",
        paper_outline="Abstract, model, results.",
        decisions_to_preserve=["Use vector-first figures."],
    )

    decision = read_json(workspace.root / "discussion" / "direction_lock.json", {})
    events = EventLog(workspace.root / "event_log.jsonl").read_all()

    assert decision["status"] == "locked"
    assert decision["requires_data_scout"] is False
    assert (workspace.root / "discussion" / "confirmed_direction.md").exists()
    assert events[-1].event_type == "user.direction.confirmed"


def test_data_scout_uses_discussion_data_questions(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "problem_understanding.md").write_text(
        "The task needs a fair compensation strategy.",
        encoding="utf-8",
    )
    (workspace.root / "discussion" / "data_questions.json").write_text(
        '["football player salary and bonus contracts"]',
        encoding="utf-8",
    )

    DataFeasibilityScoutAgent(EmptySearchProvider()).run(workspace.root)

    decision = read_json(workspace.root / "reports" / "data_feasibility_decision.json", {})
    assert decision["availability"]["target_dataset"] == (
        "football player salary and bonus contracts"
    )
    assert decision["availability"]["availability"] == "private_or_unavailable"


def test_discussion_decision_requires_unlocked_status_for_new_data_needs() -> None:
    decision = DiscussionDecision(
        status="needs_data_scout",
        selected_route="Compensation proxy route.",
        new_data_needs=["football player salary and bonus contracts"],
    )

    assert decision.requires_data_scout is True
