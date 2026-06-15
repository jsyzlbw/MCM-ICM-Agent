from pathlib import Path
import json

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


def test_provider_status_reads_json_config_file(tmp_path: Path) -> None:
    config_file = tmp_path / "mcm_agent_config.local.json"
    config_file.write_text(
        json.dumps(
            {
                "llm": {"api_key": "json-openai", "model": "json-model"},
                "search": {
                    "tavily_api_key": "json-tavily",
                    "brave_search_api_key": "json-brave",
                },
                "mineru": {"mode": "rest", "api_key": "json-mineru"},
                "humanizer": {"api_key": "json-humanizer"},
            }
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["provider-status", "--config-file", str(config_file)])

    assert result.exit_code == 0
    assert "LLM: openai-compatible (json-model)" in result.output
    assert "Search: Tavily API + Brave API" in result.output
    assert "MinerU: rest" in result.output
    assert "Humanizer: UShallPass API" in result.output


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
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {"selected_routes": ["multi_criteria_evaluation"], "route_metrics": {}},
    )
    write_json(
        workspace.root / "final_submission" / "submission_manifest.json",
        {"model_routes": ["multi_criteria_evaluation"], "audit_files": []},
    )
    runner = CliRunner()

    result = runner.invoke(app, ["inspect", str(workspace.root)])

    assert result.exit_code == 0
    assert "Current phase: validation_gate" in result.output
    assert "Failed gate: validation_gate" in result.output
    assert "Repair stage: solver_coder" in result.output
    assert "Model routes: multi_criteria_evaluation" in result.output
    assert "Submission manifest: present" in result.output
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


def test_package_command_creates_submission_manifest(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    (workspace.root / "paper" / "main.pdf").write_bytes(b"%PDF")
    (workspace.root / "review" / "reference_audit_report.md").write_text(
        "# Reference Audit Report\n\nMissing references: 0\n",
        encoding="utf-8",
    )
    write_json(workspace.root / "figures" / "figure_registry.json", [])
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {"selected_routes": ["balanced_contest_route"], "route_metrics": {}},
    )
    runner = CliRunner()

    result = runner.invoke(app, ["package", str(workspace.root)])

    assert result.exit_code == 0
    assert "Submission package created" in result.output
    assert (workspace.root / "final_submission" / "submission_manifest.json").exists()
