import json
from pathlib import Path

from mcm_agent.agents.eda import DataEDAAgent
from mcm_agent.agents.solver import SolverCoderAgent
from mcm_agent.core.models import DataLineageRecord
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json
from mcm_agent.utils.subprocesses import run_command
from mcm_agent.core.lineage import append_lineage_record


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


def test_eda_and_solver_preserve_external_data_lineage(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    external = workspace.root / "data" / "external" / "source_001.csv"
    external.parent.mkdir(parents=True, exist_ok=True)
    external.write_text("x,y\n1,2\n2,4\n", encoding="utf-8")
    append_lineage_record(
        workspace.root / "data" / "data_lineage.json",
        DataLineageRecord(
            datum_id="datum_web_001",
            name="Official data",
            value="source-level dataset",
            unit="source",
            entity="external_source",
            time_period="2024",
            source_id="web_001",
            source_url="https://data.gov/example",
            source_title="Official data",
            accessed_at="2026-06-13T12:00:00Z",
            local_path="data/external/source_001.csv",
            extraction_method="test",
            confidence=0.9,
        ),
    )

    DataEDAAgent().run(workspace.root)
    SolverCoderAgent().run(workspace.root)

    evidence = read_json(workspace.root / "results" / "evidence_registry.json", [])
    eda_evidence = next(item for item in evidence if item["evidence_id"] == "eda_source_001_row_count")
    metric_evidence = next(item for item in evidence if item["evidence_id"] == "metric_row_count")
    assert eda_evidence["source_type"] == "external_data"
    assert eda_evidence["lineage_ids"] == ["datum_web_001"]
    assert metric_evidence["lineage_ids"] == ["datum_web_001"]


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
