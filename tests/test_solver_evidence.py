import json
from pathlib import Path

from mcm_agent.agents.eda import DataEDAAgent
from mcm_agent.agents.solver import SolverCoderAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.subprocesses import run_command
from mcm_agent.utils.json_io import read_json


def test_eda_agent_profiles_csv_and_registers_evidence(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    csv_path = workspace.root / "input" / "attachments" / "sample.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text("x,y\n1,2\n2,4\n3,6\n", encoding="utf-8")

    DataEDAAgent().run(workspace.root)

    assert (workspace.root / "data" / "processed" / "sample.csv").exists()
    assert (workspace.root / "reports" / "data_profile.md").exists()
    evidence = read_json(workspace.root / "results" / "evidence_registry.json", [])
    assert any(item["source_type"] == "attachment" for item in evidence)


def test_run_command_captures_stdout(tmp_path: Path) -> None:
    result = run_command(["python", "-c", "print('ok')"], cwd=tmp_path, timeout_seconds=10)

    assert result.return_code == 0
    assert result.stdout.strip() == "ok"


def test_solver_writes_results_metrics_and_evidence(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    processed = workspace.root / "data" / "processed" / "sample.csv"
    processed.parent.mkdir(parents=True, exist_ok=True)
    processed.write_text("x,y\n1,2\n2,4\n3,6\n", encoding="utf-8")

    SolverCoderAgent().run(workspace.root)

    metrics = json.loads((workspace.root / "results" / "model_metrics.json").read_text())
    evidence = read_json(workspace.root / "results" / "evidence_registry.json", [])
    assert (workspace.root / "code" / "problem1.py").exists()
    assert (workspace.root / "results" / "problem1_results.csv").exists()
    assert "row_count" in metrics
    assert any(item["source_path"] == "results/model_metrics.json" for item in evidence)
