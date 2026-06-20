from __future__ import annotations

import re
from typing import Any


def _safe_key(key: str) -> str:
    """Token-safe metric key: only [A-Za-z0-9_-] so it survives evidence_id parsing.

    Metric keys can contain spaces/punctuation (e.g. a contestant name like
    'Billy Ray Cyrus'); those would truncate the `evidence_id=...` trace token and
    break claim-evidence binding.
    """
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(key)).strip("_") or "metric"


def flatten_metrics(metrics: Any, prefix: str = "") -> dict[str, object]:
    """Flatten a (possibly nested) metrics dict to leaf scalar metrics with token-safe
    keys.

    The LLM solver may write per-subproblem nested metrics, e.g.
    {"problem1": {"acc": 0.85}} -> {"problem1_acc": 0.85}. List values (e.g.
    p_values) are skipped — they are not single comparable metrics.
    """
    out: dict[str, object] = {}
    if not isinstance(metrics, dict):
        return out
    for key, value in metrics.items():
        flat_key = f"{prefix}{_safe_key(key)}"
        if isinstance(value, dict):
            out.update(flatten_metrics(value, prefix=f"{flat_key}_"))
        elif isinstance(value, bool) or isinstance(value, (int, float, str)):
            out[flat_key] = value
    return out
