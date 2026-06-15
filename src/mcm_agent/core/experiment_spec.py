from __future__ import annotations

from pydantic import BaseModel, Field

from mcm_agent.core.model_route_plan import ROUTE_ROLES


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
    "multi_criteria_evaluation": ExperimentSpecItem(
        route_id="multi_criteria_evaluation",
        solver_module="mcm_agent.solver_modules.evaluation",
        method="entropy_weighted_topsis",
        input_requirements=["numeric indicators", "optional entity column"],
        expected_outputs=["results/problem1_results.csv"],
        metrics=["priority_score_mean", "top_priority_entity"],
        column_bindings={"entity_column": "", "indicator_columns": ""},
    ),
    "constrained_optimization": ExperimentSpecItem(
        route_id="constrained_optimization",
        solver_module="mcm_agent.solver_modules.optimization",
        method="capacity_constrained_priority_allocation",
        input_requirements=["priority score", "optional capacity or budget column"],
        expected_outputs=["results/problem1_results.csv"],
        metrics=["allocation_capacity_total"],
        column_bindings={"priority_column": "priority_score", "capacity_column": ""},
    ),
    "forecasting_model": ExperimentSpecItem(
        route_id="forecasting_model",
        solver_module="mcm_agent.solver_modules.forecasting",
        method="linear_trend_forecast",
        input_requirements=["time column", "target numeric column"],
        expected_outputs=["results/forecast_results.csv"],
        metrics=["forecast_training_mae", "forecast_training_rmse"],
        column_bindings={"time_column": "", "target_column": ""},
    ),
    "monte_carlo_simulation": ExperimentSpecItem(
        route_id="monte_carlo_simulation",
        solver_module="mcm_agent.solver_modules.simulation",
        method="monte_carlo_scenarios",
        input_requirements=["base numeric value", "uncertainty assumption"],
        expected_outputs=["results/simulation_summary.json"],
        metrics=["simulation_mean", "simulation_p95"],
        column_bindings={"base_value_column": ""},
    ),
    "network_flow_graph": ExperimentSpecItem(
        route_id="network_flow_graph",
        solver_module="mcm_agent.solver_modules.network",
        method="shortest_path_table",
        input_requirements=["source column", "target column", "cost column"],
        expected_outputs=["results/network_paths.csv"],
        metrics=["shortest_path_cost", "shortest_path_edge_count"],
        column_bindings={"source_column": "", "target_column": "", "cost_column": ""},
    ),
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
