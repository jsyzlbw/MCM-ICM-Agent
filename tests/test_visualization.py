from pathlib import Path

from mcm_agent.agents.visualization import FigurePlanningAgent, VisualizationAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json, write_json


def test_figure_planning_agent_creates_data_and_concept_items(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "model_decision.md").write_text("# Model Decision", encoding="utf-8")
    (workspace.root / "reports" / "experiment_plan.md").write_text("# Experiment Plan", encoding="utf-8")
    (workspace.root / "reports" / "validation_report.md").write_text(
        "# Validation Report", encoding="utf-8"
    )
    write_json(workspace.root / "results" / "evidence_registry.json", [])
    (workspace.root / "results" / "problem1_results.csv").write_text(
        "x,y\n1,2\n2,4\n3,6\n", encoding="utf-8"
    )

    FigurePlanningAgent().run(workspace.root)

    plan = read_json(workspace.root / "figures" / "figure_plan.json", [])
    assert {item["figure_type"] for item in plan} == {"data_plot", "concept_diagram"}
    assert {"pdf", "svg"}.intersection(plan[0]["output_formats"])


def test_visualization_agent_renders_registry_outputs(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "results" / "problem1_results.csv").write_text(
        "x,y\n1,2\n2,4\n3,6\n", encoding="utf-8"
    )
    FigurePlanningAgent().run(workspace.root)

    VisualizationAgent().run(workspace.root)

    registry = read_json(workspace.root / "figures" / "figure_registry.json", [])
    assert (workspace.root / "figures" / "fig_q1_prediction.pdf").exists()
    assert (workspace.root / "figures" / "fig_q1_prediction.svg").exists()
    assert (workspace.root / "figures" / "source" / "fig_framework.mmd").exists()
    assert any(item["figure_id"] == "fig_framework" for item in registry)


def test_figure_planning_uses_selected_model_routes(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {
            "selected_routes": ["multi_criteria_evaluation", "constrained_optimization"],
            "route_metrics": {
                "priority_score_mean": {
                    "route_id": "multi_criteria_evaluation",
                    "value": 0.6,
                }
            },
        },
    )
    write_json(workspace.root / "results" / "evidence_registry.json", [])
    (workspace.root / "results" / "problem1_results.csv").write_text(
        "district,priority,budget\nA,0.8,10\nB,0.4,6\n", encoding="utf-8"
    )

    FigurePlanningAgent().run(workspace.root)

    plan = read_json(workspace.root / "figures" / "figure_plan.json", [])
    figure_ids = [item["figure_id"] for item in plan]
    assert "fig_priority_ranking" in figure_ids
    assert "fig_allocation_policy" in figure_ids
    assert "fig_q1_prediction" not in figure_ids


def test_concept_diagram_builder_uses_routes_claims_and_sources(tmp_path: Path) -> None:
    from mcm_agent.core.concept_diagrams import build_concept_diagram_specs

    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {
            "selected_routes": ["classification_model", "queuing_service_model"],
            "route_metrics": {
                "queue_utilization": {
                    "route_id": "queuing_service_model",
                    "value": 0.35,
                }
            },
        },
    )
    write_json(
        workspace.root / "paper" / "claim_plan.json",
        [
            {
                "claim_id": "claim_model_route",
                "section": "paper/sections/model.tex",
                "claim_text": "The selected route is classification plus queueing.",
                "claim_type": "model_choice",
                "evidence_ids": ["metric_queue_utilization"],
                "figure_ids": [],
                "source_ids": ["source_001"],
                "priority": "critical",
            }
        ],
    )

    specs = build_concept_diagram_specs(workspace.root)

    spec_by_id = {spec.diagram_id: spec for spec in specs}
    assert "fig_method_overview" in spec_by_id
    assert "fig_claim_evidence_map" in spec_by_id
    method = spec_by_id["fig_method_overview"]
    assert any(node.label == "classification_model" for node in method.nodes)
    assert any(node.label == "queuing_service_model" for node in method.nodes)
    claim_map = spec_by_id["fig_claim_evidence_map"]
    assert any("claim_model_route" in node.label for node in claim_map.nodes)
