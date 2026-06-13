from pathlib import Path

from typer.testing import CliRunner

from mcm_agent.cli import app
from mcm_agent.core.gate_decision import GateDecision, record_gate_decision
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import append_jsonl, read_json, write_json


def test_provider_status_reports_fake_and_real_providers(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=test-openai",
                "OPENAI_MODEL=test-model",
                "TAVILY_API_KEY=test-tavily",
                "FIRECRAWL_API_KEY=test-firecrawl",
                "BRAVE_SEARCH_API_KEY=test-brave",
                "EXA_API_KEY=test-exa",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["provider-status", "--env-file", str(env_file)])

    assert result.exit_code == 0
    assert "LLM: openai-compatible (test-model)" in result.output
    assert "Search: Tavily API + Brave API + Exa API" in result.output
    assert "Extract: Firecrawl API" in result.output


def test_run_command_creates_workspace_from_problem_and_attachment(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    problem = tmp_path / "problem.md"
    attachment = tmp_path / "data.csv"
    problem.write_text("# Problem\n\nBuild a model.", encoding="utf-8")
    attachment.write_text("x,y\n1,2\n2,3\n", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run",
            str(workspace),
            "--problem-file",
            str(problem),
            "--attachment",
            str(attachment),
            "--auto-approve",
        ],
    )

    assert result.exit_code == 0
    assert "Workflow completed" in result.output
    assert (workspace / "paper/main.tex").exists()
    assert (workspace / "final_submission/AI_use_report.md").exists()


def test_inspect_command_reports_stage_and_failed_gate(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    state = read_json(workspace.root / "task_state.json", {})
    state["current_phase"] = "validation_gate"
    write_json(workspace.root / "task_state.json", state)
    record_gate_decision(
        workspace.root,
        "validation_gate.json",
        GateDecision(
            gate_id="validation_gate",
            status="fail",
            failure_reason="bad_results",
            repair_stage="solver_coder",
            blocking_findings=["Missing metric evidence."],
        ),
    )
    append_jsonl(
        workspace.root / "stage_runs.jsonl",
        {"stage_id": "validation_gate", "status": "passed", "next_stage": "solver_coder"},
    )
    runner = CliRunner()

    result = runner.invoke(app, ["inspect", str(workspace.root)])

    assert result.exit_code == 0
    assert "Current phase: validation_gate" in result.output
    assert "Failed gate: validation_gate" in result.output
    assert "Repair stage: solver_coder" in result.output
    assert "Recent stages:" in result.output


def test_resume_command_runs_from_requested_stage(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    problem = tmp_path / "problem.md"
    attachment = tmp_path / "data.csv"
    problem.write_text("# Problem\n\nBuild a model.", encoding="utf-8")
    attachment.write_text("x,y\n1,2\n2,3\n", encoding="utf-8")
    runner = CliRunner()
    first = runner.invoke(
        app,
        [
            "run",
            str(workspace),
            "--problem-file",
            str(problem),
            "--attachment",
            str(attachment),
            "--auto-approve",
        ],
    )
    assert first.exit_code == 0

    resumed = runner.invoke(
        app,
        [
            "resume",
            str(workspace),
            "--problem-file",
            str(problem),
            "--attachment",
            str(attachment),
            "--from-stage",
            "validation_gate",
            "--until-stage",
            "final_gatekeeper",
            "--auto-approve",
        ],
    )

    assert resumed.exit_code == 0
    assert "Resumed workflow" in resumed.output
    stage_ids = [
        line
        for line in (workspace / "stage_runs.jsonl").read_text(encoding="utf-8").splitlines()
        if '"stage_id": "validation_gate"' in line
    ]
    assert len(stage_ids) >= 2
