from pathlib import Path

import pytest

from mcm_agent.core.gate_decision import GateDecision, record_gate_decision
from mcm_agent.core.stage_executor import RepeatedGateFailureError, StageExecutor, StageResult
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json


def test_workspace_initializes_stage_execution_files(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")

    assert (workspace.root / "stage_runs.jsonl").exists()
    assert read_json(workspace.root / "review" / "gate_decisions.json", None) == []


def test_stage_executor_records_successful_stage_run_and_next_stage(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")

    executor = StageExecutor(
        workspace.root,
        handlers={"problem_understanding": lambda root: ["reports/problem_understanding.md"]},
    )
    record = executor.run_stage("problem_understanding")

    stage_log = (workspace.root / "stage_runs.jsonl").read_text(encoding="utf-8")
    assert record.status == "passed"
    assert record.next_stage == "data_feasibility_scout"
    assert "problem_understanding" in stage_log


def test_stage_executor_follows_stage_result_condition(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")

    executor = StageExecutor(
        workspace.root,
        handlers={"user_discussion": lambda root: StageResult(condition="direction_locked")},
    )
    record = executor.run_stage("user_discussion")

    assert record.next_stage == "methodology_rag"


def test_stage_executor_records_failed_stage_run(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")

    def broken_handler(root: Path) -> list[str]:
        raise RuntimeError("boom")

    executor = StageExecutor(workspace.root, handlers={"solver_coder": broken_handler})

    with pytest.raises(RuntimeError, match="boom"):
        executor.run_stage("solver_coder")

    stage_log = (workspace.root / "stage_runs.jsonl").read_text(encoding="utf-8")
    assert "failed" in stage_log
    assert "boom" in stage_log


def test_stage_executor_routes_gate_failures_from_topology(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    executor = StageExecutor(workspace.root)

    assert executor.route_failure("validation_gate", "bad_data") == "search_data"
    assert executor.route_failure("figure_quality_gate", "visual_or_vector_issue") == (
        "figure_planning"
    )


def test_stage_executor_uses_gate_decision_repair_stage(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    executor = StageExecutor(workspace.root)

    decision = GateDecision(
        gate_id="validation_gate",
        status="fail",
        failure_reason="bad_data",
        blocking_findings=["External data is invalid."],
    )

    assert executor.next_stage_from_gate(decision) == "search_data"


def test_stage_executor_reads_gate_file_for_gate_stage(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")

    def validation_handler(root: Path) -> StageResult:
        record_gate_decision(
            root,
            "validation_gate.json",
            GateDecision(
                gate_id="validation_gate",
                status="fail",
                failure_reason="bad_results",
                repair_stage="solver_coder",
                blocking_findings=["Metric evidence missing."],
            ),
        )
        return StageResult(outputs=["review/validation_gate.json"])

    executor = StageExecutor(workspace.root, handlers={"validation_gate": validation_handler})
    record = executor.run_stage("validation_gate")

    assert record.next_stage == "solver_coder"


def test_stage_executor_run_until_complete_stops_at_terminal_stage(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    visited: list[str] = []

    def user_discussion(root: Path) -> StageResult:
        visited.append("user_discussion")
        return StageResult(condition="direction_locked")

    def methodology_rag(root: Path) -> list[str]:
        visited.append("methodology_rag")
        return ["rag/methodology_hits.json"]

    executor = StageExecutor(
        workspace.root,
        handlers={
            "user_discussion": user_discussion,
            "methodology_rag": methodology_rag,
        },
    )

    records = executor.run_until_complete("user_discussion", terminal_stage="methodology_rag")

    assert [record.stage_id for record in records] == ["user_discussion", "methodology_rag"]
    assert visited == ["user_discussion", "methodology_rag"]


def test_stage_executor_stops_repeated_gate_failure_loop(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")

    def search_data(root: Path) -> list[str]:
        return ["data/source_registry.json"]

    def source_verifier(root: Path) -> list[str]:
        record_gate_decision(
            root,
            "source_gate.json",
            GateDecision(
                gate_id="source_verifier",
                status="fail",
                failure_reason="source_unreliable",
                repair_stage="search_data",
                blocking_findings=["No trusted source found."],
            ),
        )
        return ["review/source_gate.json"]

    executor = StageExecutor(
        workspace.root,
        handlers={"search_data": search_data, "source_verifier": source_verifier},
    )

    with pytest.raises(RepeatedGateFailureError, match="source_verifier/source_unreliable"):
        executor.run_until_complete("search_data", repeated_gate_limit=2)

    state = read_json(workspace.root / "task_state.json", {})
    assert state["current_phase"] == "source_verifier"
    assert state["blocked_reason"] == "source_verifier/source_unreliable"
