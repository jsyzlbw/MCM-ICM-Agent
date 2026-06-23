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


# ---------------------------------------------------------------------------
# Task A2: writer injects judge_feedback from repair_directive
# ---------------------------------------------------------------------------

import json as _json  # noqa: E402
from pathlib import Path as _Path  # noqa: E402
from mcm_agent.providers.base import ProviderResult  # noqa: E402
class _RecordingLLM:
    """Fake LLM that records every prompt it receives and returns a valid section."""

    def __init__(self, name: str = "introduction") -> None:
        self.prompts: list[str] = []
        self._name = name

    def generate(self, system: str, prompt: str, *, temperature: float = 0.2) -> ProviderResult:
        self.prompts.append(prompt)
        # Return a valid LaTeX section so write_section doesn't fall back
        return ProviderResult(
            content="\\section{Introduction}\nThis is a substantive introduction.\n",
            metadata={},
        )


def _make_workspace_with_directive(
    tmp_path: _Path,
    *,
    target_stage: str,
    weak_dimension: str,
    critique: str,
    suggestions: list[str] | None = None,
) -> _Path:
    review_dir = tmp_path / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    directive = {
        "target_stage": target_stage,
        "weak_dimension": weak_dimension,
        "score": 5,
        "critique": critique,
        "suggestions": suggestions or [],
        "iteration": 1,
    }
    (review_dir / "repair_directive.json").write_text(
        _json.dumps(directive), encoding="utf-8"
    )
    return tmp_path


def test_writer_injects_judge_feedback_for_writing_dimension(tmp_path: _Path) -> None:
    """When directive targets paper_writer with weak_dimension=writing,
    PaperWriterAgent must inject judge_feedback into every prose section's facts.

    We assert this at the _facts_for_section level — introduction is a prose section.
    TDD: this test is written before the implementation.
    """
    _make_workspace_with_directive(
        tmp_path,
        target_stage="paper_writer",
        weak_dimension="writing",
        critique="prose is too vague and lacks specifics",
        suggestions=["Add quantitative statements", "Explain each equation"],
    )

    agent = PaperWriterAgent(llm_provider=None)
    context = _make_context()

    facts = agent._facts_for_section(
        name="introduction",
        context=context,
        metrics={},
        claims=[],
        model_spec=None,
        workspace_root=tmp_path,
    )

    assert "judge_feedback" in facts, (
        f"When directive targets paper_writer/writing, introduction facts must contain "
        f"'judge_feedback'; got keys: {list(facts.keys())}"
    )
    jf = facts["judge_feedback"]
    assert isinstance(jf, dict), f"judge_feedback must be a dict, got {type(jf)}"
    assert jf.get("critique") == "prose is too vague and lacks specifics", (
        f"judge_feedback critique mismatch: {jf}"
    )
    assert jf.get("dimension") == "writing", f"judge_feedback dimension mismatch: {jf}"


def test_writer_injects_judge_feedback_for_modeling_dimension(tmp_path: _Path) -> None:
    """When directive targets paper_writer with weak_dimension=modeling,
    judge_feedback must appear in the 'model' section's facts.
    """
    _make_workspace_with_directive(
        tmp_path,
        target_stage="paper_writer",
        weak_dimension="modeling",
        critique="model description lacks mathematical rigor",
        suggestions=["Add equations", "Justify assumptions"],
    )

    agent = PaperWriterAgent(llm_provider=None)
    context = _make_context()

    facts = agent._facts_for_section(
        name="model",
        context=context,
        metrics={},
        claims=[],
        model_spec=None,
        workspace_root=tmp_path,
    )

    assert "judge_feedback" in facts, (
        f"When directive targets paper_writer/modeling, model section facts must contain "
        f"'judge_feedback'; got keys: {list(facts.keys())}"
    )
    jf = facts["judge_feedback"]
    assert jf.get("critique") == "model description lacks mathematical rigor", (
        f"judge_feedback critique mismatch: {jf}"
    )


def test_writer_does_not_inject_for_wrong_stage(tmp_path: _Path) -> None:
    """When directive targets solver_coder (not paper_writer),
    _facts_for_section must NOT inject judge_feedback.
    """
    _make_workspace_with_directive(
        tmp_path,
        target_stage="solver_coder",
        weak_dimension="data_solution",
        critique="data analysis was wrong",
    )

    agent = PaperWriterAgent(llm_provider=None)
    context = _make_context()

    facts = agent._facts_for_section(
        name="introduction",
        context=context,
        metrics={},
        claims=[],
        model_spec=None,
        workspace_root=tmp_path,
    )

    assert "judge_feedback" not in facts, (
        f"When directive targets solver_coder, writer must NOT inject judge_feedback; "
        f"got: {facts}"
    )


def test_writer_does_not_inject_when_no_directive(tmp_path: _Path) -> None:
    """When no repair_directive.json exists, _facts_for_section must NOT inject judge_feedback."""
    agent = PaperWriterAgent(llm_provider=None)
    context = _make_context()

    facts = agent._facts_for_section(
        name="introduction",
        context=context,
        metrics={},
        claims=[],
        model_spec=None,
        workspace_root=tmp_path,
    )

    assert "judge_feedback" not in facts, (
        f"Without repair_directive.json, writer must NOT inject judge_feedback; got: {facts}"
    )


def test_writer_section_loop_passes_exemplars_to_write_section(tmp_path: _Path) -> None:
    """The section loop in _write_claim_plan_sections must pass exemplars=[] to
    write_section (KB seam confirmation). We intercept via a recording PaperSectionWriter.

    TDD: this test is written before the implementation.
    """
    from unittest.mock import patch

    # Set up a minimal workspace so _write_claim_plan_sections can run
    paper_dir = tmp_path / "paper"
    section_dir = paper_dir / "sections"
    section_dir.mkdir(parents=True)
    (tmp_path / "results").mkdir(exist_ok=True)
    (tmp_path / "results" / "model_metrics.json").write_text("{}", encoding="utf-8")
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "source_registry.json").write_text("[]", encoding="utf-8")
    (tmp_path / "figures").mkdir(exist_ok=True)

    recorded_exemplars: list = []

    class _CapturingWriter:
        def write_section(self, name, title, facts, *, exemplars=None):
            recorded_exemplars.append(exemplars)
            return f"\\section{{{title}}}\nContent.\n"

    recording_llm = _RecordingLLM()
    agent = PaperWriterAgent(llm_provider=recording_llm)

    context = _make_context()

    # Patch PaperSectionWriter to use our capturing writer
    with patch("mcm_agent.agents.writer.PaperSectionWriter") as MockWriter:
        MockWriter.return_value = _CapturingWriter()
        agent._write_claim_plan_sections(
            tmp_path,
            section_dir,
            [],  # no claim plan items
            context,
        )

    # Every section call must have passed exemplars (as a list, possibly empty)
    assert len(recorded_exemplars) > 0, "No calls to write_section were recorded"
    for i, ex in enumerate(recorded_exemplars):
        assert isinstance(ex, list), (
            f"Section {i} was called with exemplars={ex!r}; expected a list (KB seam)"
        )
