"""TDD tests for ValidationAgent result-plausibility check (PQ3).

Two scenarios:
  (a) primary metric = 0.0 (or NaN)  → gate fails, repair_stage=solver_coder
  (b) primary metric = 0.85 (sane)   → gate passes plausibility (status == "pass")

All other validation checks are satisfied in both cases.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from mcm_agent.agents.validation import ValidationAgent
from mcm_agent.core.model_spec import ModelSpec, SubproblemModel, write_model_spec
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json, write_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_passing_workspace(root: Path, primary_metric_value: float) -> Path:
    """Create a workspace whose primary metric is ``primary_metric_value``.

    All *other* validation checks (evidence coverage, experiment runs,
    solver binding) are satisfied so the only potential failure is the
    plausibility gate.
    """
    workspace = create_workspace(root)
    ws = workspace.root

    # Write a ModelSpec that names "accuracy" as the primary metric for q1.
    spec = ModelSpec(
        problem_restatement="Test problem.",
        subproblems=[
            SubproblemModel(
                subproblem_id="q1",
                title="Test model",
                approach="regression",
                metrics=["accuracy"],
            )
        ],
    )
    write_model_spec(ws, spec)

    # Write model_metrics.json with the primary metric value.
    write_json(ws / "results" / "model_metrics.json", {"accuracy": primary_metric_value})

    # Write evidence for the metric so evidence-coverage check passes.
    write_json(
        ws / "results" / "evidence_registry.json",
        [
            {
                "evidence_id": "metric_accuracy",
                "claim": f"Metric accuracy equals {primary_metric_value}.",
                "value": primary_metric_value,
                "source_type": "code_output",
                "source_path": "results/model_metrics.json",
                "generated_by": "code/experiments/problem1.py",
                "used_in": [],
                "verified": True,
            }
        ],
    )
    # No experiment_runs.jsonl entries → the runner check trivially passes (no
    # missing outputs to flag).  No solver_binding_report.json → binding check
    # trivially passes (missing file → empty dict → no "status":"fail").
    return ws


# ---------------------------------------------------------------------------
# (a) Implausible primary metric  → gate must fail + repair_stage=solver_coder
# ---------------------------------------------------------------------------


def test_zero_primary_metric_triggers_plausibility_fail(tmp_path: Path) -> None:
    ws = _build_passing_workspace(tmp_path / "ws_zero", primary_metric_value=0.0)

    ValidationAgent().run(ws)

    gate = read_json(ws / "review" / "validation_gate.json", {})
    assert gate["status"] == "fail", "Gate must fail when primary metric == 0.0"
    assert gate["repair_stage"] == "solver_coder", (
        "repair_stage must be 'solver_coder' so the workflow re-runs the solver"
    )
    findings = gate.get("blocking_findings", [])
    assert any("plausib" in f.lower() or "primary" in f.lower() or "accuracy" in f.lower() for f in findings), (
        f"No plausibility-related finding in blocking_findings: {findings}"
    )


def test_nan_primary_metric_triggers_plausibility_fail(tmp_path: Path) -> None:
    ws = _build_passing_workspace(tmp_path / "ws_nan", primary_metric_value=float("nan"))

    ValidationAgent().run(ws)

    gate = read_json(ws / "review" / "validation_gate.json", {})
    assert gate["status"] == "fail", "Gate must fail when primary metric is NaN"
    assert gate["repair_stage"] == "solver_coder"
    findings = gate.get("blocking_findings", [])
    assert any("plausib" in f.lower() or "primary" in f.lower() or "accuracy" in f.lower() for f in findings)


# ---------------------------------------------------------------------------
# (b) Sane primary metric (0.85) → plausibility check must not cause failure
# ---------------------------------------------------------------------------


def test_sane_primary_metric_passes_plausibility(tmp_path: Path) -> None:
    ws = _build_passing_workspace(tmp_path / "ws_sane", primary_metric_value=0.85)

    ValidationAgent().run(ws)

    gate = read_json(ws / "review" / "validation_gate.json", {})
    # The gate must not fail *due to plausibility* — with all other checks
    # satisfied, the overall status should be "pass".
    findings = gate.get("blocking_findings", [])
    plausibility_findings = [
        f for f in findings
        if "plausib" in f.lower() or "primary" in f.lower()
    ]
    assert plausibility_findings == [], (
        f"Unexpected plausibility finding for sane metric 0.85: {plausibility_findings}"
    )
    assert gate["status"] == "pass", (
        f"Gate should pass for sane primary metric; blocking_findings={findings}"
    )


# ---------------------------------------------------------------------------
# (c) Nested per-subproblem metrics: suffix match resolves the spec metric
# ---------------------------------------------------------------------------


def _build_nested_workspace(root: Path, primary_metric_value: float) -> Path:
    """Like _build_passing_workspace but uses NESTED model_metrics.json.

    The solver writes ``{"q1": {"elimination_consistency_rate": 0.0, "other": 5.0}}``.
    After flattening the keys become ``q1_elimination_consistency_rate`` and
    ``q1_other``.  The ModelSpec names ``elimination_consistency_rate`` as the
    primary metric — so exact-match fails and the suffix-match must kick in.
    """
    workspace = create_workspace(root)
    ws = workspace.root

    spec = ModelSpec(
        problem_restatement="Test problem nested.",
        subproblems=[
            SubproblemModel(
                subproblem_id="q1",
                title="Test model",
                approach="regression",
                metrics=["elimination_consistency_rate"],
            )
        ],
    )
    write_model_spec(ws, spec)

    # NESTED format: {sub_id: {metric: val}} — mirrors the real solver output.
    # NOTE: "other" is listed FIRST so that dict-insertion order / fallback would
    # pick q1_other (5.0, sane) instead of q1_elimination_consistency_rate if the
    # suffix-match is missing.  This ensures the test fails without the fix.
    write_json(
        ws / "results" / "model_metrics.json",
        {"q1": {"other": 5.0, "elimination_consistency_rate": primary_metric_value}},
    )

    # Evidence for all flattened keys so the evidence-coverage check passes and
    # the ONLY gate failure can come from the plausibility check.
    write_json(
        ws / "results" / "evidence_registry.json",
        [
            {
                "evidence_id": "metric_q1_other",
                "claim": "Other metric computed.",
                "value": 5.0,
                "source_type": "code_output",
                "source_path": "results/model_metrics.json",
                "generated_by": "code/experiments/problem1.py",
                "used_in": [],
                "verified": True,
            },
            {
                "evidence_id": "metric_q1_elimination_consistency_rate",
                "claim": "elimination_consistency_rate computed.",
                "value": primary_metric_value,
                "source_type": "code_output",
                "source_path": "results/model_metrics.json",
                "generated_by": "code/experiments/problem1.py",
                "used_in": [],
                "verified": True,
            },
        ],
    )
    return ws


def test_primary_metric_resolves_nested_prefixed_key(tmp_path: Path) -> None:
    """Suffix match must find q1_elimination_consistency_rate (value 0.0) not 'other'."""
    ws = _build_nested_workspace(tmp_path / "ws_nested_zero", primary_metric_value=0.0)

    ValidationAgent().run(ws)

    gate = read_json(ws / "review" / "validation_gate.json", {})
    # 0.0 is degenerate — the gate must FAIL, meaning the suffix match correctly
    # targeted q1_elimination_consistency_rate (not the sane 'other' = 5.0).
    assert gate["status"] == "fail", (
        "Gate must fail because the suffix-matched primary metric is 0.0 (degenerate); "
        f"got status={gate['status']!r}.  If it passed, the code checked 'other'=5.0 instead."
    )
    findings = gate.get("blocking_findings", [])
    assert any(
        "plausib" in f.lower() or "primary" in f.lower() or "elimination" in f.lower()
        for f in findings
    ), f"No plausibility finding referencing the primary metric: {findings}"
