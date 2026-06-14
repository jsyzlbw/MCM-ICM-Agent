from __future__ import annotations

import numpy as np
import pandas as pd


def entropy_weights(indicators: pd.DataFrame) -> dict[str, float]:
    numeric = _numeric_frame(indicators)
    if numeric.empty:
        return {}
    normalized = _minmax_normalize(numeric)
    values = normalized.to_numpy(dtype=float) + 1e-12
    proportions = values / values.sum(axis=0, keepdims=True)
    sample_count = max(len(normalized), 2)
    entropy = -(proportions * np.log(proportions)).sum(axis=0) / np.log(sample_count)
    diversity = 1 - entropy
    if float(diversity.sum()) <= 1e-12:
        weights = np.ones(len(numeric.columns)) / len(numeric.columns)
    else:
        weights = diversity / diversity.sum()
    return {column: float(weight) for column, weight in zip(numeric.columns, weights, strict=True)}


def topsis_rank(
    frame: pd.DataFrame,
    *,
    indicator_columns: list[str] | None = None,
    entity_column: str | None = None,
) -> pd.DataFrame:
    columns = indicator_columns or list(frame.select_dtypes(include="number").columns)
    if not columns:
        result = frame.copy()
        result["priority_score"] = 0.0
        result["priority_rank"] = 1
        result.attrs["method_metadata"] = {"method": "entropy_topsis", "warning": "no_numeric"}
        return result

    numeric = _numeric_frame(frame[columns])
    weights = entropy_weights(numeric)
    normalized = _vector_normalize(numeric)
    weight_array = np.array([weights[column] for column in numeric.columns], dtype=float)
    weighted = normalized.to_numpy(dtype=float) * weight_array
    ideal_best = weighted.max(axis=0)
    ideal_worst = weighted.min(axis=0)
    distance_best = np.linalg.norm(weighted - ideal_best, axis=1)
    distance_worst = np.linalg.norm(weighted - ideal_worst, axis=1)
    score = distance_worst / (distance_best + distance_worst + 1e-12)

    result = frame.copy()
    result["priority_score"] = score
    result["priority_rank"] = result["priority_score"].rank(
        ascending=False,
        method="dense",
    ).astype(int)
    sort_columns = ["priority_rank"]
    if entity_column and entity_column in result.columns:
        sort_columns.append(entity_column)
    result = result.sort_values(sort_columns).reset_index(drop=True)
    result.attrs["method_metadata"] = {
        "method": "entropy_topsis",
        **{f"entropy_weight_{column}": weight for column, weight in weights.items()},
    }
    return result


def _numeric_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.select_dtypes(include="number").fillna(0.0)


def _minmax_normalize(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy().astype(float)
    for column in normalized.columns:
        minimum = normalized[column].min()
        maximum = normalized[column].max()
        if maximum == minimum:
            normalized[column] = 1.0
        else:
            normalized[column] = (normalized[column] - minimum) / (maximum - minimum)
    return normalized


def _vector_normalize(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy().astype(float)
    for column in normalized.columns:
        norm = float(np.sqrt((normalized[column] ** 2).sum()))
        normalized[column] = normalized[column] / norm if norm > 0 else 0.0
    return normalized
