"""TDD: PQ4 — deterministic sensitivity sweep fallback in the baseline solver.

Contract:
- After the baseline solver runs (no LLM) on numeric processed data,
  results/sensitivity_analysis.csv must exist.
- It must have >=3 data rows (excluding the header).
- The primary-metric column must VARY across at least two rows — proving real
  recomputation, NOT a constant placeholder or fabricated constant.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from mcm_agent.agents.solver import SolverCoderAgent
from mcm_agent.core.workspace import create_workspace


def _build_workspace(tmp_path: Path) -> Path:
    """Create a minimal workspace with three numeric columns, no LLM provider."""
    root = create_workspace(tmp_path / "ws").root
    processed = root / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    # Five rows, two numeric columns — gives the sweep enough variance to work with.
    (processed / "data.csv").write_text(
        "entity,score,weight\n"
        "A,10,1\n"
        "B,20,2\n"
        "C,30,3\n"
        "D,40,4\n"
        "E,50,5\n",
        encoding="utf-8",
    )
    return root


def test_baseline_produces_sensitivity_csv_with_3_or_more_rows(tmp_path: Path) -> None:
    """After baseline solve, sensitivity_analysis.csv must exist with >=3 data rows."""
    root = _build_workspace(tmp_path)

    SolverCoderAgent().run(root)  # no LLM → templated baseline path

    sensitivity_path = root / "results" / "sensitivity_analysis.csv"
    assert sensitivity_path.exists(), "results/sensitivity_analysis.csv was not created"

    df = pd.read_csv(sensitivity_path)
    assert len(df) >= 3, (
        f"sensitivity_analysis.csv must have >=3 data rows; got {len(df)}: {df.to_string()}"
    )


def test_baseline_sensitivity_metric_column_varies(tmp_path: Path) -> None:
    """The metric column in sensitivity_analysis.csv must NOT be constant — real recomputation."""
    root = _build_workspace(tmp_path)

    SolverCoderAgent().run(root)

    sensitivity_path = root / "results" / "sensitivity_analysis.csv"
    assert sensitivity_path.exists(), "results/sensitivity_analysis.csv was not created"

    df = pd.read_csv(sensitivity_path)
    assert len(df) >= 3, f"Need >=3 rows for variance check; got {len(df)}"

    # The last column is the metric column; its values must differ across at least two rows.
    metric_col = df.columns[-1]
    metric_values = df[metric_col].astype(float)
    assert metric_values.nunique() >= 2, (
        f"Metric column '{metric_col}' is constant ({metric_values.unique()}) — "
        "this looks like a fabricated placeholder, not a real recomputation."
    )


def test_sensitivity_fallback_skipped_when_csv_already_has_3_rows(tmp_path: Path) -> None:
    """If solver (LLM path) already wrote >=3 real rows, the fallback must not overwrite."""
    root = _build_workspace(tmp_path)

    # Pre-populate a real sensitivity CSV with 5 rows before the solver runs.
    results_dir = root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    existing_content = (
        "parameter,scale_factor,numeric_mean\n"
        "numeric_input_scale,0.80,15.0\n"
        "numeric_input_scale,0.90,18.0\n"
        "numeric_input_scale,1.00,20.0\n"
        "numeric_input_scale,1.10,22.0\n"
        "numeric_input_scale,1.20,24.0\n"
    )
    (results_dir / "sensitivity_analysis.csv").write_text(existing_content, encoding="utf-8")

    SolverCoderAgent().run(root)

    # The pre-existing CSV must not be replaced with a shorter version.
    df = pd.read_csv(results_dir / "sensitivity_analysis.csv")
    assert len(df) >= 5, (
        "Pre-existing 5-row sensitivity CSV was wrongly truncated to "
        f"{len(df)} rows after baseline solver ran."
    )
