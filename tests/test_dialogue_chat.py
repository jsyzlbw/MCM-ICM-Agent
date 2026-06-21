"""Tests for the chat discussion path in InteractiveSession.

These tests verify that:
1. After /api + /question (but without /init), natural-language chat goes
   to the LLM — NOT blocked by the "init not complete" advisory (Bug 1).
2. The session correctly blocks when LLM is NOT configured or problem NOT imported.

TDD: written BEFORE the fix in cli_session.py / dialogue_guard.py.
"""
from __future__ import annotations

from pathlib import Path

from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workspace import create_workspace
from mcm_agent.core.workspace_models import WorkspaceState
from mcm_agent.providers.base import ProviderResult


ADVISORY_TEXT = "/init 尚未完全完成"


class _EchoLLM:
    """Minimal fake LLM that echoes the prompt back so we can inspect it."""

    def __init__(self) -> None:
        self.last_prompt = ""
        self.called = False

    def generate(self, system: str, prompt: str) -> ProviderResult:
        self.last_prompt = prompt
        self.called = True
        return ProviderResult(content="LLM_REPLY_HELLO", metadata={})


def _make_session_partial_init(tmp_path: Path) -> tuple[InteractiveSession, _EchoLLM]:
    """Workspace with llm_configured=True, problem_imported=True, completed=False."""
    root = create_workspace(tmp_path / "ws").root

    # Write a problem file so the workspace really has a problem
    problem_dir = root / "input" / "problem"
    problem_dir.mkdir(parents=True, exist_ok=True)
    (problem_dir / "problem.txt").write_text("DWTS: estimate fan votes.", encoding="utf-8")

    # Write workspace state flags
    from mcm_agent.core.workspace import save_workspace_state

    state = WorkspaceState()
    state.init.llm_configured = True
    state.init.problem_imported = True
    state.init.completed = False  # ← the key: /init not finished
    save_workspace_state(root, state)

    session = InteractiveSession(root)
    session.suppress_live_output = True  # avoid spinner / TTY code paths

    llm = _EchoLLM()
    # Monkeypatch so session uses our fake LLM
    session._chat_llm = lambda: llm  # type: ignore[method-assign]

    return session, llm


# ---------------------------------------------------------------------------
# Bug 1: advisory must NOT block when guard.allowed is True
# ---------------------------------------------------------------------------

def test_chat_proceeds_to_llm_when_init_incomplete(tmp_path: Path) -> None:
    """Natural-language chat goes to the LLM even when /init is not complete.

    Previously _handle_natural_language returned the advisory string
    'can continue, /init not done' and never called the LLM.
    """
    session, llm = _make_session_partial_init(tmp_path)

    result = session.run_once("你好")

    # Must NOT return the advisory message
    assert ADVISORY_TEXT not in result.message, (
        f"Chat was blocked by advisory when it should have called LLM.\n"
        f"Got: {result.message!r}"
    )
    # Must have called the LLM
    assert llm.called, "LLM was never called — session short-circuited before the LLM"
    assert "LLM_REPLY_HELLO" in result.message


def test_chat_still_blocked_when_llm_not_configured(tmp_path: Path) -> None:
    """When LLM is not configured the guard blocks and the LLM is never called."""
    root = create_workspace(tmp_path / "ws").root

    from mcm_agent.core.workspace import save_workspace_state

    state = WorkspaceState()
    state.init.llm_configured = False
    state.init.problem_imported = True
    save_workspace_state(root, state)

    session = InteractiveSession(root)
    session.suppress_live_output = True
    llm = _EchoLLM()
    session._chat_llm = lambda: llm  # type: ignore[method-assign]

    result = session.run_once("你好")

    assert not llm.called, "LLM should NOT be called when llm_configured=False"
    assert "LLM API 尚未配置" in result.message


def test_chat_still_blocked_when_problem_not_imported(tmp_path: Path) -> None:
    """When problem is not imported the guard blocks and the LLM is never called."""
    root = create_workspace(tmp_path / "ws").root

    from mcm_agent.core.workspace import save_workspace_state

    state = WorkspaceState()
    state.init.llm_configured = True
    state.init.problem_imported = False
    save_workspace_state(root, state)

    session = InteractiveSession(root)
    session.suppress_live_output = True
    llm = _EchoLLM()
    session._chat_llm = lambda: llm  # type: ignore[method-assign]

    result = session.run_once("你好")

    assert not llm.called, "LLM should NOT be called when problem_imported=False"
    assert "题目尚未导入" in result.message
