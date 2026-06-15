from __future__ import annotations

from pydantic import BaseModel, Field

from mcm_agent.core.model_route_plan import ROUTE_ROLES
from mcm_agent.core.model_recipes import ROUTE_RECIPES


class ExperimentSpecItem(BaseModel):
    route_id: str
    solver_module: str
    method: str
    role: str = "support"
    input_requirements: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    column_bindings: dict[str, str | list[str]] = Field(default_factory=dict)


class ExperimentSpec(BaseModel):
    version: int = 1
    route_plan: dict[str, object] = Field(default_factory=dict)
    experiments: list[ExperimentSpecItem] = Field(default_factory=list)


ROUTE_EXPERIMENTS = {
    route_id: ExperimentSpecItem(
        route_id=recipe.route_id,
        solver_module=recipe.solver_module,
        method=recipe.method,
        role=ROUTE_ROLES.get(route_id, recipe.role),
        input_requirements=recipe.input_requirements,
        expected_outputs=recipe.expected_outputs,
        metrics=recipe.metrics,
        column_bindings=recipe.column_bindings,
    )
    for route_id, recipe in ROUTE_RECIPES.items()
}


def build_experiment_spec(route_ids: list[str]) -> ExperimentSpec:
    selected = [route_id for route_id in route_ids if route_id in ROUTE_EXPERIMENTS]
    experiments = [
        ROUTE_EXPERIMENTS[route_id].model_copy(deep=True).model_copy(
            update={"role": ROUTE_ROLES.get(route_id, "support")}
        )
        for route_id in selected
    ]
    return ExperimentSpec(
        route_plan={
            "is_hybrid": len(selected) > 1,
            "execution_order": selected,
            "route_roles": {
                route_id: ROUTE_ROLES.get(route_id, "support")
                for route_id in selected
            },
        },
        experiments=experiments,
    )
