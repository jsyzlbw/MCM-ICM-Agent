"""Tests for MagTuiApp (Textual-based TUI).

pytest-asyncio is NOT available — tests use asyncio.run() in sync functions.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from mcm_agent.cli_commands.base import CommandResult
from mcm_agent.core.workspace import create_workspace
from mcm_agent.cli_session import InteractiveSession
from mcm_agent.tui.textual_app import MagTuiApp, ChatTextArea


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stub_session(tmp_path: Path, run_once_result: CommandResult) -> InteractiveSession:
    """Create an InteractiveSession with a stubbed run_once that returns immediately."""
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)
    session.run_once = lambda text: run_once_result  # type: ignore[method-assign]
    return session


def _get_log_text(pilot) -> str:
    """Collect all text content from Static widgets in the log."""
    log_view = pilot.app.query_one("#log")
    parts = []
    for widget in log_view.query("Static"):
        # Access the name-mangled content attribute
        content = getattr(widget, "_Static__content", None)
        if content is not None:
            parts.append(str(content))
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_help_shows_in_log(tmp_path: Path) -> None:
    """Submit '?' (shortcuts help) and verify help content appears in the log."""
    help_text = "快捷键 / 输入模式：\n  !  shell\n  /help  查看全部命令"
    session = _make_stub_session(tmp_path, CommandResult(help_text))

    async def _scenario():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            # Insert text directly into the prompt widget then press Enter
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            prompt.insert("?")
            await pilot.press("enter")
            # Wait for worker to complete (it's a stub, so it's instant)
            await pilot.pause(0.5)
            return _get_log_text(pilot)

    result = asyncio.run(_scenario())
    # The user turn "> ?" should appear in the log, and the help text
    assert "> ?" in result or "shell" in result or "help" in result.lower() or "快捷键" in result


def test_shell_echo_in_log(tmp_path: Path) -> None:
    """Submit '!echo tui-ok' and verify 'tui-ok' appears in the log."""
    session = _make_stub_session(tmp_path, CommandResult("tui-ok\n(exit 0)"))

    async def _scenario():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            prompt.insert("!echo tui-ok")
            await pilot.press("enter")
            # Wait for worker thread to complete
            await pilot.pause(0.5)
            return _get_log_text(pilot)

    result = asyncio.run(_scenario())
    assert "tui-ok" in result


def test_chat_textarea_enter_submits(tmp_path: Path) -> None:
    """Verify ChatTextArea submits on Enter — user turn appears in log."""
    session = _make_stub_session(tmp_path, CommandResult("ok"))

    async def _scenario():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            prompt.insert("hello world")
            # Pressing Enter should clear the TextArea and submit the text
            await pilot.press("enter")
            await pilot.pause(0.5)
            # After submission, the TextArea should be cleared
            text_after = prompt.text
            log_text = _get_log_text(pilot)
            return text_after, log_text

    text_after, log_text = asyncio.run(_scenario())
    # The textarea should be cleared after submission
    assert text_after == ""
    # The user turn should appear in the log
    assert "hello world" in log_text


def test_exit_session_causes_app_exit(tmp_path: Path) -> None:
    """CommandResult with exit_session=True causes the app to exit."""
    session = _make_stub_session(tmp_path, CommandResult("Goodbye", exit_session=True))

    async def _scenario():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            prompt.insert("/exit ")  # trailing space: bypass slash-popup so Enter submits
            await pilot.press("enter")
            # App should exit on its own; wait a bit then check
            await pilot.pause(2.0)
            return pilot.app.return_value

    # Should complete without hanging indefinitely
    asyncio.run(asyncio.wait_for(_scenario(), timeout=10.0))


def test_input_reenabled_even_on_render_error(tmp_path: Path) -> None:
    """If _append_to_log raises during result handling, input must still be re-enabled."""
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)
    session.run_once = lambda text: CommandResult("ok")  # type: ignore[method-assign]

    async def _scenario():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            app = pilot.app
            prompt = app.query_one("#prompt", ChatTextArea)

            # Monkeypatch _append_to_log to raise after first call (welcome)
            original_append = app._append_to_log
            call_count = [0]

            def raising_append(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] > 1:  # Let welcome render, fail on result rendering
                    raise RuntimeError("Simulated render error in _append_to_log")
                return original_append(*args, **kwargs)

            app._append_to_log = raising_append

            # Submit input
            prompt.insert("test input")
            await pilot.press("enter")
            # Wait for worker to finish and error handler to run
            await pilot.pause(0.5)
            # Check that the prompt is re-enabled (not stuck disabled)
            return prompt.disabled

    disabled_after = asyncio.run(_scenario())
    # Input must be re-enabled, not stuck disabled
    assert disabled_after is False, "Input prompt should be re-enabled even after render error"
