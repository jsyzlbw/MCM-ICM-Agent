import json
from pathlib import Path

from mcm_agent.agents.solver import SolverCoderAgent
from mcm_agent.agents.validation import ValidationAgent
from mcm_agent.core.experiment import run_experiment
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import append_jsonl, read_json, write_json


def test_experiment_runner_records_command_outputs_and_products(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    script = workspace.root / "code" / "experiments" / "hello.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "from pathlib import Path\n"
        "Path('results/demo.txt').write_text('ok', encoding='utf-8')\n"
        "print('done')\n",
        encoding="utf-8",
    )

    record = run_experiment(
        workspace.root,
        ["python", "code/experiments/hello.py"],
        produced_files=["results/demo.txt"],
        timeout_seconds=10,
    )

    runs = [
        json.loads(line)
        for line in (workspace.root / "results" / "experiment_runs.jsonl").read_text().splitlines()
    ]
    assert record.exit_code == 0
    assert record.stdout_path
    assert (workspace.root / record.stdout_path).read_text(encoding="utf-8").strip() == "done"
    assert runs[0]["produced_files"] == ["results/demo.txt"]


def test_solver_records_reproducible_experiment_run(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    processed = workspace.root / "data" / "processed" / "sample.csv"
    processed.parent.mkdir(parents=True, exist_ok=True)
    processed.write_text("x,y\n1,2\n2,4\n3,6\n", encoding="utf-8")

    SolverCoderAgent().run(workspace.root)

    runs = [
        json.loads(line)
        for line in (workspace.root / "results" / "experiment_runs.jsonl").read_text().splitlines()
    ]
    evidence = read_json(workspace.root / "results" / "evidence_registry.json", [])
    assert (workspace.root / "code" / "experiments" / "problem1.py").exists()
    assert runs[0]["exit_code"] == 0
    assert "results/problem1_results.csv" in runs[0]["produced_files"]
    assert any(item["generated_by"] == "code/experiments/problem1.py" for item in evidence)


def test_validation_fails_when_experiment_run_failed(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(workspace.root / "results" / "model_metrics.json", {"row_count": 3})
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [
            {
                "evidence_id": "metric_row_count",
                "source_path": "results/model_metrics.json",
            }
        ],
    )
    append_jsonl(
        workspace.root / "results" / "experiment_runs.jsonl",
        {
            "run_id": "run_failed",
            "exit_code": 1,
            "missing_outputs": ["results/problem1_results.csv"],
        },
    )

    ValidationAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "validation_gate.json", {})
    assert gate["status"] == "fail"
    assert any("Experiment run `run_failed` failed" in item for item in gate["blocking_findings"])
