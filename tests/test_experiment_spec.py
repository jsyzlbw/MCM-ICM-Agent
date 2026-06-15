from pathlib import Path

from mcm_agent.agents.modeling import ModelJudge
from mcm_agent.agents.solver import SolverCoderAgent
from mcm_agent.core.experiment_spec import build_experiment_spec
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json


def test_model_judge_writes_machine_readable_experiment_spec(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    candidates = workspace.root / "reports" / "model_candidates.md"
    candidates.write_text(
        "\n".join(
            [
                "# Model Candidates",
                "",
                "## Problem Type Diagnosis",
                "- Primary problem types: evaluation, optimization",
                "",
                "| Route ID | Candidate | Main Strength |",
                "|---|---|---|",
                "| multi_criteria_evaluation | Entropy-TOPSIS priority scoring | transparent ranking |",
                "| constrained_optimization | Resource allocation model | budget-aware policy |",
            ]
        ),
        encoding="utf-8",
    )

    ModelJudge().run(workspace.root, candidates)

    spec = read_json(workspace.root / "reports" / "experiment_spec.json", {})
    route_ids = [item["route_id"] for item in spec["experiments"]]
    assert spec["version"] == 1
    assert route_ids == ["multi_criteria_evaluation", "constrained_optimization"]
    assert spec["experiments"][0]["solver_module"] == "mcm_agent.solver_modules.evaluation"
    assert spec["experiments"][0]["method"] == "entropy_weighted_topsis"
    assert "results/problem1_results.csv" in spec["experiments"][0]["expected_outputs"]


def test_model_judge_experiment_spec_matches_selected_fallback_routes(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    candidates = workspace.root / "reports" / "model_candidates.md"
    candidates.write_text(
        "\n".join(
            [
                "# Model Candidates",
                "",
                "| Route ID | Candidate | Main Strength |",
                "|---|---|---|",
                "| multi_criteria_evaluation | Entropy-TOPSIS priority scoring | transparent ranking |",
                "| constrained_optimization | Resource allocation model | budget-aware policy |",
                "| network_flow_graph | Network route model | graph analysis |",
            ]
        ),
        encoding="utf-8",
    )

    ModelJudge().run(workspace.root, candidates)

    decision = (workspace.root / "reports" / "model_decision.md").read_text(encoding="utf-8")
    spec = read_json(workspace.root / "reports" / "experiment_spec.json", {})
    route_ids = [item["route_id"] for item in spec["experiments"]]
    assert "multi_criteria_evaluation + constrained_optimization" in decision
    assert route_ids == ["multi_criteria_evaluation", "constrained_optimization"]


def test_solver_prefers_experiment_spec_over_markdown_route_detection(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    processed = workspace.root / "data" / "processed" / "sample.csv"
    processed.parent.mkdir(parents=True, exist_ok=True)
    processed.write_text("district,risk,exposure,budget\nA,9,5,10\nB,2,8,6\n", encoding="utf-8")
    (workspace.root / "reports" / "model_decision.md").write_text(
        "# Model Decision\n\n## Selected Route\nBalanced contest-paper route.",
        encoding="utf-8",
    )
    (workspace.root / "reports" / "experiment_spec.json").write_text(
        """
{
  "version": 1,
  "experiments": [
    {
      "route_id": "multi_criteria_evaluation",
      "solver_module": "mcm_agent.solver_modules.evaluation",
      "method": "entropy_weighted_topsis",
      "input_requirements": ["numeric indicators"],
      "expected_outputs": ["results/problem1_results.csv"],
      "metrics": ["priority_score_mean"]
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    SolverCoderAgent().run(workspace.root)

    result = (workspace.root / "results" / "problem1_results.csv").read_text(encoding="utf-8")
    summary = read_json(workspace.root / "results" / "model_route_summary.json", {})
    assert "priority_score" in result
    assert summary["selected_routes"] == ["multi_criteria_evaluation"]


def test_experiment_spec_includes_column_binding_contract() -> None:
    spec = build_experiment_spec(["forecasting_model", "network_flow_graph"])

    forecast = spec.experiments[0]
    network = spec.experiments[1]
    assert forecast.column_bindings == {"time_column": "", "target_column": ""}
    assert network.column_bindings == {
        "source_column": "",
        "target_column": "",
        "cost_column": "",
    }


def test_experiment_spec_records_hybrid_route_metadata() -> None:
    spec = build_experiment_spec(
        ["multi_criteria_evaluation", "constrained_optimization", "forecasting_model"]
    )

    assert spec.route_plan["is_hybrid"] is True
    assert spec.route_plan["execution_order"] == [
        "multi_criteria_evaluation",
        "constrained_optimization",
        "forecasting_model",
    ]
    assert spec.experiments[1].role == "decision"


def test_solver_records_inferred_column_bindings_in_route_summary(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    processed = workspace.root / "data" / "processed" / "sample.csv"
    processed.parent.mkdir(parents=True, exist_ok=True)
    processed.write_text(
        "origin,destination,distance,year,sales\nA,B,1,2021,10\nB,C,2,2022,12\nA,C,5,2023,14\n",
        encoding="utf-8",
    )
    (workspace.root / "reports" / "experiment_spec.json").write_text(
        """
{
  "version": 1,
  "experiments": [
    {
      "route_id": "forecasting_model",
      "solver_module": "mcm_agent.solver_modules.forecasting",
      "method": "linear_trend_forecast",
      "input_requirements": ["time column", "target numeric column"],
      "expected_outputs": ["results/forecast_results.csv"],
      "metrics": ["forecast_training_mae"],
      "column_bindings": {
        "time_column": "year",
        "target_column": "sales"
      }
    },
    {
      "route_id": "network_flow_graph",
      "solver_module": "mcm_agent.solver_modules.network",
      "method": "shortest_path_table",
      "input_requirements": ["source column", "target column", "cost column"],
      "expected_outputs": ["results/network_paths.csv"],
      "metrics": ["shortest_path_cost"],
      "column_bindings": {
        "source_column": "origin",
        "target_column": "destination",
        "cost_column": "distance"
      }
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    SolverCoderAgent().run(workspace.root)

    summary = read_json(workspace.root / "results" / "model_route_summary.json", {})
    bindings = summary["column_bindings"]
    assert bindings["forecasting_model"]["time_column"] == "year"
    assert bindings["forecasting_model"]["target_column"] == "sales"
    assert bindings["network_flow_graph"]["source_column"] == "origin"
    assert bindings["network_flow_graph"]["cost_column"] == "distance"
    assert (workspace.root / "results" / "forecast_results.csv").exists()
    assert (workspace.root / "results" / "network_paths.csv").exists()


def test_solver_uses_schema_profile_semantic_tags_for_column_bindings(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    processed = workspace.root / "data" / "processed" / "sample.csv"
    processed.parent.mkdir(parents=True, exist_ok=True)
    processed.write_text(
        "a,b,c,d,e\nA,B,1,2021,10\nB,C,2,2022,12\nA,C,5,2023,14\n",
        encoding="utf-8",
    )
    (workspace.root / "results" / "schema_profile.json").write_text(
        """
{
  "datasets": [
    {
      "file": "data/processed/sample.csv",
      "columns": [
        {"name": "a", "semantic_tags": ["source_node"]},
        {"name": "b", "semantic_tags": ["target_node"]},
        {"name": "c", "semantic_tags": ["cost"]},
        {"name": "d", "semantic_tags": ["time"]},
        {"name": "e", "semantic_tags": ["target"]}
      ]
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )
    (workspace.root / "reports" / "experiment_spec.json").write_text(
        """
{
  "version": 1,
  "experiments": [
    {
      "route_id": "forecasting_model",
      "solver_module": "mcm_agent.solver_modules.forecasting",
      "method": "linear_trend_forecast",
      "input_requirements": ["time column", "target numeric column"],
      "expected_outputs": ["results/forecast_results.csv"],
      "metrics": ["forecast_training_mae"],
      "column_bindings": {"time_column": "", "target_column": ""}
    },
    {
      "route_id": "network_flow_graph",
      "solver_module": "mcm_agent.solver_modules.network",
      "method": "shortest_path_table",
      "input_requirements": ["source column", "target column", "cost column"],
      "expected_outputs": ["results/network_paths.csv"],
      "metrics": ["shortest_path_cost"],
      "column_bindings": {"source_column": "", "target_column": "", "cost_column": ""}
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    SolverCoderAgent().run(workspace.root)

    summary = read_json(workspace.root / "results" / "model_route_summary.json", {})
    assert summary["column_bindings"]["forecasting_model"]["time_column"] == "d"
    assert summary["column_bindings"]["forecasting_model"]["target_column"] == "e"
    assert summary["column_bindings"]["network_flow_graph"]["source_column"] == "a"
    assert summary["column_bindings"]["network_flow_graph"]["target_column"] == "b"
    assert summary["column_bindings"]["network_flow_graph"]["cost_column"] == "c"


def test_solver_writes_binding_report_when_required_columns_are_missing(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    processed = workspace.root / "data" / "processed" / "sample.csv"
    processed.parent.mkdir(parents=True, exist_ok=True)
    processed.write_text("x,y\n1,2\n2,3\n", encoding="utf-8")
    (workspace.root / "reports" / "experiment_spec.json").write_text(
        """
{
  "version": 1,
  "experiments": [
    {
      "route_id": "network_flow_graph",
      "solver_module": "mcm_agent.solver_modules.network",
      "method": "shortest_path_table",
      "input_requirements": ["source column", "target column", "cost column"],
      "expected_outputs": ["results/network_paths.csv"],
      "metrics": ["shortest_path_cost"],
      "column_bindings": {"source_column": "", "target_column": "", "cost_column": ""}
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    SolverCoderAgent().run(workspace.root)

    binding_report = read_json(workspace.root / "results" / "solver_binding_report.json", {})
    assert binding_report["status"] == "fail"
    assert "network_flow_graph.source_column" in binding_report["missing_bindings"]
    assert "network_flow_graph.target_column" in binding_report["missing_bindings"]
    assert "network_flow_graph.cost_column" in binding_report["missing_bindings"]
