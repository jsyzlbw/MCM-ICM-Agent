"""PQ2 – Abstract↔Model coherence.

The abstract facts must be derived from the code-derived ModelSpec (the same
source the model section uses), NOT from model_decision_summary (a pre-solve
planning text that can describe a completely different method).

Test strategy
-------------
Build a minimal PaperContext whose model_decision_summary contains the phrase
"Bayesian MCMC" and a ModelSpec whose subproblem approach contains the phrase
"constrained optimization inversion". Assert that:

1. The abstract facts dict contains the ModelSpec approach phrase.
2. The abstract facts dict does NOT contain the model_decision_summary phrase.
3. When no ModelSpec is present the fallback still uses model_decision_summary
   (existing behaviour must be preserved).
"""
from __future__ import annotations

from mcm_agent.agents.paper_context import PaperContext
from mcm_agent.agents.writer import PaperWriterAgent
from mcm_agent.core.model_spec import ModelSpec, SubproblemModel


_SPEC_APPROACH = "constrained optimization inversion"
_PLAN_APPROACH = "Bayesian MCMC"


def _make_context() -> PaperContext:
    return PaperContext(
        problem_summary="Optimize a wildfire suppression network.",
        model_decision_summary=f"We apply {_PLAN_APPROACH} to sample the posterior.",
        direction_summary="Hybrid combinatorial-continuous formulation.",
        validation_summary="RMSE < 0.05 across hold-out scenarios.",
    )


def _make_spec() -> ModelSpec:
    return ModelSpec(
        version=1,
        problem_restatement="Wildfire suppression optimization.",
        subproblems=[
            SubproblemModel(
                subproblem_id="SP1",
                title="Resource Allocation",
                approach=_SPEC_APPROACH,
                variables=[],
                assumptions=["Homogeneous terrain"],
                equations=[],
                algorithm_steps=["Step 1: initialize"],
                metrics=["coverage_rate"],
            )
        ],
    )


def test_abstract_facts_use_model_spec_approach_not_plan() -> None:
    """Abstract facts must reflect the ModelSpec approach, not model_decision_summary."""
    agent = PaperWriterAgent(llm_provider=None)
    context = _make_context()
    spec = _make_spec()

    facts = agent._facts_for_section(
        name="abstract",
        context=context,
        metrics={},
        claims=[],
        model_spec=spec,
    )

    # The ModelSpec approach phrase must appear somewhere in the facts.
    facts_str = str(facts)
    assert _SPEC_APPROACH in facts_str, (
        f"Abstract facts should contain ModelSpec approach '{_SPEC_APPROACH}'; got: {facts_str!r}"
    )

    # The pre-solve planning phrase must NOT appear (that comes from a different source).
    assert _PLAN_APPROACH not in facts_str, (
        f"Abstract facts should NOT contain model_decision_summary phrase '{_PLAN_APPROACH}'; got: {facts_str!r}"
    )


def test_abstract_facts_fallback_when_no_spec() -> None:
    """When no ModelSpec is available the existing fallback (model_decision_summary) is preserved."""
    agent = PaperWriterAgent(llm_provider=None)
    context = _make_context()

    facts = agent._facts_for_section(
        name="abstract",
        context=context,
        metrics={},
        claims=[],
        model_spec=None,
    )

    facts_str = str(facts)
    # Fallback: model_decision_summary content must still appear.
    assert _PLAN_APPROACH in facts_str, (
        f"Fallback abstract facts should contain model_decision_summary phrase '{_PLAN_APPROACH}'; got: {facts_str!r}"
    )
