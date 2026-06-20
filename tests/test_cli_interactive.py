from pathlib import Path

from typer.testing import CliRunner

from mcm_agent.cli import app
from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workspace import create_workspace, load_workspace_state, save_workspace_state


def test_bare_mag_initializes_empty_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, [], input="\n")

    assert result.exit_code == 0
    assert "Mag" in result.output
    assert (tmp_path / ".mag/workspace.json").exists()
    assert (tmp_path / ".git").exists()


def test_bare_mag_rejects_non_empty_non_workspace(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "notes.txt").write_text("keep me", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, [])

    assert result.exit_code == 1
    assert "当前文件夹不为空" in result.output
    assert not (tmp_path / ".mag").exists()


def test_bare_mag_recovers_existing_workspace(tmp_path: Path, monkeypatch) -> None:
    create_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, [], input="\n")

    assert result.exit_code == 0
    assert "Workspace" in result.output
    assert "initialized" in result.output


def test_interactive_help_lists_core_commands(tmp_path: Path) -> None:
    create_workspace(tmp_path)
    session = InteractiveSession(tmp_path)

    result = session.run_once("/help")

    assert "/api" in result.message
    assert "/git" in result.message
    assert "/reset" in result.message
    assert "/status" in result.message


def test_interactive_api_status_reports_missing_llm(tmp_path: Path) -> None:
    create_workspace(tmp_path)
    session = InteractiveSession(tmp_path)

    result = session.run_once("/api")

    assert "LLM" in result.message
    assert "[--]" in result.message  # compact status: LLM not configured


def test_interactive_git_status_reports_checkpoint(tmp_path: Path) -> None:
    create_workspace(tmp_path)
    session = InteractiveSession(tmp_path)

    result = session.run_once("/git")

    assert "Git safety net" in result.message
    assert "Local repository: enabled" in result.message


def test_natural_language_requires_llm(tmp_path: Path) -> None:
    create_workspace(tmp_path)
    session = InteractiveSession(tmp_path)

    result = session.run_once("帮我分析这个题")

    assert "LLM API 尚未配置" in result.message


def test_natural_language_requires_problem_after_llm(tmp_path: Path) -> None:
    create_workspace(tmp_path)
    state = load_workspace_state(tmp_path)
    state.init.llm_configured = True
    save_workspace_state(tmp_path, state)
    session = InteractiveSession(tmp_path)

    result = session.run_once("帮我分析这个题")

    assert "题目尚未导入" in result.message
