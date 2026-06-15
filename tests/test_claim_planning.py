from pathlib import Path

import pytest
from pydantic import ValidationError

from mcm_agent.core.models import PaperClaimPlanItem


def test_paper_claim_plan_item_accepts_supported_critical_claim() -> None:
    item = PaperClaimPlanItem(
        claim_id="claim_model_route",
        section="paper/sections/model.tex",
        claim_text="The selected route is a multi-criteria evaluation model.",
        claim_type="model_choice",
        evidence_ids=["metric_priority_score_mean"],
        figure_ids=[],
        source_ids=[],
        priority="critical",
    )

    assert item.status == "planned"
    assert item.unresolved_reason == ""
    assert Path(item.section).name == "model.tex"


def test_paper_claim_plan_item_rejects_unsupported_critical_claim() -> None:
    with pytest.raises(
        ValidationError,
        match="critical claim requires evidence, figure, or source",
    ):
        PaperClaimPlanItem(
            claim_id="claim_results_primary",
            section="paper/sections/results.tex",
            claim_text="The optimized policy improves the primary metric.",
            claim_type="metric_result",
            priority="critical",
        )


def test_paper_claim_plan_item_accepts_unresolved_critical_claim_with_reason() -> None:
    item = PaperClaimPlanItem(
        claim_id="claim_unresolved_private_data",
        section="paper/sections/results.tex",
        claim_text="The private salary benchmark could not be verified.",
        claim_type="limitation",
        priority="critical",
        status="unresolved",
        unresolved_reason=(
            "Required salary data is private and no user-provided substitute exists."
        ),
    )

    assert item.status == "unresolved"
    assert "private" in item.unresolved_reason


def test_paper_claim_plan_item_requires_paper_section_path() -> None:
    with pytest.raises(ValidationError, match="section must point to paper/sections"):
        PaperClaimPlanItem(
            claim_id="claim_bad_section",
            section="reports/results.md",
            claim_text="This claim is in the wrong location.",
            claim_type="conclusion",
            evidence_ids=["metric_001"],
            priority="major",
        )
