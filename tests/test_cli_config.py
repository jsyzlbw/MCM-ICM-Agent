from pathlib import Path

from typer.testing import CliRunner

from mcm_agent.cli import app


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
