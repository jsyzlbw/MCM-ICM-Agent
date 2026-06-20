from pathlib import Path

from mcm_agent.cli_commands.api import ApiCommand
from mcm_agent.cli_commands.base import CommandContext
from mcm_agent.core.workspace import create_workspace


def test_api_status_only_without_tty(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "w").root

    result = ApiCommand().run([], CommandContext(workspace_root=root))  # ask=None -> status

    assert "API status" in result.message
    assert "[missing] LLM" in result.message


def test_api_interactive_imports_env(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "w").root
    src = tmp_path / "x.env"
    src.write_text("MAG_LLM_API_KEY=sk-x\n", encoding="utf-8")
    answers = iter(["1", str(src), "5"])
    out: list[str] = []

    ApiCommand().run(
        [],
        CommandContext(
            workspace_root=root,
            ask=lambda prompt="": next(answers),
            printer=out.append,
        ),
    )

    assert "MAG_LLM_API_KEY=sk-x" in (root / ".env").read_text(encoding="utf-8")
    assert any("复制" in line for line in out)


def test_api_interactive_manual_llm(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "w").root
    answers = iter(["2", "sk-manual", "", "", "5"])

    ApiCommand().run(
        [],
        CommandContext(
            workspace_root=root,
            ask=lambda prompt="": next(answers),
            printer=lambda _m: None,
        ),
    )

    assert "MAG_LLM_API_KEY=sk-manual" in (root / ".env").read_text(encoding="utf-8")
