"""TDD tests for TUI-4: streaming LLM chat into the Textual log.

Tests:
  A. NL chat with a streaming LLM → LLMStreamBlock accumulates tokens, log
     contains concatenated text after finalize.
  B. NL chat with a non-streaming LLM (no generate_stream) → fallback path
     still renders a reply.
  C. Assistant reply is recorded to session_store after streaming.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from mcm_agent.cli_commands.base import CommandResult
from mcm_agent.core.workspace import create_workspace
from mcm_agent.cli_session import InteractiveSession
from mcm_agent.tui.textual_app import MagTuiApp, ChatTextArea, LLMStreamBlock


# ---------------------------------------------------------------------------
# Fake LLM providers
# ---------------------------------------------------------------------------


class _StreamingFakeLLM:
    """Fake LLM that HAS generate_stream, yields tokens."""

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    def generate(self, system: str, prompt: str):
        raise NotImplementedError("should not be called on streaming path")

    def generate_stream(self, system: str, prompt: str):
        yield from self._chunks


class _NonStreamingFakeLLM:
    """Fake LLM WITHOUT generate_stream — fallback path."""

    def __init__(self, reply: str) -> None:
        self._reply = reply

    def generate(self, system: str, prompt: str):
        # Return an object with .content (matching provider interface)
        class _Resp:
            def __init__(self, text):
                self.content = text
        return _Resp(self._reply)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(tmp_path: Path) -> InteractiveSession:
    """Create a fresh workspace + session with a completed /start state so
    DialogueGuard allows chat without blocking on 'no problem imported'."""
    root = create_workspace(tmp_path / "ws").root

    # Write a minimal problem file so dialogue guard allows chat
    problem_dir = root / "input"
    problem_dir.mkdir(parents=True, exist_ok=True)
    (problem_dir / "problem.txt").write_text("Test problem: optimize something.", encoding="utf-8")

    # Mark workspace state so guard allows chat (llm_configured = True via monkeypatch)
    return InteractiveSession(root)


def _collect_stream_blocks(pilot) -> list[LLMStreamBlock]:
    """Return all LLMStreamBlock widgets currently in the log."""
    log_view = pilot.app.query_one("#log")
    return list(log_view.query(LLMStreamBlock))


def _get_log_text(pilot) -> str:
    """Collect all text from Static / Markdown / LLMStreamBlock in #log."""
    from textual.widgets import Markdown as TxtMarkdown
    log_view = pilot.app.query_one("#log")
    parts = []
    for widget in log_view.children:
        # Static text (includes ANSI markup strings)
        content = getattr(widget, "_Static__content", None)
        if content is not None:
            parts.append(str(content))
        # LLMStreamBlock internal text
        if isinstance(widget, LLMStreamBlock):
            parts.append(widget._text)
        # Textual Markdown widget — access the markdown source
        if isinstance(widget, TxtMarkdown):
            md_src = getattr(widget, "_markdown", None)
            if md_src is not None:
                parts.append(str(md_src))
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Test A: streaming path — LLMStreamBlock in log, tokens concatenated
# ---------------------------------------------------------------------------


def test_streaming_chat_renders_into_llm_stream_block(tmp_path: Path) -> None:
    """NL text submitted with a streaming LLM:
    - An LLMStreamBlock must appear in the log.
    - After the worker completes, the block's accumulated text must equal
      the concatenation of all chunks.
    """
    chunks = ["建议", "先", "估计", "票数"]
    expected = "建议先估计票数"

    session = _make_session(tmp_path)
    fake_llm = _StreamingFakeLLM(chunks)
    session._chat_llm = lambda: fake_llm  # type: ignore[method-assign]

    # Bypass dialogue guard: patch _handle_natural_language path's guard
    import mcm_agent.core.dialogue_guard as dg_mod
    from mcm_agent.core.dialogue_guard import DialogueGuardResult

    async def _scenario():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            app = pilot.app

            # Patch dialogue guard to allow chat
            original_evaluate = dg_mod.DialogueGuard.evaluate
            dg_mod.DialogueGuard.evaluate = staticmethod(
                lambda state, msg: DialogueGuardResult(allowed=True, message="")
            )
            try:
                await pilot.pause(0.3)
                prompt = app.query_one("#prompt", ChatTextArea)
                # Natural language (no prefix) — triggers streaming path
                prompt.insert("给我一些建议")
                await pilot.press("enter")

                # Wait for streaming worker to complete
                # Stream is fast (fake), but we need to let the thread finish
                await pilot.pause(1.5)

                blocks = _collect_stream_blocks(pilot)
                log_text = _get_log_text(pilot)
                return blocks, log_text
            finally:
                dg_mod.DialogueGuard.evaluate = original_evaluate

    blocks, log_text = asyncio.run(_scenario())

    assert len(blocks) >= 1, (
        f"Expected at least one LLMStreamBlock in the log after NL chat. "
        f"Log text: {log_text!r}"
    )
    # The accumulated text in the block (or in the log) must contain all chunks
    assert expected in log_text, (
        f"Expected concatenated tokens '{expected}' in log text. Got: {log_text!r}"
    )


# ---------------------------------------------------------------------------
# Test B: fallback path — non-streaming LLM still produces a reply
# ---------------------------------------------------------------------------


def test_non_streaming_fallback_renders_reply(tmp_path: Path) -> None:
    """NL text submitted with a non-streaming LLM (no generate_stream):
    - Fallback path (generate_chat_reply / run_once) must render a reply.
    - No LLMStreamBlock is expected (or it may exist but with content from fallback).
    - The reply text must appear in the log.
    """
    reply_text = "这是一个非流式回复"

    session = _make_session(tmp_path)
    fake_llm = _NonStreamingFakeLLM(reply_text)
    session._chat_llm = lambda: fake_llm  # type: ignore[method-assign]

    import mcm_agent.core.dialogue_guard as dg_mod
    from mcm_agent.core.dialogue_guard import DialogueGuardResult

    async def _scenario():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            app = pilot.app

            original_evaluate = dg_mod.DialogueGuard.evaluate
            dg_mod.DialogueGuard.evaluate = staticmethod(
                lambda state, msg: DialogueGuardResult(allowed=True, message="")
            )
            try:
                await pilot.pause(0.3)
                prompt = app.query_one("#prompt", ChatTextArea)
                prompt.insert("帮我分析题目")
                await pilot.press("enter")

                await pilot.pause(1.5)
                return _get_log_text(pilot)
            finally:
                dg_mod.DialogueGuard.evaluate = original_evaluate

    log_text = asyncio.run(_scenario())

    assert reply_text in log_text, (
        f"Expected non-streaming reply '{reply_text}' in log. Got: {log_text!r}"
    )


# ---------------------------------------------------------------------------
# Test C: assistant reply recorded to session_store after streaming
# ---------------------------------------------------------------------------


def test_streaming_reply_recorded_to_session_store(tmp_path: Path) -> None:
    """After streaming completes, the assistant reply must be persisted in
    session_store.read_recent_messages() so chat history is maintained.
    """
    chunks = ["hello", " world"]
    expected_content = "hello world"

    session = _make_session(tmp_path)
    fake_llm = _StreamingFakeLLM(chunks)
    session._chat_llm = lambda: fake_llm  # type: ignore[method-assign]

    import mcm_agent.core.dialogue_guard as dg_mod
    from mcm_agent.core.dialogue_guard import DialogueGuardResult

    async def _scenario():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            app = pilot.app

            original_evaluate = dg_mod.DialogueGuard.evaluate
            dg_mod.DialogueGuard.evaluate = staticmethod(
                lambda state, msg: DialogueGuardResult(allowed=True, message="")
            )
            try:
                await pilot.pause(0.3)
                prompt = app.query_one("#prompt", ChatTextArea)
                prompt.insert("test message")
                await pilot.press("enter")
                await pilot.pause(1.5)

                # Read messages from session_store
                messages = session.session_store.read_recent_messages(limit=10)
                return messages
            finally:
                dg_mod.DialogueGuard.evaluate = original_evaluate

    messages = asyncio.run(_scenario())

    assistant_messages = [m for m in messages if m.get("role") == "assistant"]
    assert assistant_messages, (
        f"Expected at least one assistant message in session_store. Got: {messages!r}"
    )
    last_assistant = assistant_messages[-1]
    assert expected_content in str(last_assistant.get("content", "")), (
        f"Expected '{expected_content}' in assistant message. Got: {last_assistant!r}"
    )


# ---------------------------------------------------------------------------
# Test D: commands still use the non-streaming path unchanged
# ---------------------------------------------------------------------------


def test_slash_command_still_uses_run_once_path(tmp_path: Path) -> None:
    """Slash commands (/help etc.) must still go through run_once, NOT streaming."""
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)

    # Override run_once to capture calls and return a known result
    run_once_calls: list[str] = []
    original_run_once = session.run_once

    def tracking_run_once(text: str) -> CommandResult:
        run_once_calls.append(text)
        return original_run_once(text)

    session.run_once = tracking_run_once  # type: ignore[method-assign]

    async def _scenario():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            prompt.insert("?")
            await pilot.press("enter")
            await pilot.pause(0.5)
            return list(run_once_calls)

    calls = asyncio.run(_scenario())
    assert "?" in calls, (
        f"'?' command should have been routed through run_once. Got: {calls!r}"
    )


# ---------------------------------------------------------------------------
# Test E: NL chat with _has_draft() → skips streaming, uses run_once instead
# ---------------------------------------------------------------------------


def test_nl_chat_with_draft_skips_streaming_uses_run_once(tmp_path: Path) -> None:
    """When a paper draft exists (_has_draft() returns True), NL chat input
    must NOT use the streaming path. Instead, it must route through run_once
    (which calls _handle_natural_language and creates a revision plan).

    Verification:
    - No LLMStreamBlock should be mounted during/after processing.
    - The response text should come from the revision plan path (not streaming).
    - The run_once path should be called (via worker).
    """
    session = _make_session(tmp_path)

    # Create a draft file so _has_draft() returns True
    draft_file = session.workspace_root / "output" / "draft" / "main.tex"
    draft_file.parent.mkdir(parents=True, exist_ok=True)
    draft_file.write_text("\\documentclass{article}\n\\begin{document}\ntest\n\\end{document}")

    assert session._has_draft(), "Setup: _has_draft() should be True"

    # Set up a fake LLM with streaming support
    fake_llm = _StreamingFakeLLM(["should", " not", " stream"])
    session._chat_llm = lambda: fake_llm  # type: ignore[method-assign]

    # Track whether run_once is called
    run_once_calls: list[str] = []
    original_run_once = session.run_once

    def tracking_run_once(text: str) -> CommandResult:
        run_once_calls.append(text)
        return original_run_once(text)

    session.run_once = tracking_run_once  # type: ignore[method-assign]

    import mcm_agent.core.dialogue_guard as dg_mod
    from mcm_agent.core.dialogue_guard import DialogueGuardResult

    async def _scenario():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            app = pilot.app

            original_evaluate = dg_mod.DialogueGuard.evaluate
            dg_mod.DialogueGuard.evaluate = staticmethod(
                lambda state, msg: DialogueGuardResult(allowed=True, message="")
            )
            try:
                await pilot.pause(0.3)
                prompt = app.query_one("#prompt", ChatTextArea)
                # Natural language input (no prefix)
                prompt.insert("请帮我修订论文")
                await pilot.press("enter")

                # Wait for processing to complete
                await pilot.pause(1.5)

                # Check: no LLMStreamBlock should be in the log
                blocks = _collect_stream_blocks(pilot)
                log_text = _get_log_text(pilot)
                return blocks, log_text, list(run_once_calls)
            finally:
                dg_mod.DialogueGuard.evaluate = original_evaluate

    blocks, log_text, calls = asyncio.run(_scenario())

    # Verify: run_once was called (streaming path skipped)
    assert len(calls) > 0, (
        f"With _has_draft() True, run_once should be called to create revision plan. "
        f"Calls: {calls!r}"
    )

    # Verify: no LLMStreamBlock in the log (streaming was skipped)
    assert len(blocks) == 0, (
        f"With _has_draft() True, no LLMStreamBlock should be mounted. Got {len(blocks)}"
    )

    # Verify: revision plan response should appear (not streaming output)
    assert "revision" in log_text.lower() or "修订" in log_text, (
        f"With draft, response should contain revision plan. Log: {log_text!r}"
    )
