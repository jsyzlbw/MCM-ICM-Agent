from __future__ import annotations

from pydantic import BaseModel, Field


class ModelRoute(BaseModel):
    route_id: str
    candidate: str
    problem_type: str
    main_strength: str
    data_needs: list[str]
    methods: list[str]
    metrics: list[str]
    implementation_risk: str


class ProblemDiagnosis(BaseModel):
    primary_problem_types: list[str] = Field(default_factory=list)
    routes: list[ModelRoute] = Field(default_factory=list)
    data_limitations: list[str] = Field(default_factory=list)


class ModelingIntelligence:
    def diagnose(self, text: str) -> ProblemDiagnosis:
        lowered = text.lower()
        problem_types = self._problem_types(lowered)
        if not problem_types:
            problem_types = ["evaluation"]
        return self.diagnose_problem_types(problem_types)

    def diagnose_problem_types(self, problem_types: list[str]) -> ProblemDiagnosis:
        unique_problem_types = []
        for problem_type in problem_types:
            if problem_type not in unique_problem_types:
                unique_problem_types.append(problem_type)
        routes = [self._route_for(problem_type) for problem_type in unique_problem_types]
        return ProblemDiagnosis(
            primary_problem_types=unique_problem_types,
            routes=routes,
            data_limitations=[
                "Use registered attachments and external sources only.",
                "If direct private data is unavailable, use proxy variables and state assumptions.",
            ],
        )

    def _problem_types(self, lowered: str) -> list[str]:
        scores = {
            "evaluation": self._score(
                lowered,
                [
                    "rank",
                    "ranking",
                    "score",
                    "priority",
                    "evaluate",
                    "assessment",
                    "index",
                    "indicator",
                    "decision",
                    "district",
                ],
            ),
            "optimization": self._score(
                lowered,
                [
                    "optimize",
                    "optimization",
                    "allocate",
                    "allocation",
                    "limited",
                    "constraint",
                    "budget",
                    "resource",
                    "schedule",
                    "policy",
                ],
            ),
            "prediction": self._score(
                lowered,
                [
                    "forecast",
                    "predict",
                    "prediction",
                    "demand",
                    "future",
                    "trend",
                    "time series",
                    "monthly",
                    "yearly",
                    "estimate",
                ],
            ),
            "simulation": self._score(
                lowered,
                [
                    "simulate",
                    "simulation",
                    "scenario",
                    "uncertainty",
                    "stochastic",
                    "monte carlo",
                    "robust",
                    "random",
                ],
            ),
            "graph_network": self._score(
                lowered,
                [
                    "network",
                    "graph",
                    "shortest path",
                    "path",
                    "route",
                    "flow",
                    "evacuation",
                    "roads",
                    "transport",
                ],
            ),
            "multi_objective": self._score(
                lowered,
                [
                    "multi-objective",
                    "multi objective",
                    "tradeoff",
                    "trade-off",
                    "pareto",
                    "balance",
                    "conflicting",
                ],
            ),
        }
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return [problem_type for problem_type, score in ranked if score > 0]

    def _score(self, lowered: str, keywords: list[str]) -> int:
        return sum(1 for keyword in keywords if keyword in lowered)

    def _route_for(self, problem_type: str) -> ModelRoute:
        routes = {
            "evaluation": ModelRoute(
                route_id="multi_criteria_evaluation",
                candidate="Entropy-TOPSIS priority scoring",
                problem_type="evaluation",
                main_strength="Transparent ranking from normalized indicators",
                data_needs=["indicator table", "weights or entropy-derived weights"],
                methods=["normalization", "entropy weighting", "TOPSIS"],
                metrics=["priority score", "rank stability"],
                implementation_risk="low",
            ),
            "optimization": ModelRoute(
                route_id="constrained_optimization",
                candidate="Resource allocation optimization",
                problem_type="optimization",
                main_strength="Turns model scores into budget-aware recommendations",
                data_needs=["resource limits", "priority scores", "capacity constraints"],
                methods=["linear programming", "integer allocation", "sensitivity analysis"],
                metrics=["objective value", "coverage", "constraint violation count"],
                implementation_risk="medium",
            ),
            "prediction": ModelRoute(
                route_id="forecasting_model",
                candidate="Interpretable forecasting baseline",
                problem_type="prediction",
                main_strength="Forecasts future demand or risk with explainable features",
                data_needs=["historical observations", "time or feature columns"],
                methods=["linear regression", "random forest", "time-series baseline"],
                metrics=["RMSE", "MAE", "out-of-sample error"],
                implementation_risk="medium",
            ),
            "simulation": ModelRoute(
                route_id="monte_carlo_simulation",
                candidate="Scenario and uncertainty simulation",
                problem_type="simulation",
                main_strength="Tests robustness under uncertain assumptions",
                data_needs=["parameter ranges", "uncertainty assumptions"],
                methods=["Monte Carlo simulation", "scenario analysis"],
                metrics=["expected value", "percentile outcomes", "failure probability"],
                implementation_risk="medium",
            ),
            "graph_network": ModelRoute(
                route_id="network_flow_graph",
                candidate="Network flow or shortest-path model",
                problem_type="graph_network",
                main_strength="Captures routes, flows, connectivity, and bottlenecks",
                data_needs=["nodes", "edges", "capacities or travel costs"],
                methods=["shortest path", "max flow", "minimum cost flow"],
                metrics=["travel cost", "flow served", "bottleneck count"],
                implementation_risk="medium",
            ),
            "multi_objective": ModelRoute(
                route_id="multi_objective_decision",
                candidate="Multi-objective trade-off model",
                problem_type="multi_objective",
                main_strength="Makes conflicting goals and Pareto trade-offs explicit",
                data_needs=["objective definitions", "decision variables", "constraints"],
                methods=["weighted sum", "Pareto analysis", "goal programming"],
                metrics=["Pareto dominance", "weighted utility", "trade-off slope"],
                implementation_risk="medium",
            ),
        }
        return routes[problem_type]
