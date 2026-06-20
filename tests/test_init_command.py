from pathlib import Path

from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workspace import create_workspace, load_workspace_state


def test_init_requires_llm_key(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    session = InteractiveSession(workspace.root)

    result = session.run_once("/init")

    assert "--llm-key" in result.message  # shows configuration guidance
    assert "--from-env" in result.message  # both modes offered
    assert load_workspace_state(workspace.root).init.completed is False


def test_init_from_env_copies_env_file(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    src = tmp_path / "my.env"
    src.write_text(
        "MAG_LLM_API_KEY=sk-fromfile\nMAG_LLM_BASE_URL=https://api.deepseek.com/v1\n",
        encoding="utf-8",
    )
    session = InteractiveSession(workspace.root)

    result = session.run_once(f"/init --from-env {src}")

    env = (workspace.root / ".env").read_text(encoding="utf-8")
    assert "MAG_LLM_API_KEY=sk-fromfile" in env
    assert "复制" in result.message
    assert load_workspace_state(workspace.root).init.llm_configured is True


def test_init_llm_key_preserves_existing_base_url_and_model(tmp_path: Path) -> None:
    """/init --llm-key (no --llm-base-url) must NOT wipe a base_url/model set earlier
    (e.g. by an /api preset). Otherwise a DeepSeek key is silently sent to OpenAI -> 401."""
    workspace = create_workspace(tmp_path / "workspace")
    from mcm_agent.config import load_settings
    from mcm_agent.core.config_writer import set_env_var

    set_env_var(workspace.root, "MAG_LLM_BASE_URL", "https://api.deepseek.com/v1")
    set_env_var(workspace.root, "MAG_LLM_MODEL", "deepseek-v4-flash")
    session = InteractiveSession(workspace.root)

    session.run_once("/init --llm-key sk-deepseek-123")

    settings = load_settings(workspace_root=workspace.root)
    assert settings.openai_api_key == "sk-deepseek-123"
    assert settings.openai_base_url == "https://api.deepseek.com/v1"  # preserved
    assert settings.openai_model == "deepseek-v4-flash"  # preserved


def test_init_from_env_missing_file(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    session = InteractiveSession(workspace.root)

    result = session.run_once(f"/init --from-env {tmp_path / 'nope.env'}")

    assert "未找到" in result.message
    assert load_workspace_state(workspace.root).init.completed is False


def test_init_interactive_import_env(tmp_path: Path) -> None:
    from mcm_agent.cli_commands.base import CommandContext
    from mcm_agent.cli_commands.init import InitCommand

    workspace = create_workspace(tmp_path / "workspace")
    src = tmp_path / "team.env"
    src.write_text("MAG_LLM_API_KEY=sk-team\n", encoding="utf-8")
    answers = iter(["1", str(src)])

    InitCommand().run(
        [], CommandContext(workspace_root=workspace.root, ask=lambda prompt="": next(answers))
    )

    assert "MAG_LLM_API_KEY=sk-team" in (workspace.root / ".env").read_text(encoding="utf-8")
    assert load_workspace_state(workspace.root).init.llm_configured is True


def test_init_interactive_manual_preset(tmp_path: Path) -> None:
    from mcm_agent.cli_commands.base import CommandContext
    from mcm_agent.cli_commands.init import InitCommand

    workspace = create_workspace(tmp_path / "workspace")
    # init menu 2 (manual) -> preset 1 (DeepSeek OpenAI) -> key -> model
    answers = iter(["2", "1", "sk-manual", "deepseek-v4-flash"])

    InitCommand().run(
        [], CommandContext(workspace_root=workspace.root, ask=lambda prompt="": next(answers))
    )

    env = (workspace.root / ".env").read_text(encoding="utf-8")
    assert "MAG_LLM_API_KEY=sk-manual" in env
    assert "MAG_LLM_BASE_URL=https://api.deepseek.com/v1" in env
    assert "MAG_LLM_MODEL=deepseek-v4-flash" in env
    assert "MAG_LLM_PROTOCOL=openai" in env


def test_init_with_llm_key_marks_workspace_complete(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    session = InteractiveSession(workspace.root)

    result = session.run_once("/init --llm-key test-key")

    state = load_workspace_state(workspace.root)
    assert "Init complete" in result.message
    assert "MAG_LLM_API_KEY=test-key" in (workspace.root / ".env").read_text(encoding="utf-8")
    assert state.init.llm_configured is True
    assert state.init.completed is True
    assert state.phase == "init_complete"


def test_init_writes_full_llm_config(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    session = InteractiveSession(workspace.root)

    session.run_once(
        "/init --llm-key sk-deepseek "
        "--llm-base-url https://api.deepseek.com/v1 "
        "--llm-model deepseek-v4-flash"
    )

    env_text = (workspace.root / ".env").read_text(encoding="utf-8")
    assert "MAG_LLM_API_KEY=sk-deepseek" in env_text
    assert "MAG_LLM_BASE_URL=https://api.deepseek.com/v1" in env_text
    assert "MAG_LLM_MODEL=deepseek-v4-flash" in env_text


def test_second_init_warns_and_offers_reset_options(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    session = InteractiveSession(workspace.root)
    session.run_once("/init --llm-key test-key")

    result = session.run_once("/init")

    assert "already been initialized" in result.message
    assert "/init rethink" in result.message
    assert "/init full-reset RESET" in result.message


def test_init_rethink_clears_work_and_output_but_keeps_inputs(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    (workspace.root / "input/problem/problem.md").write_text("problem", encoding="utf-8")
    (workspace.root / "knowledge/papers/paper.md").write_text("paper", encoding="utf-8")
    (workspace.root / "work/results/result.json").write_text("{}", encoding="utf-8")
    (workspace.root / "output/draft/main.pdf").write_text("pdf", encoding="utf-8")
    session = InteractiveSession(workspace.root)
    session.run_once("/init --llm-key test-key")

    result = session.run_once("/init rethink")

    assert "Re-think complete" in result.message
    assert (workspace.root / "input/problem/problem.md").exists()
    assert (workspace.root / "knowledge/papers/paper.md").exists()
    assert not (workspace.root / "work/results/result.json").exists()
    assert not (workspace.root / "output/draft/main.pdf").exists()


def test_reset_rethink_command_clears_generated_history(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    (workspace.root / "input/problem/problem.md").write_text("problem", encoding="utf-8")
    (workspace.root / "work/results/result.json").write_text("{}", encoding="utf-8")
    session = InteractiveSession(workspace.root)

    result = session.run_once("/reset rethink")

    assert "Re-think reset complete" in result.message
    assert (workspace.root / "input/problem/problem.md").exists()
    assert not (workspace.root / "work/results/result.json").exists()


def test_init_full_reset_requires_reset_word(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    (workspace.root / "input/problem/problem.md").write_text("problem", encoding="utf-8")
    session = InteractiveSession(workspace.root)

    result = session.run_once("/init full-reset")

    assert "--llm-key" in result.message  # falls through to config guidance, does not reset
    assert (workspace.root / "input/problem/problem.md").exists()


def test_init_full_reset_recreates_workspace(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    (workspace.root / "input/problem/problem.md").write_text("problem", encoding="utf-8")
    session = InteractiveSession(workspace.root)

    result = session.run_once("/init full-reset RESET")

    assert "Workspace fully reset" in result.message
    assert not (workspace.root / "input/problem/problem.md").exists()
    assert (workspace.root / ".mag/workspace.json").exists()
    assert (workspace.root / ".git").exists()
