import json
from pathlib import Path

from mcm_agent.agents.eda import DataEDAAgent
from mcm_agent.agents.solver import SolverCoderAgent
from mcm_agent.core.experiment_spec import build_experiment_spec
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


def test_eda_agent_writes_schema_profile_with_semantic_hints(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    csv_path = workspace.root / "input" / "attachments" / "sample.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(
        "origin,destination,distance,year,sales\nA,B,1,2021,10\nB,C,2,2022,\n",
        encoding="utf-8",
    )

    DataEDAAgent().run(workspace.root)

    profile = read_json(workspace.root / "results" / "schema_profile.json", {})
    columns = profile["datasets"][0]["columns"]
    by_name = {column["name"]: column for column in columns}
    assert by_name["year"]["semantic_tags"] == ["time"]
    assert "target" in by_name["sales"]["semantic_tags"]
    assert "source_node" in by_name["origin"]["semantic_tags"]
    assert "target_node" in by_name["destination"]["semantic_tags"]
    assert "cost" in by_name["distance"]["semantic_tags"]
    assert by_name["sales"]["missing_rate"] == 0.5


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
    assert (workspace.root / "code" / "experiments" / "problem1.py").exists()
    assert (workspace.root / "results" / "problem1_results.csv").exists()
    assert "row_count" in metrics
    assert any(item["source_path"] == "results/model_metrics.json" for item in evidence)


def test_classification_solver_module_returns_metrics() -> None:
    import pandas as pd

    from mcm_agent.solver_modules.classification import logistic_regression_baseline

    frame = pd.DataFrame(
        {
            "feature_a": [0, 1, 2, 3, 4, 5],
            "feature_b": [0, 1, 1, 2, 2, 3],
            "risk_label": [0, 0, 0, 1, 1, 1],
        }
    )

    predictions, metrics = logistic_regression_baseline(
        frame,
        feature_columns=["feature_a", "feature_b"],
        label_column="risk_label",
    )

    assert "predicted_label" in predictions.columns
    assert metrics["classification_accuracy"] >= 0.5


def test_clustering_solver_module_returns_segments() -> None:
    import pandas as pd

    from mcm_agent.solver_modules.clustering import kmeans_segmentation

    frame = pd.DataFrame({"x": [0, 0.1, 8, 8.2], "y": [0, 0.2, 8, 8.1]})

    segments, metrics = kmeans_segmentation(frame, feature_columns=["x", "y"], n_clusters=2)

    assert "cluster_id" in segments.columns
    assert metrics["cluster_count"] == 2


def test_queuing_solver_module_returns_service_metrics() -> None:
    import pandas as pd

    from mcm_agent.solver_modules.queuing import mmc_queue_summary

    frame = pd.DataFrame(
        {"arrival_rate": [2.0, 2.2], "service_rate": [3.0, 3.1], "servers": [2, 2]}
    )

    summary, metrics = mmc_queue_summary(
        frame,
        arrival_rate_column="arrival_rate",
        service_rate_column="service_rate",
        server_count_column="servers",
    )

    assert "utilization" in summary.columns
    assert metrics["queue_utilization"] < 1


def test_solver_binds_outputs_to_selected_model_routes(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    processed = workspace.root / "data" / "processed" / "sample.csv"
    processed.parent.mkdir(parents=True, exist_ok=True)
    processed.write_text("district,priority,budget\nA,0.8,10\nB,0.4,6\n", encoding="utf-8")
    (workspace.root / "reports" / "model_decision.md").write_text(
        "\n".join(
            [
                "# Model Decision",
                "",
                "## Selected Route",
                "multi_criteria_evaluation + constrained_optimization. Weighted score: 8.60.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    SolverCoderAgent().run(workspace.root)

    route_summary = read_json(workspace.root / "results" / "model_route_summary.json", {})
    evidence = read_json(workspace.root / "results" / "evidence_registry.json", [])
    assert route_summary["selected_routes"] == [
        "multi_criteria_evaluation",
        "constrained_optimization",
    ]
    assert route_summary["solver_modules"][0]["method"] == "entropy_weighted_topsis"
    assert "priority_score_mean" in route_summary["route_metrics"]
    assert "allocation_capacity_total" in route_summary["route_metrics"]
    assert any(
        item["evidence_id"] == "metric_priority_score_mean"
        and item["used_in"] == ["multi_criteria_evaluation"]
        for item in evidence
    )


def test_solver_generates_route_specific_evaluation_and_allocation_columns(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    processed = workspace.root / "data" / "processed" / "sample.csv"
    processed.parent.mkdir(parents=True, exist_ok=True)
    processed.write_text("district,risk,exposure,budget\nA,9,5,10\nB,2,8,6\n", encoding="utf-8")
    (workspace.root / "reports" / "model_decision.md").write_text(
        "\n".join(
            [
                "# Model Decision",
                "",
                "## Selected Route",
                "multi_criteria_evaluation + constrained_optimization. Weighted score: 8.60.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    SolverCoderAgent().run(workspace.root)

    result = (workspace.root / "results" / "problem1_results.csv").read_text(encoding="utf-8")
    route_summary = read_json(workspace.root / "results" / "model_route_summary.json", {})
    assert "priority_score" in result
    assert "priority_rank" in result
    assert "recommended_allocation" in result
    assert "top_priority_entity" in route_summary["route_metrics"]
    assert route_summary["route_metrics"]["top_priority_entity"]["value"] == "A"


def test_solver_generated_script_uses_reusable_solver_modules(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    processed = workspace.root / "data" / "processed" / "sample.csv"
    processed.parent.mkdir(parents=True, exist_ok=True)
    processed.write_text("district,risk,exposure,budget\nA,9,5,10\nB,2,8,6\n", encoding="utf-8")
    (workspace.root / "reports" / "model_decision.md").write_text(
        "# Model Decision\n\n## Selected Route\nmulti_criteria_evaluation + constrained_optimization.",
        encoding="utf-8",
    )

    SolverCoderAgent().run(workspace.root)

    script = (workspace.root / "code" / "experiments" / "problem1.py").read_text(
        encoding="utf-8"
    )
    assert "mcm_agent.solver_modules.evaluation" in script
    assert "mcm_agent.solver_modules.optimization" in script


def test_solver_runs_forecasting_simulation_and_network_modules(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    processed = workspace.root / "data" / "processed" / "sample.csv"
    processed.parent.mkdir(parents=True, exist_ok=True)
    processed.write_text(
        "source,target,cost,period,demand\nA,B,1,1,10\nB,C,2,2,12\nA,C,5,3,14\n",
        encoding="utf-8",
    )
    (workspace.root / "reports" / "model_decision.md").write_text(
        "\n".join(
            [
                "# Model Decision",
                "",
                "## Selected Route",
                "forecasting_model + monte_carlo_simulation + network_flow_graph.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    SolverCoderAgent().run(workspace.root)

    summary = read_json(workspace.root / "results" / "model_route_summary.json", {})
    evidence = read_json(workspace.root / "results" / "evidence_registry.json", [])
    assert (workspace.root / "results" / "forecast_results.csv").exists()
    assert (workspace.root / "results" / "simulation_summary.json").exists()
    assert (workspace.root / "results" / "network_paths.csv").exists()
    assert "forecast_training_mae" in summary["route_metrics"]
    assert "simulation_p95" in summary["route_metrics"]
    assert "shortest_path_cost" in summary["route_metrics"]
    assert any(item["evidence_id"] == "metric_shortest_path_cost" for item in evidence)


def test_solver_records_route_execution_status_for_hybrid_specs(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    processed = workspace.root / "data" / "processed" / "sample.csv"
    processed.parent.mkdir(parents=True, exist_ok=True)
    processed.write_text(
        "district,risk,exposure,budget,period,demand\nA,9,5,10,1,10\nB,2,8,6,2,12\n",
        encoding="utf-8",
    )
    (workspace.root / "reports" / "experiment_spec.json").write_text(
        build_experiment_spec(
            [
                "multi_criteria_evaluation",
                "constrained_optimization",
                "forecasting_model",
                "monte_carlo_simulation",
            ]
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )

    SolverCoderAgent().run(workspace.root)

    summary = read_json(workspace.root / "results" / "model_route_summary.json", {})
    status = summary["route_execution_status"]
    assert status["multi_criteria_evaluation"] == "executed"
    assert status["constrained_optimization"] == "executed"
    assert status["forecasting_model"] == "executed"
    assert status["monte_carlo_simulation"] == "executed"
