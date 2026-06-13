import json
from pathlib import Path

from typer.testing import CliRunner

from mcm_agent.cli import app
from mcm_agent.utils.json_io import read_json


EXAMPLE_ROOT = Path("examples/demo_mcm_task")


def test_example_demo_task_files_are_present() -> None:
    assert (EXAMPLE_ROOT / "problem.md").exists()
    assert (EXAMPLE_ROOT / "attachments" / "city_flood_indicators.csv").exists()
    assert (EXAMPLE_ROOT / "user_idea.md").exists()
    assert (EXAMPLE_ROOT / "skills" / "figure-designer" / "SKILL.md").exists()
    assert (EXAMPLE_ROOT / "skills" / "pre-submission-reviewer" / "SKILL.md").exists()
    assert (EXAMPLE_ROOT / "expected_outputs.md").exists()


def test_example_demo_task_runs_end_to_end(tmp_path: Path) -> None:
    workspace = tmp_path / "demo_workspace"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run",
            str(workspace),
            "--problem-file",
            str(EXAMPLE_ROOT / "problem.md"),
            "--attachment",
            str(EXAMPLE_ROOT / "attachments" / "city_flood_indicators.csv"),
            "--user-idea-file",
            str(EXAMPLE_ROOT / "user_idea.md"),
            "--supervisor-skills-dir",
            str(EXAMPLE_ROOT / "skills"),
            "--auto-approve",
        ],
    )

    assert result.exit_code == 0
    assert (workspace / "paper/main.tex").exists()
    assert (workspace / "figures/fig_q1_prediction.pdf").exists()
    assert (workspace / "review/reviewer_report.md").exists()
    assert (workspace / "review/figure_quality_report.md").exists()
    assert (workspace / "final_submission/AI_use_report.md").exists()
    metrics = read_json(workspace / "results" / "model_metrics.json", {})
    assert metrics["row_count"] == 8
    figure_gate = read_json(workspace / "review" / "figure_gate.json", {})
    assert figure_gate["status"] == "pass"
    stage_ids = [
        json.loads(line)["stage_id"]
        for line in (workspace / "stage_runs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert stage_ids[0] == "intake"
    assert stage_ids[-1] == "final_gatekeeper"
