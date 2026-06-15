from pathlib import Path

from mcm_agent.agents.modeling_quality import ModelingPlanQualityAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json
from mcm_agent.utils.json_io import write_json


def test_modeling_quality_gate_fails_when_required_route_data_is_unavailable(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "problem_understanding.md").write_text(
        "# Problem Understanding\n\n## Subtasks\n- Forecast future demand.\n",
        encoding="utf-8",
    )
    (workspace.root / "reports" / "model_decision.md").write_text(
        "# Model Decision\n\n## Selected Route\nforecasting_model.\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "reports" / "experiment_spec.json",
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
                    "column_bindings": {"time_column": "", "target_column": ""},
                }
            ],
        },
    )
    write_json(
        workspace.root / "data" / "data_feasibility_matrix.json",
        [
            {
                "need_id": "need_001",
                "target_dataset": "historical demand time series",
                "availability": "unknown",
                "confidence": 0.55,
                "proxy_variables": [],
            }
        ],
    )

    ModelingPlanQualityAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "modeling_gate.json", {})
    report = (workspace.root / "reports" / "modeling_quality_report.md").read_text(
        encoding="utf-8"
    )
    assert gate["status"] == "fail"
    assert gate["failure_reason"] == "weak_model"
    assert gate["repair_stage"] == "modeling_council"
    assert "forecasting_model.time_column" in gate["blocking_findings"][0]
    assert "historical demand time series" in report


def test_modeling_quality_gate_passes_with_proxy_reframing_and_experiment_metrics(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "problem_understanding.md").write_text(
        "# Problem Understanding\n\n## Subtasks\n- Design a fair compensation policy.\n",
        encoding="utf-8",
    )
    (workspace.root / "reports" / "model_decision.md").write_text(
        "# Model Decision\n\n## Selected Route\nmulti_criteria_evaluation.\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "reports" / "experiment_spec.json",
        {
            "version": 1,
            "experiments": [
                {
                    "route_id": "multi_criteria_evaluation",
                    "solver_module": "mcm_agent.solver_modules.evaluation",
                    "method": "entropy_weighted_topsis",
                    "input_requirements": ["numeric indicators"],
                    "expected_outputs": ["results/problem1_results.csv"],
                    "metrics": ["priority_score_mean"],
                    "column_bindings": {"indicator_columns": "proxy indicators"},
                }
            ],
        },
    )
    write_json(
        workspace.root / "discussion" / "direction_lock.json",
        {
            "status": "locked",
            "selected_route": "Compensation proxy route",
            "new_data_needs": [],
            "requires_data_scout": False,
            "adopted_reframing_strategy": "proxy_modeling",
            "adopted_reframing_option_id": "need_001:proxy_modeling",
        },
    )

    ModelingPlanQualityAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "modeling_gate.json", {})
    assert gate["status"] == "pass"


def test_modeling_quality_gate_allows_unknown_data_when_attachment_exists(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    attachment = workspace.root / "input" / "attachments" / "data.csv"
    attachment.parent.mkdir(parents=True, exist_ok=True)
    attachment.write_text("x,y\n1,2\n", encoding="utf-8")
    (workspace.root / "reports" / "model_decision.md").write_text(
        "# Model Decision\n\n## Selected Route\nmulti_criteria_evaluation.\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "reports" / "experiment_spec.json",
        {
            "version": 1,
            "experiments": [
                {
                    "route_id": "multi_criteria_evaluation",
                    "solver_module": "mcm_agent.solver_modules.evaluation",
                    "method": "entropy_weighted_topsis",
                    "input_requirements": ["numeric indicators"],
                    "expected_outputs": ["results/problem1_results.csv"],
                    "metrics": ["priority_score_mean"],
                    "column_bindings": {"indicator_columns": ""},
                }
            ],
        },
    )
    write_json(
        workspace.root / "data" / "data_feasibility_matrix.json",
        [
            {
                "need_id": "need_001",
                "target_dataset": "public population data",
                "availability": "unknown",
                "confidence": 0.55,
                "proxy_variables": [],
            }
        ],
    )

    ModelingPlanQualityAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "modeling_gate.json", {})
    assert gate["status"] == "pass"


def test_modeling_quality_gate_allows_required_bindings_when_attachment_can_be_profiled(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    attachment = workspace.root / "input" / "attachments" / "network_demand.csv"
    attachment.parent.mkdir(parents=True, exist_ok=True)
    attachment.write_text(
        "source,target,cost,period,demand\nA,B,1,1,10\nB,C,2,2,12\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "reports" / "experiment_spec.json",
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
                    "column_bindings": {"time_column": "", "target_column": ""},
                },
                {
                    "route_id": "network_flow_graph",
                    "solver_module": "mcm_agent.solver_modules.network",
                    "method": "shortest_path_table",
                    "input_requirements": ["source column", "target column", "cost column"],
                    "expected_outputs": ["results/network_paths.csv"],
                    "metrics": ["shortest_path_cost"],
                    "column_bindings": {
                        "source_column": "",
                        "target_column": "",
                        "cost_column": "",
                    },
                },
            ],
        },
    )

    ModelingPlanQualityAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "modeling_gate.json", {})
    assert gate["status"] == "pass"
