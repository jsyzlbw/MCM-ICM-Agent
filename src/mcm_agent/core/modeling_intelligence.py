from __future__ import annotations

import re

from pydantic import BaseModel, Field

from mcm_agent.core.model_recipes import recipe_for_problem_type


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
            "classification": self._score(
                lowered,
                [
                    "classify",
                    "classification",
                    "category",
                    "label",
                    "risk level",
                    "binary",
                    "logistic",
                ],
            ),
            "clustering": self._score(
                lowered,
                [
                    "cluster",
                    "clustering",
                    "segmentation",
                    "segment",
                    "group",
                    "unsupervised",
                    "typology",
                ],
            ),
            "queuing": self._score(
                lowered,
                [
                    "queue",
                    "queuing",
                    "waiting time",
                    "arrival",
                    "service rate",
                    "server",
                    "counter",
                    "line",
                ],
            ),
        }
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return [problem_type for problem_type, score in ranked if score > 0]

    def _score(self, lowered: str, keywords: list[str]) -> int:
        return sum(1 for keyword in keywords if self._contains_keyword(lowered, keyword))

    def _contains_keyword(self, lowered: str, keyword: str) -> bool:
        pattern = r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])"
        return re.search(pattern, lowered) is not None

    def _route_for(self, problem_type: str) -> ModelRoute:
        recipe = recipe_for_problem_type(problem_type)
        return ModelRoute(
            route_id=recipe.route_id,
            candidate=recipe.candidate,
            problem_type=recipe.problem_type,
            main_strength=recipe.main_strength,
            data_needs=recipe.data_needs,
            methods=recipe.methods,
            metrics=recipe.metrics,
            implementation_risk=recipe.implementation_risk,
        )
