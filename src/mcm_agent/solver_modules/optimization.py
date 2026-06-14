from __future__ import annotations

import pandas as pd


def allocate_by_priority(
    frame: pd.DataFrame,
    *,
    priority_column: str,
    total_resource: float,
    capacity_column: str | None = None,
) -> pd.DataFrame:
    result = frame.copy()
    if priority_column not in result.columns or total_resource <= 0:
        result["recommended_allocation"] = 0.0
        result["allocation_gap"] = 0.0
        return result

    priorities = result[priority_column].clip(lower=0).astype(float)
    if float(priorities.sum()) <= 1e-12:
        result["recommended_allocation"] = 0.0
        result["allocation_gap"] = 0.0
        return result

    raw_allocation = priorities / priorities.sum() * float(total_resource)
    if capacity_column and capacity_column in result.columns:
        capacities = result[capacity_column].clip(lower=0).astype(float)
        allocation = _cap_and_redistribute(raw_allocation, priorities, capacities, float(total_resource))
    else:
        allocation = raw_allocation
    result["recommended_allocation"] = allocation
    result["allocation_gap"] = raw_allocation - allocation
    return result


def _cap_and_redistribute(
    raw_allocation: pd.Series,
    priorities: pd.Series,
    capacities: pd.Series,
    total_resource: float,
) -> pd.Series:
    allocation = raw_allocation.clip(upper=capacities)
    for _ in range(len(allocation) + 1):
        remaining = total_resource - float(allocation.sum())
        if remaining <= 1e-9:
            break
        room = capacities - allocation
        eligible = room > 1e-9
        if not bool(eligible.any()):
            break
        eligible_priorities = priorities.where(eligible, 0.0)
        if float(eligible_priorities.sum()) <= 1e-12:
            increment = room.where(eligible, 0.0)
            increment = increment / increment.sum() * remaining
        else:
            increment = eligible_priorities / eligible_priorities.sum() * remaining
        allocation = (allocation + increment).clip(upper=capacities)
    return allocation
