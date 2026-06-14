import pandas as pd

from mcm_agent.solver_modules.evaluation import entropy_weights, topsis_rank
from mcm_agent.solver_modules.forecasting import linear_trend_forecast
from mcm_agent.solver_modules.network import shortest_path_table
from mcm_agent.solver_modules.optimization import allocate_by_priority
from mcm_agent.solver_modules.simulation import monte_carlo_scenarios


def test_entropy_weights_are_normalized_and_prefer_informative_indicator() -> None:
    frame = pd.DataFrame(
        {
            "risk": [9, 5, 1],
            "constant": [3, 3, 3],
        }
    )

    weights = entropy_weights(frame)

    assert round(sum(weights.values()), 6) == 1.0
    assert weights["risk"] > weights["constant"]


def test_topsis_rank_returns_priority_score_and_dense_rank() -> None:
    frame = pd.DataFrame(
        {
            "district": ["A", "B", "C"],
            "risk": [9, 5, 1],
            "exposure": [8, 4, 2],
        }
    )

    ranked = topsis_rank(frame, indicator_columns=["risk", "exposure"], entity_column="district")

    assert list(ranked["district"]) == ["A", "B", "C"]
    assert ranked.iloc[0]["priority_rank"] == 1
    assert ranked.iloc[0]["priority_score"] > ranked.iloc[-1]["priority_score"]
    assert "entropy_weight_risk" in ranked.attrs["method_metadata"]


def test_allocate_by_priority_respects_capacity_and_bounds() -> None:
    frame = pd.DataFrame(
        {
            "district": ["A", "B", "C"],
            "priority_score": [0.7, 0.2, 0.1],
            "capacity": [5, 4, 10],
        }
    )

    allocated = allocate_by_priority(
        frame,
        priority_column="priority_score",
        total_resource=10,
        capacity_column="capacity",
    )

    assert round(float(allocated["recommended_allocation"].sum()), 6) == 10.0
    assert all(allocated["recommended_allocation"] <= allocated["capacity"] + 1e-9)
    assert allocated.iloc[0]["recommended_allocation"] == 5


def test_linear_trend_forecast_adds_future_rows_and_error_metrics() -> None:
    frame = pd.DataFrame({"period": [1, 2, 3, 4], "demand": [10, 12, 14, 16]})

    forecast, metrics = linear_trend_forecast(
        frame,
        time_column="period",
        target_column="demand",
        periods=2,
    )

    assert list(forecast["forecast_period"].tail(2)) == [5.0, 6.0]
    assert list(forecast["forecast_value"].tail(2)) == [18.0, 20.0]
    assert metrics["forecast_horizon"] == 2
    assert metrics["training_mae"] < 1e-9


def test_monte_carlo_scenarios_returns_reproducible_percentiles() -> None:
    summary = monte_carlo_scenarios(
        base_value=100,
        relative_std=0.1,
        iterations=1000,
        seed=7,
    )

    assert summary["iterations"] == 1000
    assert 95 < summary["mean"] < 105
    assert summary["p95"] > summary["p50"] > summary["p05"]


def test_shortest_path_table_returns_path_and_cost() -> None:
    edges = pd.DataFrame(
        {
            "source": ["A", "A", "B"],
            "target": ["B", "C", "C"],
            "cost": [1, 5, 2],
        }
    )

    table = shortest_path_table(edges, source="A", target="C")

    assert table.iloc[0]["path"] == "A -> B -> C"
    assert table.iloc[0]["path_cost"] == 3
