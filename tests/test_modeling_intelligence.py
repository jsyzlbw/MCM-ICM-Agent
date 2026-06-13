from pathlib import Path

from mcm_agent.agents.modeling import ModelJudge, ModelingCouncil
from mcm_agent.core.modeling_intelligence import ModelingIntelligence
from mcm_agent.core.workspace import create_workspace


def test_modeling_intelligence_detects_evaluation_and_optimization_route() -> None:
    diagnosis = ModelingIntelligence().diagnose(
        "Rank city districts with a priority score and recommend limited resource allocation."
    )

    route_ids = [route.route_id for route in diagnosis.routes]
    assert diagnosis.primary_problem_types[:2] == ["evaluation", "optimization"]
    assert "multi_criteria_evaluation" in route_ids
    assert "constrained_optimization" in route_ids


def test_modeling_intelligence_detects_forecasting_and_simulation_route() -> None:
    diagnosis = ModelingIntelligence().diagnose(
        "Forecast monthly demand under uncertainty and simulate several policy scenarios."
    )

    route_ids = [route.route_id for route in diagnosis.routes]
    assert "prediction" in diagnosis.primary_problem_types
    assert "simulation" in diagnosis.primary_problem_types
    assert "forecasting_model" in route_ids
    assert "monte_carlo_simulation" in route_ids


def test_modeling_intelligence_detects_graph_route() -> None:
    diagnosis = ModelingIntelligence().diagnose(
        "Design an evacuation network and find shortest paths across blocked roads."
    )

    route_ids = [route.route_id for route in diagnosis.routes]
    assert diagnosis.primary_problem_types[0] == "graph_network"
    assert "network_flow_graph" in route_ids


def test_modeling_council_fallback_includes_problem_type_diagnosis(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    problem_report = workspace.root / "reports" / "problem_understanding.md"
    direction = workspace.root / "discussion" / "confirmed_direction.md"
    problem_report.write_text(
        "# 题意理解报告\n\nRank districts and optimize limited emergency resources.",
        encoding="utf-8",
    )
    direction.parent.mkdir(parents=True, exist_ok=True)
    direction.write_text("# Confirmed Direction\nUse interpretable ranking.", encoding="utf-8")

    ModelingCouncil().run(workspace.root, problem_report, direction)

    content = (workspace.root / "reports" / "model_candidates.md").read_text(encoding="utf-8")
    assert "## Problem Type Diagnosis" in content
    assert "multi_criteria_evaluation" in content
    assert "constrained_optimization" in content


def test_model_judge_fallback_selects_diagnosed_route(tmp_path: Path) -> None:
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
                "## Candidate Summary Table",
                "| Route ID | Candidate | Main Strength |",
                "|---|---|---|",
                "| multi_criteria_evaluation | Entropy-TOPSIS priority scoring | transparent ranking |",
                "| constrained_optimization | Resource allocation model | budget-aware policy |",
                "",
            ]
        ),
        encoding="utf-8",
    )

    ModelJudge().run(workspace.root, candidates)

    decision = (workspace.root / "reports" / "model_decision.md").read_text(encoding="utf-8")
    assert "multi_criteria_evaluation + constrained_optimization" in decision
