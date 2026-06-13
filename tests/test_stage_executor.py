from pathlib import Path

import pytest

from mcm_agent.core.gate_decision import GateDecision
from mcm_agent.core.stage_executor import StageExecutor
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
