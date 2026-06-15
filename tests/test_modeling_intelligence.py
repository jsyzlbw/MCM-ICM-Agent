from pathlib import Path

from mcm_agent.agents.modeling import ModelJudge, ModelingCouncil
from mcm_agent.core.model_route_plan import build_route_plan
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


def test_modeling_intelligence_detects_classification_clustering_and_queuing() -> None:
    diagnosis = ModelingIntelligence().diagnose(
        "Classify risk levels, cluster customer segments, and model queue waiting time with service counters."
    )

    route_ids = [route.route_id for route in diagnosis.routes]
    assert "classification" in diagnosis.primary_problem_types
    assert "clustering" in diagnosis.primary_problem_types
    assert "queuing" in diagnosis.primary_problem_types
    assert "classification_model" in route_ids
    assert "clustering_segmentation" in route_ids
    assert "queuing_service_model" in route_ids


def test_modeling_intelligence_does_not_match_graph_keywords_inside_other_words() -> None:
    diagnosis = ModelingIntelligence().diagnose(
        "Build a modeling workflow for flood response priority scoring and resource allocation."
    )

    route_ids = [route.route_id for route in diagnosis.routes]
    assert "network_flow_graph" not in route_ids
    assert "multi_criteria_evaluation" in route_ids
    assert "constrained_optimization" in route_ids


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


def test_modeling_council_fallback_includes_solver_blueprint(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    problem_report = workspace.root / "reports" / "problem_understanding.md"
    direction = workspace.root / "discussion" / "confirmed_direction.md"
    problem_report.write_text(
        "# Report\n\nClassify risk levels and cluster customer groups.",
        encoding="utf-8",
    )
    direction.parent.mkdir(parents=True, exist_ok=True)
    direction.write_text("# Direction\nUse interpretable model recipes.", encoding="utf-8")

    ModelingCouncil().run(workspace.root, problem_report, direction)

    content = (workspace.root / "reports" / "model_candidates.md").read_text(encoding="utf-8")
    assert "## Solver Blueprint" in content
    assert "classification_model" in content
    assert "clustering_segmentation" in content


def test_modeling_council_ignores_problem_understanding_boilerplate_for_diagnosis(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    problem_report = workspace.root / "reports" / "problem_understanding.md"
    direction = workspace.root / "discussion" / "confirmed_direction.md"
    problem_report.write_text(
        "\n".join(
            [
                "# 题意理解报告",
                "",
                "## 题目背景",
                "Forecast evacuation demand, simulate uncertainty, and route traffic through a network.",
                "",
                "## 子问题拆解",
                "- Separate prediction, evaluation, and optimization objectives when present.",
                "",
                "## 评价指标",
                "- Use task-specific predictive, optimization, or evaluation metrics.",
            ]
        ),
        encoding="utf-8",
    )
    direction.parent.mkdir(parents=True, exist_ok=True)
    direction.write_text("# Confirmed Direction\nBalanced contest-paper route.", encoding="utf-8")

    ModelingCouncil().run(workspace.root, problem_report, direction)

    content = (workspace.root / "reports" / "model_candidates.md").read_text(encoding="utf-8")
    assert "forecasting_model" in content
    assert "monte_carlo_simulation" in content
    assert "network_flow_graph" in content
    assert "constrained_optimization" not in content
    assert "multi_criteria_evaluation" not in content


def test_modeling_council_ignores_direction_boilerplate_for_diagnosis(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    problem_report = workspace.root / "reports" / "problem_understanding.md"
    direction = workspace.root / "discussion" / "confirmed_direction.md"
    problem_report.write_text(
        "\n".join(
            [
                "# 题意理解报告",
                "",
                "## 题目背景",
                "Use the injected provider.",
                "",
                "## 初步建模方向",
                "- Start with interpretable baselines, then add complexity only when supported.",
            ]
        ),
        encoding="utf-8",
    )
    direction.parent.mkdir(parents=True, exist_ok=True)
    direction.write_text(
        "\n".join(
            [
                "# Confirmed Direction",
                "## Selected Modeling Route",
                "Balanced contest-paper route.",
                "## Decisions To Preserve",
                "- Use vector-first figures.",
            ]
        ),
        encoding="utf-8",
    )

    ModelingCouncil().run(workspace.root, problem_report, direction)

    content = (workspace.root / "reports" / "model_candidates.md").read_text(encoding="utf-8")
    assert "multi_criteria_evaluation" in content
    assert "network_flow_graph" not in content
    assert "multi_objective_decision" not in content


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


def test_route_plan_marks_hybrid_models_for_multi_type_problems() -> None:
    diagnosis = ModelingIntelligence().diagnose(
        "Rank districts, optimize limited resources, forecast demand, and simulate uncertainty."
    )

    plan = build_route_plan(diagnosis)

    assert plan.is_hybrid is True
    assert plan.route_ids[:3] == [
        "multi_criteria_evaluation",
        "constrained_optimization",
        "forecasting_model",
    ]
    assert "monte_carlo_simulation" in plan.route_ids
    assert plan.execution_order[0] == "multi_criteria_evaluation"
    assert plan.route_roles["constrained_optimization"] == "decision"


def test_route_plan_limits_routes_to_keep_solver_feasible() -> None:
    diagnosis = ModelingIntelligence().diagnose(
        "Rank, optimize, forecast, simulate, design a network, and balance multi-objective tradeoffs."
    )

    plan = build_route_plan(diagnosis, max_routes=4)

    assert len(plan.route_ids) == 4
    assert plan.truncated is True
