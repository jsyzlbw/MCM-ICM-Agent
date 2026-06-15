from pathlib import Path

import pytest
from pydantic import ValidationError

from mcm_agent.agents.claim_planning import ClaimPlanningAgent
from mcm_agent.core.models import PaperClaimPlanItem
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json, write_json


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


def test_claim_planning_agent_writes_model_result_and_conclusion_claims(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {
            "selected_routes": ["multi_criteria_evaluation"],
            "route_metrics": {
                "priority_score_mean": {
                    "route_id": "multi_criteria_evaluation",
                    "value": 0.6,
                },
            },
        },
    )
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [
            {
                "evidence_id": "metric_priority_score_mean",
                "claim": "Route metric priority_score_mean equals 0.6.",
                "verified": True,
            }
        ],
    )
    write_json(
        workspace.root / "figures" / "figure_registry.json",
        [
            {
                "figure_id": "fig_priority_ranking",
                "status": "approved",
                "claim_supported": "Priority ranking supports the main result.",
                "evidence_ids": ["metric_priority_score_mean"],
                "source_ids": ["web_001"],
            }
        ],
    )
    write_json(workspace.root / "data" / "source_registry.json", [{"source_id": "web_001"}])
    (workspace.root / "reports" / "validation_report.md").write_text(
        "# Validation Report\n\nAll validation checks passed.\n",
        encoding="utf-8",
    )

    ClaimPlanningAgent().run(workspace.root)

    plan = read_json(workspace.root / "paper" / "claim_plan.json", [])
    claim_ids = {item["claim_id"] for item in plan}
    assert "claim_model_route" in claim_ids
    assert "claim_metric_priority_score_mean" in claim_ids
    assert "claim_conclusion_traceability" in claim_ids
    assert all(item["status"] == "planned" for item in plan)
    assert (workspace.root / "review" / "claim_plan_report.md").exists()


def test_claim_planning_agent_marks_missing_evidence_as_unresolved(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {"selected_routes": ["forecasting_baseline"], "route_metrics": {}},
    )
    write_json(workspace.root / "results" / "evidence_registry.json", [])
    write_json(workspace.root / "figures" / "figure_registry.json", [])
    write_json(workspace.root / "data" / "source_registry.json", [])

    ClaimPlanningAgent().run(workspace.root)

    plan = read_json(workspace.root / "paper" / "claim_plan.json", [])
    unresolved = [item for item in plan if item["status"] == "unresolved"]
    assert unresolved
    assert any(item["priority"] == "critical" for item in unresolved)
    assert "Missing verified evidence" in unresolved[0]["unresolved_reason"]


def test_claim_planning_agent_adds_sensitivity_claim_when_evidence_exists(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {"selected_routes": ["multi_criteria_evaluation"], "route_metrics": {}},
    )
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [
            {
                "evidence_id": "metric_priority_score_mean",
                "claim": "Route metric priority_score_mean equals 0.6.",
                "verified": True,
            }
        ],
    )
    write_json(
        workspace.root / "figures" / "figure_registry.json",
        [{"figure_id": "fig_priority_ranking", "status": "approved"}],
    )
    write_json(workspace.root / "data" / "source_registry.json", [{"source_id": "web_001"}])

    ClaimPlanningAgent().run(workspace.root)

    plan = read_json(workspace.root / "paper" / "claim_plan.json", [])
    sensitivity_claim = next(
        item for item in plan if item["claim_id"] == "claim_sensitivity_baseline"
    )
    assert sensitivity_claim["section"] == "paper/sections/sensitivity.tex"
    assert sensitivity_claim["claim_type"] == "sensitivity"
    assert sensitivity_claim["evidence_ids"] == ["metric_priority_score_mean"]
