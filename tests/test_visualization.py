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
