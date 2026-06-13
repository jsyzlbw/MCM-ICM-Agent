from pathlib import Path

from mcm_agent.agents.data_feasibility import DataFeasibilityScoutAgent
from mcm_agent.core.events import EventLog
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.search import SearchResult
from mcm_agent.utils.json_io import read_json


class EmptySearchProvider:
    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        return []


class OfficialSearchProvider:
    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                title="Official public dataset",
                url="https://data.gov/example",
                snippet="Public data source.",
                score=0.9,
            )
        ]


def test_data_feasibility_scout_reframes_likely_private_salary_data(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "problem_understanding.md").write_text(
        "The task asks how to set football player salary and bonus contract standards.",
        encoding="utf-8",
    )

    DataFeasibilityScoutAgent(EmptySearchProvider()).run(workspace.root)

    decision = read_json(workspace.root / "reports" / "data_feasibility_decision.json", {})
    report = (workspace.root / "reports" / "data_feasibility_report.md").read_text(
        encoding="utf-8"
    )
    events = EventLog(workspace.root / "event_log.jsonl").read_all()
    assert decision["route"]["next_stage"] == "research_reframing"
    assert decision["route"]["requires_user_discussion"] is True
    assert "proxy variables" in report
    assert "salary" in report
    assert events[-1].event_type == "data.feasibility.reframe_required"


def test_data_feasibility_scout_allows_available_public_data(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "problem_understanding.md").write_text(
        "The task requires public population and climate data.",
        encoding="utf-8",
    )

    DataFeasibilityScoutAgent(OfficialSearchProvider()).run(workspace.root)

    decision = read_json(workspace.root / "reports" / "data_feasibility_decision.json", {})
    assert decision["availability"]["availability"] == "available"
    assert decision["route"]["next_stage"] == "user_discussion"
