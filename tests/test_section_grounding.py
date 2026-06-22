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
