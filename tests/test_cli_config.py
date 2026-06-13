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
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["provider-status", "--env-file", str(env_file)])

    assert result.exit_code == 0
    assert "LLM: openai-compatible (test-model)" in result.output
    assert "Search: Tavily API" in result.output
    assert "Extract: Firecrawl API" in result.output
