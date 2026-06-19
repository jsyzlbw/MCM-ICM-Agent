from mcm_agent.agents.paper_context import PaperContext
from mcm_agent.agents.paper_sections import render_claim_plan_sections


def test_abstract_hides_internal_route_sentinel() -> None:
    context = PaperContext(
        problem_summary="DWTS voting fairness",
        selected_routes=["llm_generated"],
    )

    sections = render_claim_plan_sections([], context, None)
    abstract = sections["abstract.tex"]

    assert "llm_generated" not in abstract
    assert "problem-specific model" in abstract


def test_abstract_uses_named_routes_when_present() -> None:
    context = PaperContext(
        problem_summary="An evacuation problem",
        selected_routes=["constrained_optimization"],
    )

    sections = render_claim_plan_sections([], context, None)

    assert "constrained\\_optimization" in sections["abstract.tex"]


def test_abstract_is_language_aware() -> None:
    en = render_claim_plan_sections([], PaperContext(problem_summary="DWTS fairness", language="en"), None)
    zh = render_claim_plan_sections([], PaperContext(problem_summary="DWTS 公平性", language="zh"), None)

    assert "This paper develops" in en["abstract.tex"]
    assert "本文采用" in zh["abstract.tex"]
    assert "This paper develops" not in zh["abstract.tex"]


def test_abstract_bounds_long_approach_text() -> None:
    from mcm_agent.core.models import PaperClaimPlanItem

    long_claim = PaperClaimPlanItem(
        claim_id="claim_model_route",
        section="paper/sections/model.tex",
        claim_text="We adopt a two-stage route " + "and more detail " * 80,
        claim_type="model_choice",
        priority="critical",
        evidence_ids=["ev_1"],
    )
    sections = render_claim_plan_sections([long_claim], PaperContext(problem_summary="X"), None)

    # The abstract must not dump the entire 600+ char claim text.
    assert len(sections["abstract.tex"]) < 500
