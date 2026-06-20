from __future__ import annotations

from typing import Any


def flatten_metrics(metrics: Any, prefix: str = "") -> dict[str, object]:
    """Flatten a (possibly nested) metrics dict to leaf scalar metrics.

    The LLM solver may write per-subproblem nested metrics, e.g.
    {"problem1": {"acc": 0.85}} -> {"problem1_acc": 0.85}. List values (e.g.
    p_values) are skipped — they are not single comparable metrics.
    """
    out: dict[str, object] = {}
    if not isinstance(metrics, dict):
        return out
    for key, value in metrics.items():
        flat_key = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(flatten_metrics(value, prefix=f"{flat_key}_"))
        elif isinstance(value, bool) or isinstance(value, (int, float, str)):
            out[flat_key] = value
    return out
