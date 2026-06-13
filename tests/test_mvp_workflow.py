from pathlib import Path

from mcm_agent.workflows.mvp import run_demo_workflow
from mcm_agent.utils.json_io import read_json


def test_run_demo_workflow_creates_required_artifacts(tmp_path: Path) -> None:
    workspace = tmp_path / "demo"

    run_demo_workflow(workspace, auto_approve=True)

    required = [
        "reports/problem_understanding.md",
        "reports/model_candidates.md",
        "reports/model_decision.md",
        "reports/experiment_plan.md",
        "data/source_registry.json",
        "data/retrieval_log.jsonl",
        "rag/methodology_hits.json",
        "reports/data_profile.md",
        "results/model_metrics.json",
        "results/evidence_registry.json",
        "reports/validation_report.md",
        "figures/figure_plan.json",
        "figures/figure_registry.json",
        "paper/main.tex",
        "review/originality_report.md",
        "review/humanization_diff.md",
        "review/fact_regression_report.md",
        "review/reviewer_report.md",
        "review/methodology_checklist_report.md",
        "final_submission/AI_use_report.md",
    ]
    for relative_path in required:
        assert (workspace / relative_path).exists(), relative_path

    state = read_json(workspace / "task_state.json", {})
    assert [item for item in state["checkpoints"] if item["status"] == "pending"] == []
