from pathlib import Path

from mcm_agent.workflows.demo_report import build_demo_report


def test_build_demo_report_summarizes_workspace_outputs(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "review").mkdir(parents=True)
    (workspace / "figures").mkdir(parents=True)
    (workspace / "results").mkdir(parents=True)
    (workspace / "paper").mkdir(parents=True)
    (workspace / "stage_runs.jsonl").write_text(
        '{"stage_id":"intake","status":"passed"}\n'
        '{"stage_id":"final_gatekeeper","status":"passed"}\n',
        encoding="utf-8",
    )
    (workspace / "review" / "figure_gate.json").write_text(
        '{"status":"pass"}',
        encoding="utf-8",
    )
    (workspace / "review" / "final_gate.json").write_text(
        '{"status":"pass"}',
        encoding="utf-8",
    )
    (workspace / "results" / "model_metrics.json").write_text(
        '{"row_count":8}',
        encoding="utf-8",
    )
    (workspace / "figures" / "fig_q1_prediction.pdf").write_text("pdf", encoding="utf-8")
    (workspace / "paper" / "main.tex").write_text("\\documentclass{article}", encoding="utf-8")

    report = build_demo_report(workspace)

    assert "# Demo Run Report" in report
    assert "Stage count: 2" in report
    assert "Figure gate: pass" in report
    assert "Final gate: pass" in report
    assert "row_count: 8" in report
