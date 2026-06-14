import pandas as pd

from mcm_agent.solver_modules.evaluation import entropy_weights, topsis_rank
from mcm_agent.solver_modules.optimization import allocate_by_priority


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
