from __future__ import annotations

from pydantic import BaseModel, Field


class ModelRecipe(BaseModel):
    problem_type: str
    route_id: str
    candidate: str
    main_strength: str
    data_needs: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    implementation_risk: str
    solver_module: str
    method: str
    role: str
    input_requirements: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    column_bindings: dict[str, str | list[str]] = Field(default_factory=dict)
    paper_guidance: list[str] = Field(default_factory=list)


MODEL_RECIPES: dict[str, ModelRecipe] = {
    "evaluation": ModelRecipe(
        problem_type="evaluation",
        route_id="multi_criteria_evaluation",
        candidate="Entropy-TOPSIS priority scoring",
        main_strength="Transparent ranking from normalized indicators",
        data_needs=["indicator table", "weights or entropy-derived weights"],
        methods=["normalization", "entropy weighting", "TOPSIS"],
        metrics=["priority_score_mean", "top_priority_entity"],
        implementation_risk="low",
        solver_module="mcm_agent.solver_modules.evaluation",
        method="entropy_weighted_topsis",
        role="screening",
        input_requirements=["numeric indicators", "optional entity column"],
        expected_outputs=["results/problem1_results.csv"],
        column_bindings={"entity_column": "", "indicator_columns": ""},
        paper_guidance=[
            "Explain indicator orientation and normalization before reporting rankings.",
            "Use sensitivity analysis to show rank stability.",
        ],
    ),
    "optimization": ModelRecipe(
        problem_type="optimization",
        route_id="constrained_optimization",
        candidate="Resource allocation optimization",
        main_strength="Turns model scores into budget-aware recommendations",
        data_needs=["resource limits", "priority scores", "capacity constraints"],
        methods=["linear programming", "integer allocation", "sensitivity analysis"],
        metrics=["allocation_capacity_total"],
        implementation_risk="medium",
        solver_module="mcm_agent.solver_modules.optimization",
        method="capacity_constrained_priority_allocation",
        role="decision",
        input_requirements=["priority score", "optional capacity or budget column"],
        expected_outputs=["results/problem1_results.csv"],
        column_bindings={"priority_column": "priority_score", "capacity_column": ""},
        paper_guidance=[
            "State objective, decision variables, and active constraints explicitly.",
            "Report tradeoffs when resource limits change.",
        ],
    ),
    "prediction": ModelRecipe(
        problem_type="prediction",
        route_id="forecasting_model",
        candidate="Interpretable forecasting baseline",
        main_strength="Forecasts future demand or risk with explainable features",
        data_needs=["historical observations", "time or feature columns"],
        methods=["linear regression", "random forest", "time-series baseline"],
        metrics=["forecast_training_mae", "forecast_training_rmse"],
        implementation_risk="medium",
        solver_module="mcm_agent.solver_modules.forecasting",
        method="linear_trend_forecast",
        role="prediction",
        input_requirements=["time column", "target numeric column"],
        expected_outputs=["results/forecast_results.csv"],
        column_bindings={"time_column": "", "target_column": ""},
        paper_guidance=[
            "Show training fit, forecast horizon, and uncertainty caveats.",
            "Avoid over-claiming accuracy when data history is short.",
        ],
    ),
    "simulation": ModelRecipe(
        problem_type="simulation",
        route_id="monte_carlo_simulation",
        candidate="Scenario and uncertainty simulation",
        main_strength="Tests robustness under uncertain assumptions",
        data_needs=["parameter ranges", "uncertainty assumptions"],
        methods=["Monte Carlo simulation", "scenario analysis"],
        metrics=["simulation_mean", "simulation_p95"],
        implementation_risk="medium",
        solver_module="mcm_agent.solver_modules.simulation",
        method="monte_carlo_scenarios",
        role="uncertainty",
        input_requirements=["base numeric value", "uncertainty assumption"],
        expected_outputs=["results/simulation_summary.json"],
        column_bindings={"base_value_column": ""},
        paper_guidance=[
            "Tie sampled assumptions to the problem statement or registered evidence.",
            "Report percentile outcomes, not only average outcomes.",
        ],
    ),
    "graph_network": ModelRecipe(
        problem_type="graph_network",
        route_id="network_flow_graph",
        candidate="Network flow or shortest-path model",
        main_strength="Captures routes, flows, connectivity, and bottlenecks",
        data_needs=["nodes", "edges", "capacities or travel costs"],
        methods=["shortest path", "max flow", "minimum cost flow"],
        metrics=["shortest_path_cost", "shortest_path_edge_count"],
        implementation_risk="medium",
        solver_module="mcm_agent.solver_modules.network",
        method="shortest_path_table",
        role="structure",
        input_requirements=["source column", "target column", "cost column"],
        expected_outputs=["results/network_paths.csv"],
        column_bindings={"source_column": "", "target_column": "", "cost_column": ""},
        paper_guidance=[
            "Define nodes, edges, and cost semantics before interpreting paths.",
            "Discuss bottlenecks and unreachable cases.",
        ],
    ),
    "multi_objective": ModelRecipe(
        problem_type="multi_objective",
        route_id="multi_objective_decision",
        candidate="Multi-objective trade-off model",
        main_strength="Makes conflicting goals and Pareto trade-offs explicit",
        data_needs=["objective definitions", "decision variables", "constraints"],
        methods=["weighted sum", "Pareto analysis", "goal programming"],
        metrics=["Pareto dominance", "weighted utility", "trade-off slope"],
        implementation_risk="medium",
        solver_module="mcm_agent.solver_modules.optimization",
        method="weighted_tradeoff_analysis",
        role="tradeoff",
        input_requirements=["objective columns", "decision variables"],
        expected_outputs=["results/problem1_results.csv"],
        column_bindings={"objective_columns": ""},
        paper_guidance=[
            "State why objectives conflict and how weights are chosen.",
            "Report at least one sensitivity check over objective weights.",
        ],
    ),
    "classification": ModelRecipe(
        problem_type="classification",
        route_id="classification_model",
        candidate="Interpretable classification baseline",
        main_strength="Predicts category or risk labels from measurable features",
        data_needs=["labeled examples", "numeric or encoded predictors", "label column"],
        methods=["logistic regression", "train/test split", "confusion analysis"],
        metrics=["classification_accuracy", "classification_f1"],
        implementation_risk="medium",
        solver_module="mcm_agent.solver_modules.classification",
        method="logistic_regression_baseline",
        role="prediction",
        input_requirements=["feature columns", "label column"],
        expected_outputs=["results/classification_results.csv"],
        column_bindings={"feature_columns": "", "label_column": ""},
        paper_guidance=[
            "Define class labels and discuss class imbalance before interpreting accuracy.",
            "Use classification results as decision support, not an unexplained black box.",
        ],
    ),
    "clustering": ModelRecipe(
        problem_type="clustering",
        route_id="clustering_segmentation",
        candidate="K-means segmentation baseline",
        main_strength="Finds interpretable groups or typologies in multivariate data",
        data_needs=["numeric feature columns", "meaningful entity rows"],
        methods=["standardization", "K-means", "silhouette analysis"],
        metrics=["cluster_count", "cluster_silhouette"],
        implementation_risk="medium",
        solver_module="mcm_agent.solver_modules.clustering",
        method="kmeans_segmentation",
        role="structure",
        input_requirements=["numeric feature columns"],
        expected_outputs=["results/cluster_segments.csv"],
        column_bindings={"feature_columns": "", "entity_column": ""},
        paper_guidance=[
            "Name clusters by their feature profiles rather than arbitrary IDs.",
            "Use clusters to simplify recommendations or scenario design.",
        ],
    ),
    "queuing": ModelRecipe(
        problem_type="queuing",
        route_id="queuing_service_model",
        candidate="Queueing service-system baseline",
        main_strength="Estimates utilization and waiting time under service capacity",
        data_needs=["arrival rate", "service rate", "server or counter count"],
        methods=["M/M/c queue", "utilization analysis", "capacity sensitivity"],
        metrics=["queue_utilization", "expected_wait_time"],
        implementation_risk="medium",
        solver_module="mcm_agent.solver_modules.queuing",
        method="mmc_queue_summary",
        role="service",
        input_requirements=["arrival rate column", "service rate column", "server count column"],
        expected_outputs=["results/queue_summary.csv"],
        column_bindings={
            "arrival_rate_column": "",
            "service_rate_column": "",
            "server_count_column": "",
        },
        paper_guidance=[
            "Check the stability condition before interpreting wait times.",
            "Use capacity sensitivity to justify service recommendations.",
        ],
    ),
}

ROUTE_RECIPES: dict[str, ModelRecipe] = {
    recipe.route_id: recipe for recipe in MODEL_RECIPES.values()
}


def recipe_for_problem_type(problem_type: str) -> ModelRecipe:
    return MODEL_RECIPES[problem_type]


def route_recipe(route_id: str) -> ModelRecipe:
    return ROUTE_RECIPES[route_id]
