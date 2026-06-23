"""TDD regression test: /api must set llm_configured in workspace state.

Bug: After /api configures LLM, chat was still blocked with
"LLM API 尚未配置。请先运行 /api 或 /init。" because ApiCommand never
updated state.init.llm_configured — only /init's _finalize did that.

Fix verified by this test: both choice "1" (LLM preset) and choice "3"
(import .env) must persist llm_configured=True after a successful config.
"""
from __future__ import annotations

from pathlib import Path


from mcm_agent.cli_commands.api import ApiCommand
from mcm_agent.cli_commands.base import CommandContext
from mcm_agent.core.dialogue_guard import DialogueGuard
from mcm_agent.core.workspace import create_workspace, load_workspace_state


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_queue_ask(answers: list[str]):
    """Return a fake `ask` that returns successive answers from the list."""
    it = iter(answers)

    def _ask(prompt: str = "") -> str:  # noqa: ARG001
        return next(it)

    return _ask


# ---------------------------------------------------------------------------
# Choice "1" (LLM preset) — the primary bug path
# ---------------------------------------------------------------------------

def test_api_choice1_sets_llm_configured(tmp_path: Path) -> None:
    """Selecting [1] LLM and entering a key must flip llm_configured to True."""
    root = create_workspace(tmp_path / "w").root

    # Confirm precondition: flag is False before /api
    assert load_workspace_state(root).init.llm_configured is False

    # Drive /api → "1" (LLM) → "1" (DeepSeek preset) → key → default model
    answers = ["1", "1", "sk-test-deepseek-key", ""]
    ApiCommand().run(
        [],
        CommandContext(
            workspace_root=root,
            ask=_make_queue_ask(answers),
            printer=lambda _: None,
        ),
    )

    state = load_workspace_state(root)
    assert state.init.llm_configured is True, (
        "llm_configured must be True after /api choice '1' successfully writes a key"
    )


def test_api_choice1_unblocks_dialogue_guard(tmp_path: Path) -> None:
    """After /api choice '1', DialogueGuard must not block with 尚未配置."""
    root = create_workspace(tmp_path / "w").root

    answers = ["1", "1", "sk-test-deepseek-key", ""]
    ApiCommand().run(
        [],
        CommandContext(
            workspace_root=root,
            ask=_make_queue_ask(answers),
            printer=lambda _: None,
        ),
    )

    state = load_workspace_state(root)
    guard = DialogueGuard.evaluate(state, "你好")
    # The guard may block for other reasons (problem not imported), but it must
    # NOT block specifically because LLM is unconfigured.
    assert "尚未配置" not in guard.message, (
        f"DialogueGuard still blocks with LLM-not-configured message: {guard.message!r}"
    )


# ---------------------------------------------------------------------------
# Choice "3" (import .env) — secondary bug path
# ---------------------------------------------------------------------------

def test_api_choice3_sets_llm_configured_when_env_has_key(tmp_path: Path) -> None:
    """Importing a .env that contains MAG_LLM_API_KEY must flip llm_configured."""
    root = create_workspace(tmp_path / "w").root

    # Prepare a .env with a real-looking key
    src_env = tmp_path / "my.env"
    src_env.write_text("MAG_LLM_API_KEY=sk-imported-key\n", encoding="utf-8")

    answers = ["3", str(src_env)]
    ApiCommand().run(
        [],
        CommandContext(
            workspace_root=root,
            ask=_make_queue_ask(answers),
            printer=lambda _: None,
        ),
    )

    state = load_workspace_state(root)
    assert state.init.llm_configured is True, (
        "llm_configured must be True after /api choice '3' imports .env with MAG_LLM_API_KEY"
    )


def test_api_choice3_stays_false_when_env_has_no_key(tmp_path: Path) -> None:
    """Importing a .env WITHOUT MAG_LLM_API_KEY must NOT set llm_configured."""
    root = create_workspace(tmp_path / "w").root

    src_env = tmp_path / "no-llm.env"
    src_env.write_text("SOME_OTHER_KEY=abc\n", encoding="utf-8")

    answers = ["3", str(src_env)]
    ApiCommand().run(
        [],
        CommandContext(
            workspace_root=root,
            ask=_make_queue_ask(answers),
            printer=lambda _: None,
        ),
    )

    state = load_workspace_state(root)
    assert state.init.llm_configured is False, (
        "llm_configured must stay False when imported .env has no MAG_LLM_API_KEY"
    )
