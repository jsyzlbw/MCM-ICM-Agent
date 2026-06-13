from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


DataAvailability = Literal["available", "proxy_required", "private_or_unavailable", "unknown"]
ReviewCategory = Literal[
    "requirement",
    "model",
    "data",
    "evidence",
    "figure",
    "writing",
    "format",
    "originality",
]


class StageRoute(BaseModel):
    next_stage: str
    requires_user_discussion: bool = False
    recommendation: str


class DataAvailabilityDecision(BaseModel):
    target_dataset: str
    availability: DataAvailability
    confidence: float = Field(ge=0, le=1)
    reason: str


class ReviewFailure(BaseModel):
    category: ReviewCategory
    severity: Literal["critical", "major", "minor", "suggestion"]


def route_data_availability(decision: DataAvailabilityDecision) -> StageRoute:
    if decision.availability == "available":
        return StageRoute(
            next_stage="user_discussion",
            recommendation=(
                f"Use `{decision.target_dataset}` as a candidate dataset, but keep source "
                "verification before modeling."
            ),
        )
    if decision.availability == "proxy_required":
        return StageRoute(
            next_stage="user_discussion",
            requires_user_discussion=True,
            recommendation=(
                f"Discuss proxy variables for `{decision.target_dataset}` before locking the "
                "research plan."
            ),
        )
    if decision.availability == "private_or_unavailable" and decision.confidence >= 0.8:
        return StageRoute(
            next_stage="research_reframing",
            requires_user_discussion=True,
            recommendation=(
                f"`{decision.target_dataset}` appears private or unavailable. Propose proxy "
                "variables, use user-provided assumptions only when explicitly confirmed, or "
                "change the research question before modeling."
            ),
        )
    return StageRoute(
        next_stage="search_data",
        recommendation=(
            f"Run deeper search for `{decision.target_dataset}` and record uncertainty before "
            "final user direction."
        ),
    )


def route_review_failure(failure: ReviewFailure) -> StageRoute:
    route_map = {
        "requirement": "problem_understanding",
        "model": "modeling_council",
        "data": "search_data",
        "evidence": "solver_coder",
        "figure": "figure_planning",
        "writing": "paper_writer",
        "format": "typesetting",
        "originality": "paper_writer",
    }
    next_stage = route_map[failure.category]
    return StageRoute(
        next_stage=next_stage,
        requires_user_discussion=failure.severity in {"critical", "major"}
        and failure.category in {"requirement", "model", "data"},
        recommendation=f"Route {failure.category} review failure back to `{next_stage}`.",
    )
