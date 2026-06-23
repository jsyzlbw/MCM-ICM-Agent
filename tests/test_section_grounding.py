"""Task B2 — Ground results and sensitivity sections in ModelSpec approach + validation.

Tests for `_facts_for_section` ensuring:
1. Results section includes real metrics AND model_approach (from ModelSpec) AND validation.
2. Sensitivity section includes model_approach alongside existing validation/sensitivity_table.
3. Graceful degradation when model_spec is None (model_approach absent or [], no crash).
"""
from __future__ import annotations

from mcm_agent.agents.paper_context import PaperContext
from mcm_agent.agents.writer import PaperWriterAgent
from mcm_agent.core.model_spec import ModelSpec, SubproblemModel


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_context() -> PaperContext:
    return PaperContext(
        problem_summary="Optimize a wildfire suppression network.",
        model_decision_summary="We apply gradient descent to minimize loss.",
        direction_summary="Hybrid combinatorial-continuous formulation.",
        validation_summary="RMSE < 0.05 across hold-out scenarios. Cross-validation confirms stability.",
    )


def _make_spec() -> ModelSpec:
    return ModelSpec(
        version=1,
        problem_restatement="Wildfire suppression optimization.",
        subproblems=[
            SubproblemModel(
                subproblem_id="SP1",
                title="Resource Allocation",
                approach="integer linear programming",
                variables=[],
                assumptions=["Homogeneous terrain"],
                equations=["\\min \\sum_i x_i"],
                algorithm_steps=["Step 1: initialize", "Step 2: solve LP relaxation"],
                metrics=["coverage_rate"],
            ),
            SubproblemModel(
                subproblem_id="SP2",
                title="Route Optimization",
                approach="dynamic programming on DAG",
                variables=[],
                assumptions=["No traffic delays"],
                equations=["V(s) = \\min_{a} c(s,a) + V(s')"],
                algorithm_steps=["Step 1: topological sort", "Step 2: Bellman update"],
                metrics=["travel_time_reduction"],
            ),
        ],
    )


def _make_real_metrics() -> dict:
    return {
        "coverage_rate": 0.92,
        "travel_time_reduction": 0.15,
        "total_cost": 1234.5,
    }


# ---------------------------------------------------------------------------
# Test 1: results facts include metrics, model_approach (from spec), and validation
# ---------------------------------------------------------------------------

def test_results_facts_include_metrics_and_model_context() -> None:
    """_facts_for_section('results') must return:
    - metrics dict with the real metric keys
    - non-empty model_approach list referencing subproblem approaches
    - a validation field with text from validation_summary
    """
    agent = PaperWriterAgent(llm_provider=None)
    context = _make_context()
    spec = _make_spec()
    metrics = _make_real_metrics()

    facts = agent._facts_for_section(
        name="results",
        context=context,
        metrics=metrics,
        claims=[],
        model_spec=spec,
    )

    # metrics must be present with real keys
    assert "metrics" in facts, f"'metrics' key missing from results facts; got: {list(facts.keys())}"
    assert "coverage_rate" in facts["metrics"], (
        f"Real metric 'coverage_rate' not found in results facts['metrics']; got: {facts['metrics']}"
    )
    assert "travel_time_reduction" in facts["metrics"], (
        f"Real metric 'travel_time_reduction' not found; got: {facts['metrics']}"
    )

    # model_approach must be non-empty and reference the subproblem approaches
    assert "model_approach" in facts, (
        f"'model_approach' key missing from results facts; got: {list(facts.keys())}"
    )
    model_approach = facts["model_approach"]
    assert isinstance(model_approach, list), (
        f"'model_approach' must be a list, got: {type(model_approach)}"
    )
    assert len(model_approach) > 0, "'model_approach' must be non-empty when spec has subproblems"
    approach_str = str(model_approach)
    assert "integer linear programming" in approach_str, (
        f"SP1 approach 'integer linear programming' not found in model_approach: {model_approach}"
    )
    assert "dynamic programming on DAG" in approach_str, (
        f"SP2 approach 'dynamic programming on DAG' not found in model_approach: {model_approach}"
    )

    # validation must be present
    assert "validation" in facts, (
        f"'validation' key missing from results facts; got: {list(facts.keys())}"
    )
    assert "RMSE" in str(facts["validation"]), (
        f"validation field should contain text from validation_summary; got: {facts['validation']!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: sensitivity facts include model_approach alongside existing fields
# ---------------------------------------------------------------------------

def test_sensitivity_facts_include_model_context() -> None:
    """_facts_for_section('sensitivity') must carry model_approach (non-empty)
    alongside the existing validation field.
    """
    agent = PaperWriterAgent(llm_provider=None)
    context = _make_context()
    spec = _make_spec()
    metrics = _make_real_metrics()

    facts = agent._facts_for_section(
        name="sensitivity",
        context=context,
        metrics=metrics,
        claims=[],
        model_spec=spec,
    )

    # validation must still be present (existing behaviour)
    assert "validation" in facts, (
        f"'validation' key missing from sensitivity facts; got: {list(facts.keys())}"
    )
    assert "RMSE" in str(facts["validation"]), (
        f"validation should contain validation_summary text; got: {facts['validation']!r}"
    )

    # model_approach must be added
    assert "model_approach" in facts, (
        f"'model_approach' key missing from sensitivity facts; got: {list(facts.keys())}"
    )
    model_approach = facts["model_approach"]
    assert isinstance(model_approach, list), (
        f"'model_approach' must be a list, got: {type(model_approach)}"
    )
    assert len(model_approach) > 0, "'model_approach' must be non-empty when spec has subproblems"
    approach_str = str(model_approach)
    assert "integer linear programming" in approach_str or "Resource Allocation" in approach_str, (
        f"SP1 title/approach not found in model_approach: {model_approach}"
    )
    assert "dynamic programming on DAG" in approach_str or "Route Optimization" in approach_str, (
        f"SP2 title/approach not found in model_approach: {model_approach}"
    )


# ---------------------------------------------------------------------------
# Test 3: graceful degradation — model_spec=None
# ---------------------------------------------------------------------------

def test_results_facts_without_spec_degrade() -> None:
    """When model_spec=None, results facts must:
    - still contain the real metrics (no crash)
    - have model_approach as [] or absent (not raise)
    """
    agent = PaperWriterAgent(llm_provider=None)
    context = _make_context()
    metrics = _make_real_metrics()

    facts = agent._facts_for_section(
        name="results",
        context=context,
        metrics=metrics,
        claims=[],
        model_spec=None,
    )

    # No crash — that's implicit from reaching here.
    # metrics must still be present
    assert "metrics" in facts, (
        f"'metrics' must still be present even without model_spec; got: {list(facts.keys())}"
    )
    assert "coverage_rate" in facts["metrics"], (
        f"Real metric 'coverage_rate' must be present even without model_spec; got: {facts['metrics']}"
    )

    # model_approach must either be absent or be an empty list
    if "model_approach" in facts:
        assert facts["model_approach"] == [], (
            f"Without spec, model_approach must be [] if present; got: {facts['model_approach']}"
        )


# ---------------------------------------------------------------------------
# Test 4: sensitivity also degrades gracefully without spec
# ---------------------------------------------------------------------------

def test_sensitivity_facts_without_spec_degrade() -> None:
    """When model_spec=None, sensitivity facts must not crash and must contain
    validation; model_approach must be [] or absent.
    """
    agent = PaperWriterAgent(llm_provider=None)
    context = _make_context()
    metrics = {}

    facts = agent._facts_for_section(
        name="sensitivity",
        context=context,
        metrics=metrics,
        claims=[],
        model_spec=None,
    )

    # validation still present
    assert "validation" in facts, (
        f"'validation' must still be present without model_spec; got: {list(facts.keys())}"
    )

    # model_approach absent or []
    if "model_approach" in facts:
        assert facts["model_approach"] == [], (
            f"Without spec, model_approach must be [] if present; got: {facts['model_approach']}"
        )


# ---------------------------------------------------------------------------
# SC4 Tests: per-subproblem grouping in results facts
# ---------------------------------------------------------------------------

import json  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402
def _make_two_sub_spec() -> ModelSpec:
    """2-subproblem spec with ids q1 and q2."""
    return ModelSpec(
        version=1,
        problem_restatement="Multi-task problem.",
        subproblems=[
            SubproblemModel(
                subproblem_id="q1",
                title="Task 1 Ranking",
                approach="Weighted scoring model",
                variables=[],
                assumptions=["Independent scores"],
                equations=[],
                algorithm_steps=[],
                metrics=["acc"],
            ),
            SubproblemModel(
                subproblem_id="q2",
                title="Task 2 Prediction",
                approach="Random Forest regression",
                variables=[],
                assumptions=["i.i.d. samples"],
                equations=[],
                algorithm_steps=[],
                metrics=["rmse"],
            ),
        ],
    )


def test_results_facts_grouped_by_subproblem() -> None:
    """_facts_for_section('results') with nested model_metrics.json + 2-sub spec
    must return facts with per_subproblem of length 2, each entry carrying its
    own metrics (q1→acc, q2→rmse) and its title/approach.
    """
    agent = PaperWriterAgent(llm_provider=None)
    context = _make_context()
    spec = _make_two_sub_spec()

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        results_dir = ws / "results"
        results_dir.mkdir(parents=True)

        # Write nested model_metrics.json (the SC2 format)
        nested = {"q1": {"acc": 0.8}, "q2": {"rmse": 1.2}}
        (results_dir / "model_metrics.json").write_text(json.dumps(nested), encoding="utf-8")

        # Flat metrics (as produced by flatten_metrics) passed to _facts_for_section
        flat_metrics = {"q1_acc": 0.8, "q2_rmse": 1.2}

        facts = agent._facts_for_section(
            name="results",
            context=context,
            metrics=flat_metrics,
            claims=[],
            model_spec=spec,
            workspace_root=ws,
        )

    # per_subproblem must exist and have length 2
    assert "per_subproblem" in facts, (
        f"'per_subproblem' key missing from results facts; got: {list(facts.keys())}"
    )
    per_sub = facts["per_subproblem"]
    assert isinstance(per_sub, list), f"per_subproblem must be a list, got: {type(per_sub)}"
    assert len(per_sub) == 2, f"Expected 2 entries in per_subproblem, got: {len(per_sub)}"

    # First entry is q1
    q1_entry = next((e for e in per_sub if e.get("subproblem") == "Task 1 Ranking"), None)
    assert q1_entry is not None, f"No entry for 'Task 1 Ranking' in per_subproblem: {per_sub}"
    assert "acc" in q1_entry["metrics"], (
        f"q1 entry missing 'acc' metric; got: {q1_entry['metrics']}"
    )
    assert "rmse" not in q1_entry["metrics"], (
        f"q1 entry must NOT contain q2's 'rmse'; got: {q1_entry['metrics']}"
    )
    assert q1_entry.get("approach") == "Weighted scoring model", (
        f"q1 approach mismatch: {q1_entry.get('approach')!r}"
    )

    # Second entry is q2
    q2_entry = next((e for e in per_sub if e.get("subproblem") == "Task 2 Prediction"), None)
    assert q2_entry is not None, f"No entry for 'Task 2 Prediction' in per_subproblem: {per_sub}"
    assert "rmse" in q2_entry["metrics"], (
        f"q2 entry missing 'rmse' metric; got: {q2_entry['metrics']}"
    )
    assert "acc" not in q2_entry["metrics"], (
        f"q2 entry must NOT contain q1's 'acc'; got: {q2_entry['metrics']}"
    )
    assert q2_entry.get("approach") == "Random Forest regression", (
        f"q2 approach mismatch: {q2_entry.get('approach')!r}"
    )

    # Back-compat: existing keys must still be present
    assert "metrics" in facts, "'metrics' key must still be present for back-compat"
    assert "instruction" in facts, "'instruction' key must still be present"


def test_results_facts_single_subproblem_unchanged() -> None:
    """With one subproblem and flat metrics, results facts must not crash
    and must still have the 'metrics' key (back-compat); per_subproblem may
    be a single-element list or absent — either is acceptable.
    """
    agent = PaperWriterAgent(llm_provider=None)
    context = _make_context()

    # Single subproblem spec
    single_spec = ModelSpec(
        version=1,
        problem_restatement="Single task problem.",
        subproblems=[
            SubproblemModel(
                subproblem_id="q1",
                title="Ranking Task",
                approach="Weighted scoring",
                variables=[],
                assumptions=[],
                equations=[],
                algorithm_steps=[],
                metrics=["coverage_rate"],
            ),
        ],
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        results_dir = ws / "results"
        results_dir.mkdir(parents=True)

        # Flat metrics only (as used before SC2)
        flat_metrics = {"coverage_rate": 0.92, "travel_time_reduction": 0.15}

        facts = agent._facts_for_section(
            name="results",
            context=context,
            metrics=flat_metrics,
            claims=[],
            model_spec=single_spec,
            workspace_root=ws,
        )

    # Must not crash and must have 'metrics' for back-compat
    assert "metrics" in facts, f"'metrics' must be present; got: {list(facts.keys())}"
    assert facts["metrics"] == flat_metrics or "coverage_rate" in str(facts["metrics"]), (
        f"Flat metrics must be passed through; got: {facts['metrics']}"
    )

    # per_subproblem, if present, must be a list of length <= 1
    if "per_subproblem" in facts:
        assert len(facts["per_subproblem"]) <= 1, (
            f"Single-sub: per_subproblem must have <=1 entry, got {len(facts['per_subproblem'])}"
        )
