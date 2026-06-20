from pathlib import Path

from mcm_agent.cli_commands.api import ApiCommand
from mcm_agent.cli_commands.base import CommandContext
from mcm_agent.core.workspace import create_workspace


def test_api_status_only_without_tty(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "w").root

    result = ApiCommand().run([], CommandContext(workspace_root=root))  # ask=None -> status only

    assert "LLM" in result.message
    assert "[--]" in result.message  # compact status shows unconfigured providers


def test_api_interactive_imports_env(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "w").root
    src = tmp_path / "x.env"
    src.write_text("MAG_LLM_API_KEY=sk-x\n", encoding="utf-8")
    answers = iter(["3", str(src)])  # menu: 3 = import .env (single action)

    result = ApiCommand().run(
        [],
        CommandContext(
            workspace_root=root,
            ask=lambda prompt="": next(answers),
            printer=lambda _m: None,
        ),
    )

    assert "MAG_LLM_API_KEY=sk-x" in (root / ".env").read_text(encoding="utf-8")
    assert "复制" in result.message


def test_api_interactive_llm_preset(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "w").root
    answers = iter(["1", "1", "sk-manual", ""])  # 1=LLM -> preset 1 -> key -> default model

    result = ApiCommand().run(
        [],
        CommandContext(
            workspace_root=root,
            ask=lambda prompt="": next(answers),
            printer=lambda _m: None,
        ),
    )

    assert "MAG_LLM_API_KEY=sk-manual" in (root / ".env").read_text(encoding="utf-8")
    assert "已配置" in result.message
