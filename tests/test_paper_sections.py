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
