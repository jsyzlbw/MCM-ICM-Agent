from __future__ import annotations

import math

import pandas as pd


def mmc_queue_summary(
    frame: pd.DataFrame,
    *,
    arrival_rate_column: str,
    service_rate_column: str,
    server_count_column: str | None = None,
) -> tuple[pd.DataFrame, dict[str, float]]:
    for column in [arrival_rate_column, service_rate_column]:
        if column not in frame.columns:
            raise ValueError(f"missing queue column: {column}")
    result = frame.copy()
    servers = (
        result[server_count_column].fillna(1).clip(lower=1).astype(int)
        if server_count_column and server_count_column in result.columns
        else pd.Series([1 for _ in range(len(result))], index=result.index)
    )
    utilization_values = []
    wait_values = []
    stable_values = []
    for row_index, row in result.iterrows():
        arrival_rate = max(float(row[arrival_rate_column]), 0.0)
        service_rate = max(float(row[service_rate_column]), 1e-12)
        server_count = int(servers.loc[row_index])
        utilization = arrival_rate / (server_count * service_rate)
        stable = utilization < 1
        wait_time = (
            _erlang_c_wait(arrival_rate, service_rate, server_count)
            if stable
            else float("inf")
        )
        utilization_values.append(utilization)
        wait_values.append(wait_time)
        stable_values.append(stable)
    result["utilization"] = utilization_values
    result["expected_wait_time"] = wait_values
    result["stable_queue"] = stable_values
    finite_waits = [value for value in wait_values if math.isfinite(value)]
    return result, {
        "queue_utilization": float(sum(utilization_values) / len(utilization_values))
        if utilization_values
        else 0.0,
        "expected_wait_time": float(sum(finite_waits) / len(finite_waits))
        if finite_waits
        else float("inf"),
        "unstable_queue_count": float(sum(1 for stable in stable_values if not stable)),
    }


def _erlang_c_wait(arrival_rate: float, service_rate: float, server_count: int) -> float:
    traffic = arrival_rate / service_rate
    utilization = traffic / server_count
    if arrival_rate <= 0 or utilization <= 0:
        return 0.0
    if utilization >= 1:
        return float("inf")
    sum_terms = sum((traffic**n) / math.factorial(n) for n in range(server_count))
    final_term = (traffic**server_count) / (
        math.factorial(server_count) * (1 - utilization)
    )
    p0 = 1 / (sum_terms + final_term)
    erlang_c = final_term * p0
    return erlang_c / (server_count * service_rate - arrival_rate)
