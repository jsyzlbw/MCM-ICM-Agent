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
    assert (workspace.root / "figures" / "source" / "fig_method_overview.mmd").exists()
    assert any(item["figure_id"] == "fig_method_overview" for item in registry)


def test_visualization_skips_unplottable_source_without_crashing(tmp_path: Path) -> None:
    """A result table with no numeric columns (e.g. a text-only pairing assignment)
    must not crash the visualization stage — the data_plot is skipped, the pipeline
    proceeds (best-effort). Regression for the DWTS run-5 hard crash."""
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "results" / "problem1_results.csv").write_text(
        "celebrity_name,professional_name\nCorey,Brandon\nDanielle,Alan\n", encoding="utf-8"
    )
    FigurePlanningAgent().run(workspace.root)

    # Must NOT raise.
    VisualizationAgent().run(workspace.root)

    registry = read_json(workspace.root / "figures" / "figure_registry.json", [])
    # The un-plottable data_plot is skipped...
    assert not (workspace.root / "figures" / "fig_q1_prediction.pdf").exists()
    assert all(item["figure_id"] != "fig_q1_prediction" for item in registry)
    # ...but concept diagrams still render and the stage completes.
    assert any(item["figure_id"] == "fig_method_overview" for item in registry)


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


def test_figure_planning_adds_method_and_claim_concept_diagrams(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {"selected_routes": ["classification_model"], "route_metrics": {}},
    )
    write_json(workspace.root / "results" / "evidence_registry.json", [])
    write_json(
        workspace.root / "paper" / "claim_plan.json",
        [
            {
                "claim_id": "claim_model_route",
                "section": "paper/sections/model.tex",
                "claim_text": "The selected model is classification.",
                "claim_type": "model_choice",
                "evidence_ids": [],
                "figure_ids": [],
                "source_ids": [],
                "priority": "critical",
                "status": "unresolved",
                "unresolved_reason": "test unresolved claim",
            }
        ],
    )
    (workspace.root / "results" / "problem1_results.csv").write_text(
        "x,y\n1,2\n2,4\n",
        encoding="utf-8",
    )

    FigurePlanningAgent().run(workspace.root)

    plan = read_json(workspace.root / "figures" / "figure_plan.json", [])
    by_id = {item["figure_id"]: item for item in plan}
    assert by_id["fig_method_overview"]["figure_type"] == "concept_diagram"
    assert by_id["fig_claim_evidence_map"]["target_section"] == "paper/sections/model.tex"
    assert "svg" in by_id["fig_method_overview"]["output_formats"]


def test_visualization_agent_renders_concept_diagram_mermaid_and_svg(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {
            "selected_routes": ["classification_model", "queuing_service_model"],
            "route_metrics": {},
        },
    )
    write_json(workspace.root / "results" / "evidence_registry.json", [])
    (workspace.root / "results" / "problem1_results.csv").write_text(
        "x,y\n1,2\n2,4\n",
        encoding="utf-8",
    )
    FigurePlanningAgent().run(workspace.root)

    VisualizationAgent().run(workspace.root)

    mermaid = workspace.root / "figures" / "source" / "fig_method_overview.mmd"
    svg = workspace.root / "figures" / "fig_method_overview.svg"
    registry = read_json(workspace.root / "figures" / "figure_registry.json", [])
    method_record = next(item for item in registry if item["figure_id"] == "fig_method_overview")
    assert mermaid.exists()
    assert svg.exists()
    assert "classification_model" in mermaid.read_text(encoding="utf-8")
    assert "<svg" in svg.read_text(encoding="utf-8")
    assert "figures/fig_method_overview.svg" in method_record["outputs"]
    assert method_record["status"] == "approved"


def _make_concept_diagram_workspace(tmp_path: Path):
    """Shared setup for concept-diagram PDF tests."""
    from mcm_agent.core.workspace import create_workspace

    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {
            "selected_routes": ["classification_model"],
            "route_metrics": {},
        },
    )
    write_json(workspace.root / "results" / "evidence_registry.json", [])
    (workspace.root / "results" / "problem1_results.csv").write_text(
        "x,y\n1,2\n2,4\n",
        encoding="utf-8",
    )
    return workspace


def test_concept_diagram_renders_pdf(tmp_path: Path) -> None:
    """FIG1: after VisualizationAgent.run, figures/fig_method_overview.pdf must
    exist on disk AND the registry outputs list must have it first."""
    workspace = _make_concept_diagram_workspace(tmp_path)
    FigurePlanningAgent().run(workspace.root)

    VisualizationAgent().run(workspace.root)

    pdf_path = workspace.root / "figures" / "fig_method_overview.pdf"
    assert pdf_path.exists(), "Expected figures/fig_method_overview.pdf to be created by matplotlib"

    registry = read_json(workspace.root / "figures" / "figure_registry.json", [])
    method_record = next(
        (item for item in registry if item["figure_id"] == "fig_method_overview"), None
    )
    assert method_record is not None, "fig_method_overview not found in registry"
    assert any(out.endswith(".pdf") for out in method_record["outputs"]), (
        f"No .pdf in registry outputs: {method_record['outputs']}"
    )
    assert method_record["outputs"][0].endswith(".pdf"), (
        f"First output must be .pdf (for _best_output preference), got: {method_record['outputs']}"
    )


def test_concept_diagram_embeds_in_paper(tmp_path: Path) -> None:
    """FIG1: after visualization + writer, the concept diagram's target section
    must contain \\includegraphics referencing fig_method_overview."""
    from mcm_agent.agents.writer import PaperWriterAgent

    workspace = _make_concept_diagram_workspace(tmp_path)
    FigurePlanningAgent().run(workspace.root)
    VisualizationAgent().run(workspace.root)

    # Confirm registry has .pdf first (so _best_output will pick it)
    registry = read_json(workspace.root / "figures" / "figure_registry.json", [])
    method_record = next(
        (item for item in registry if item["figure_id"] == "fig_method_overview"), None
    )
    assert method_record is not None
    assert method_record["outputs"][0].endswith(".pdf"), (
        "_best_output won't pick .pdf unless it is first in outputs"
    )

    PaperWriterAgent().run(workspace.root)

    # The target_section for fig_method_overview is paper/sections/model.tex
    target_tex = workspace.root / "paper" / "sections" / "model.tex"
    assert target_tex.exists(), "Expected model.tex to be written by PaperWriterAgent"
    content = target_tex.read_text(encoding="utf-8")
    assert "\\includegraphics" in content, (
        "Expected \\includegraphics in model.tex but found none.\n"
        f"model.tex content:\n{content}"
    )
    assert "fig_method_overview" in content, (
        "Expected figure id 'fig_method_overview' in model.tex.\n"
        f"model.tex content:\n{content}"
    )
