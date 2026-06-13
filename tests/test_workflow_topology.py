from mcm_agent.core.stage_policy import (
    DataAvailabilityDecision,
    ReviewFailure,
    route_data_availability,
    route_review_failure,
)
from mcm_agent.core.workflow_graph import build_default_workflow_graph


def test_default_workflow_runs_data_feasibility_before_user_direction() -> None:
    graph = build_default_workflow_graph()

    assert graph.has_edge("problem_understanding", "data_feasibility_scout")
    assert graph.has_edge("data_feasibility_scout", "user_discussion")
    assert not graph.has_edge("problem_understanding", "user_discussion")


def test_default_workflow_contains_review_feedback_loops() -> None:
    graph = build_default_workflow_graph()

    assert graph.next_nodes("final_gatekeeper") == ["submission_packager"]
    assert graph.failure_route("final_gatekeeper", "missing_requirement") == "problem_understanding"
    assert graph.failure_route("final_gatekeeper", "weak_model") == "modeling_council"
    assert graph.failure_route("final_gatekeeper", "bad_figures") == "figure_planning"
    assert graph.failure_route("figure_quality_gate", "visual_or_vector_issue") == "figure_planning"


def test_data_availability_policy_reframes_private_or_missing_data() -> None:
    decision = route_data_availability(
        DataAvailabilityDecision(
            target_dataset="football player salary and bonus contracts",
            availability="private_or_unavailable",
            confidence=0.91,
            reason="Detailed salary and bonus contracts are not publicly disclosed.",
        )
    )

    assert decision.next_stage == "research_reframing"
    assert decision.requires_user_discussion is True
    assert "proxy variables" in decision.recommendation
    assert "change the research question" in decision.recommendation


def test_review_failure_policy_routes_to_responsible_stage() -> None:
    assert (
        route_review_failure(ReviewFailure(category="data", severity="critical")).next_stage
        == "search_data"
    )
    assert (
        route_review_failure(ReviewFailure(category="format", severity="major")).next_stage
        == "typesetting"
    )
