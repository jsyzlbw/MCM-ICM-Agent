from pathlib import Path

from mcm_agent.agents.paper_context import build_paper_context
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import write_json


def test_build_paper_context_reads_core_paper_inputs(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "problem_understanding.md").write_text(
        "# Problem Understanding\n\nNeed a resilient evacuation allocation model.",
        encoding="utf-8",
    )
    (workspace.root / "discussion" / "confirmed_direction.md").write_text(
        "# Confirmed Direction\n\nUse interpretable optimization.",
        encoding="utf-8",
    )
    (workspace.root / "reports" / "model_decision.md").write_text(
        "# Model Decision\n\nSelected constrained optimization with TOPSIS ranking.",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {
            "selected_routes": ["multi_criteria_evaluation", "constrained_optimization"],
            "route_metrics": {"priority_score_mean": {"value": 0.6}},
        },
    )
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [{"evidence_id": "ev_priority", "claim": "Priority score mean equals 0.6."}],
    )
    write_json(
        workspace.root / "figures" / "figure_registry.json",
        [
            {
                "figure_id": "fig_priority",
                "claim_supported": "Priority ranking supports allocation.",
            }
        ],
    )
    write_json(workspace.root / "data" / "source_registry.json", [{"source_id": "web_001"}])

    context = build_paper_context(workspace.root)

    assert "evacuation allocation" in context.problem_summary
    assert "interpretable optimization" in context.direction_summary
    assert context.selected_routes == ["multi_criteria_evaluation", "constrained_optimization"]
    assert context.primary_evidence_ids == ["ev_priority"]
    assert context.primary_figure_ids == ["fig_priority"]
    assert context.primary_source_ids == ["web_001"]


def test_build_paper_context_reads_rag_notes_and_limitations(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "validation_report.md").write_text(
        "# Validation Report\n\nLimitation: private mobility data is unavailable.",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "rag" / "methodology_hits.json",
        [{"title": "Assumption Guide", "content": "State assumptions before model equations."}],
    )

    context = build_paper_context(workspace.root)

    assert "private mobility data" in context.validation_summary
    assert context.methodology_notes == ["Assumption Guide: State assumptions before model equations."]
