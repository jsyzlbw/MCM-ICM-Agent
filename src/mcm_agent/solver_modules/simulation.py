from __future__ import annotations

import numpy as np


def monte_carlo_scenarios(
    *,
    base_value: float,
    relative_std: float = 0.1,
    iterations: int = 1000,
    seed: int = 42,
) -> dict[str, float]:
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    if relative_std < 0:
        raise ValueError("relative_std must be non-negative")
    rng = np.random.default_rng(seed)
    samples = rng.normal(
        loc=float(base_value),
        scale=abs(float(base_value)) * float(relative_std),
        size=int(iterations),
    )
    return {
        "iterations": int(iterations),
        "base_value": float(base_value),
        "relative_std": float(relative_std),
        "mean": float(samples.mean()),
        "std": float(samples.std(ddof=1)),
        "p05": float(np.percentile(samples, 5)),
        "p50": float(np.percentile(samples, 50)),
        "p95": float(np.percentile(samples, 95)),
    }
