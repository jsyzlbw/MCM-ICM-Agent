"""Tests for FIG3: FigurePlanningAgent consumes repair_directive.json for
targeted figure-dimension repair.

TDD: tests written FIRST (RED), then implementation added to make them GREEN.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcm_agent.agents.visualization import FigurePlanningAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json, write_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_workspace(tmp_path: Path, *, with_routes: bool = False) -> Path:
    """Return a workspace root with minimal files for FigurePlanningAgent.

    When ``with_routes=True``, a model_route_summary.json is written so that
    ``_route_data_figures`` returns route-based figures (and the fallback
    fig_q1_prediction is suppressed in normal operation).
    """
    workspace = create_workspace(tmp_path / "run_001")
    root = workspace.root
    # Minimal reports so concept-diagram builder doesn't error
    (root / "reports" / "model_decision.md").write_text("# Model Decision", encoding="utf-8")
    (root / "reports" / "experiment_plan.md").write_text("# Experiment Plan", encoding="utf-8")
    (root / "reports" / "validation_report.md").write_text(
        "# Validation Report", encoding="utf-8"
    )
    write_json(root / "results" / "evidence_registry.json", [])
    # Numeric results CSV so the fallback data figure is plottable
    (root / "results" / "problem1_results.csv").write_text(
        "x,y\n1,2\n2,4\n3,6\n", encoding="utf-8"
    )
    if with_routes:
        # Route summary causes _route_data_figures to return route-based items,
        # suppressing the fallback fig_q1_prediction in normal operation.
        write_json(
            root / "results" / "model_route_summary.json",
            {"selected_routes": ["multi_criteria_evaluation"]},
        )
    return root


def _write_figures_repair_directive(root: Path, critique: str, suggestions: list[str]) -> None:
    """Write a repair directive targeting the figure_planning stage."""
    (root / "review").mkdir(parents=True, exist_ok=True)
    directive = {
        "target_stage": "figure_planning",
        "weak_dimension": "figures",
        "score": 2,
        "critique": critique,
        "suggestions": suggestions,
        "iteration": 1,
    }
    (root / "review" / "repair_directive.json").write_text(
        json.dumps(directive), encoding="utf-8"
    )


def _write_sensitivity_csv(root: Path) -> None:
    """Write a sensitivity_analysis.csv with numeric data (>=3 rows)."""
    (root / "results" / "sensitivity_analysis.csv").write_text(
        "parameter,metric\n0.5,10.0\n1.0,12.5\n1.5,14.8\n2.0,16.1\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Test 1 – directive is consumed: plan is richer + critique text present
# ---------------------------------------------------------------------------

def test_figure_planning_consumes_repair_directive(tmp_path: Path) -> None:
    """With a figures-dim repair directive, the plan must be richer (more
    figures) than without it, and at least one figure must carry the
    directive's critique text in its purpose or caption_intent."""

    # --- workspace WITHOUT directive (baseline count) ---
    # Use routes so that the normal path produces only route-based figures
    # (fig_q1_prediction fallback is suppressed), making the baseline smaller.
    root_no_dir = _make_workspace(tmp_path / "no_dir", with_routes=True)
    _write_sensitivity_csv(root_no_dir)
    FigurePlanningAgent().run(root_no_dir)
    plan_no_dir = read_json(root_no_dir / "figures" / "figure_plan.json", [])
    count_no_dir = len(plan_no_dir)

    # --- workspace WITH directive ---
    root_with_dir = _make_workspace(tmp_path / "with_dir", with_routes=True)
    _write_sensitivity_csv(root_with_dir)
    _write_figures_repair_directive(
        root_with_dir,
        critique="too few figures",
        suggestions=["add result and sensitivity plots"],
    )
    FigurePlanningAgent().run(root_with_dir)
    plan_with_dir = read_json(root_with_dir / "figures" / "figure_plan.json", [])
    count_with_dir = len(plan_with_dir)

    # Must be richer
    assert count_with_dir > count_no_dir, (
        f"Expected richer plan with directive ({count_with_dir} figures) "
        f"but got no more than baseline ({count_no_dir})"
    )

    # Critique text must appear in at least one figure's purpose or caption_intent
    critique_text = "too few figures"
    carries_critique = any(
        critique_text in (item.get("purpose", "") or "")
        or critique_text in (item.get("caption_intent", "") or "")
        for item in plan_with_dir
    )
    assert carries_critique, (
        f"Expected directive critique '{critique_text}' to appear in at least one "
        f"planned figure's purpose or caption_intent, but none found in: {plan_with_dir}"
    )


# ---------------------------------------------------------------------------
# Test 2 – no directive → plan identical to current behavior
# ---------------------------------------------------------------------------

def test_figure_planning_no_directive_unchanged(tmp_path: Path) -> None:
    """Without a directive, FigurePlanningAgent must produce the same figure
    ids as without this change (no accidental enrichment)."""

    root_a = _make_workspace(tmp_path / "run_a")
    _write_sensitivity_csv(root_a)
    FigurePlanningAgent().run(root_a)
    plan_a = read_json(root_a / "figures" / "figure_plan.json", [])
    ids_a = sorted(item["figure_id"] for item in plan_a)

    # Run again in a second workspace with no directive — same setup
    root_b = _make_workspace(tmp_path / "run_b")
    _write_sensitivity_csv(root_b)
    # Explicitly ensure no directive file exists
    assert not (root_b / "review" / "repair_directive.json").exists()
    FigurePlanningAgent().run(root_b)
    plan_b = read_json(root_b / "figures" / "figure_plan.json", [])
    ids_b = sorted(item["figure_id"] for item in plan_b)

    assert ids_a == ids_b, (
        f"Without directive, two identical workspaces must yield identical "
        f"figure_ids. Got {ids_a!r} vs {ids_b!r}"
    )


# ---------------------------------------------------------------------------
# Test 3 – directive for a different stage is ignored
# ---------------------------------------------------------------------------

def test_figure_planning_ignores_directive_for_other_stage(tmp_path: Path) -> None:
    """A repair_directive targeting a different stage (e.g. 'paper_writer')
    must leave the figure plan unchanged (no enrichment)."""

    # Baseline without any directive
    root_baseline = _make_workspace(tmp_path / "baseline")
    _write_sensitivity_csv(root_baseline)
    FigurePlanningAgent().run(root_baseline)
    plan_baseline = read_json(root_baseline / "figures" / "figure_plan.json", [])
    ids_baseline = sorted(item["figure_id"] for item in plan_baseline)

    # Workspace with a directive targeting paper_writer (not figure_planning)
    root_other = _make_workspace(tmp_path / "other_stage")
    _write_sensitivity_csv(root_other)
    (root_other / "review").mkdir(parents=True, exist_ok=True)
    other_directive = {
        "target_stage": "paper_writer",
        "weak_dimension": "math",
        "score": 2,
        "critique": "math notation weak",
        "suggestions": ["add more equations"],
        "iteration": 1,
    }
    (root_other / "review" / "repair_directive.json").write_text(
        json.dumps(other_directive), encoding="utf-8"
    )
    FigurePlanningAgent().run(root_other)
    plan_other = read_json(root_other / "figures" / "figure_plan.json", [])
    ids_other = sorted(item["figure_id"] for item in plan_other)

    assert ids_other == ids_baseline, (
        f"Directive for 'paper_writer' must NOT change the figure plan. "
        f"Baseline: {ids_baseline!r}, got: {ids_other!r}"
    )
