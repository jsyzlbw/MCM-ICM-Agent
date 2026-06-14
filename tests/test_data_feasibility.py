from pathlib import Path

from mcm_agent.agents.data_feasibility import DataFeasibilityScoutAgent
from mcm_agent.core.events import EventLog
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.search import SearchResult
from mcm_agent.utils.json_io import read_json
from mcm_agent.utils.json_io import write_json


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


def test_data_feasibility_scout_writes_matrix_for_discussion_data_needs(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "problem_understanding.md").write_text(
        "The task asks for a disaster response model.",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "discussion" / "data_questions.json",
        ["public population data", "football player salary and bonus contracts"],
    )

    class MixedSearchProvider:
        def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
            if "population" in query:
                return [
                    SearchResult(
                        title="Official population data",
                        url="https://data.gov/population",
                        snippet="Official dataset.",
                        score=0.9,
                    )
                ]
            return []

    DataFeasibilityScoutAgent(MixedSearchProvider()).run(workspace.root)

    matrix = read_json(workspace.root / "data" / "data_feasibility_matrix.json", [])
    assert [row["target_dataset"] for row in matrix] == [
        "public population data",
        "football player salary and bonus contracts",
    ]
    assert matrix[0]["availability"] == "available"
    assert matrix[1]["availability"] == "private_or_unavailable"
    assert "Market value or transfer fee" in matrix[1]["proxy_variables"]


def test_data_feasibility_scout_routes_unknown_need_to_search_data(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "problem_understanding.md").write_text(
        "The task asks for a custom sports performance index.",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "discussion" / "data_questions.json",
        ["custom sports performance index data"],
    )

    DataFeasibilityScoutAgent(EmptySearchProvider()).run(workspace.root)

    decision = read_json(workspace.root / "reports" / "data_feasibility_decision.json", {})
    assert decision["route"]["next_stage"] == "search_data"
    assert decision["route"]["requires_user_discussion"] is False
