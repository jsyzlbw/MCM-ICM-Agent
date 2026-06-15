from __future__ import annotations

from pydantic import BaseModel, Field

from mcm_agent.core.modeling_intelligence import ProblemDiagnosis


ROUTE_ROLES = {
    "multi_criteria_evaluation": "screening",
    "constrained_optimization": "decision",
    "forecasting_model": "prediction",
    "monte_carlo_simulation": "uncertainty",
    "classification_model": "prediction",
    "clustering_segmentation": "structure",
    "queuing_service_model": "service",
    "network_flow_graph": "structure",
    "multi_objective_decision": "tradeoff",
}

ROUTE_ORDER = [
    "multi_criteria_evaluation",
    "constrained_optimization",
    "forecasting_model",
    "monte_carlo_simulation",
    "classification_model",
    "clustering_segmentation",
    "queuing_service_model",
    "network_flow_graph",
    "multi_objective_decision",
]


class ModelRoutePlan(BaseModel):
    route_ids: list[str] = Field(default_factory=list)
    execution_order: list[str] = Field(default_factory=list)
    route_roles: dict[str, str] = Field(default_factory=dict)
    is_hybrid: bool = False
    truncated: bool = False


def build_route_plan(diagnosis: ProblemDiagnosis, *, max_routes: int = 4) -> ModelRoutePlan:
    detected = [route.route_id for route in diagnosis.routes]
    ordered = [route_id for route_id in ROUTE_ORDER if route_id in detected]
    truncated = len(ordered) > max_routes
    route_ids = ordered[:max_routes]
    return ModelRoutePlan(
        route_ids=route_ids,
        execution_order=route_ids,
        route_roles={
            route_id: ROUTE_ROLES.get(route_id, "support")
            for route_id in route_ids
        },
        is_hybrid=len(route_ids) > 1,
        truncated=truncated,
    )
