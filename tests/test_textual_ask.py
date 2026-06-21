"""Tests for the ask/printer bridge in MagTuiApp (TUI-3).

The bridge routes interactive command I/O through the Textual UI:
  - _io_printer: posts command print() output to the log from a worker thread
  - _io_ask: blocks the worker until the user types an answer, then returns it

These tests use a stub command that calls ctx.ask() once, plus a test for
printer routing. They drive the app with Textual's Pilot (asyncio).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from mcm_agent.cli_commands.base import CommandContext, CommandResult
from mcm_agent.core.workspace import create_workspace
from mcm_agent.cli_session import InteractiveSession
from mcm_agent.tui.textual_app import MagTuiApp, ChatTextArea


# ---------------------------------------------------------------------------
# Stub command that exercises ask() and printer()
# ---------------------------------------------------------------------------


class _AskTestCommand:
    """Minimal slash-command: prints a line then asks one question."""

    name = "asktest"
    summary = "Test command that uses ask and printer."

    def run(self, args: list[str], context: CommandContext) -> CommandResult:
        context.printer("printer-output-sentinel")
        answer = context.ask("pick: ")
        return CommandResult(f"got-{answer}")


class _PrinterOnlyCommand:
    """Command that only calls printer (no ask)."""

    name = "printertest"
    summary = "Test printer routing."

    def run(self, args: list[str], context: CommandContext) -> CommandResult:
        context.printer("only-printer-sentinel")
        return CommandResult("printer-done")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_with_stub(tmp_path: Path) -> InteractiveSession:
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)
    session.commands["asktest"] = _AskTestCommand()
    session.commands["printertest"] = _PrinterOnlyCommand()
    return session


def _get_log_text(pilot) -> str:
    """Collect all text from Static widgets in #log."""
    log_view = pilot.app.query_one("#log")
    parts = []
    for widget in log_view.query("Static"):
        content = getattr(widget, "_Static__content", None)
        if content is not None:
            parts.append(str(content))
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_printer_routes_to_log(tmp_path: Path) -> None:
    """_io_printer must post command print() output into the log."""
    session = _make_session_with_stub(tmp_path)

    # Inject a stub ask so the command doesn't need interaction for printertest
    async def _scenario():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            prompt.insert("/printertest")
            await pilot.press("enter")
            # Worker is fast (no ask), give it time to complete
            await pilot.pause(1.0)
            return _get_log_text(pilot)

    result = asyncio.run(_scenario())
    assert "only-printer-sentinel" in result, (
        f"Expected 'only-printer-sentinel' in log. Got: {result!r}"
    )


def test_ask_bridge_blocks_then_unblocks_on_answer(tmp_path: Path) -> None:
    """The ask bridge must:
    1. Show the prompt text in the log (app enters ask mode).
    2. Block the worker until the user types an answer.
    3. Return the typed answer to the command.
    4. Show the command result in the log.
    5. Leave ask mode so the next submit runs run_once normally.
    """
    session = _make_session_with_stub(tmp_path)

    async def _scenario():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.3)

            # Submit /asktest — this triggers ctx.ask("pick: ") in the worker
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            prompt.insert("/asktest")
            await pilot.press("enter")

            # Give the worker a moment to reach the ask() call and enter ask mode
            await pilot.pause(0.5)

            # At this point the app should be in ask mode
            app = pilot.app
            in_ask_mode_after_submit = getattr(app, "_ask_mode", False)

            # The ask prompt should appear in the log
            log_after_submit = _get_log_text(pilot)

            # Type "3" and press Enter — this should answer the ask()
            prompt2 = app.query_one("#prompt", ChatTextArea)
            prompt2.insert("3")
            await pilot.press("enter")

            # Worker should now unblock and complete; wait for it
            await pilot.pause(1.0)

            log_after_answer = _get_log_text(pilot)
            ask_mode_after_answer = getattr(app, "_ask_mode", False)

            return in_ask_mode_after_submit, log_after_submit, log_after_answer, ask_mode_after_answer

    (in_ask_mode, log1, log2, ask_mode_done) = asyncio.run(_scenario())

    assert in_ask_mode is True, "App should be in ask mode after /asktest blocks on ctx.ask()"
    assert "pick:" in log1 or "pick" in log1, (
        f"Ask prompt 'pick:' should appear in log. Got: {log1!r}"
    )
    assert "got-3" in log2, (
        f"Command result 'got-3' should appear in log after answering. Got: {log2!r}"
    )
    assert ask_mode_done is False, (
        "App should leave ask mode after the answer is submitted"
    )


def test_ask_answer_echoed_to_log(tmp_path: Path) -> None:
    """The typed answer must be echoed to the log (user sees what they typed)."""
    session = _make_session_with_stub(tmp_path)

    async def _scenario():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            prompt.insert("/asktest")
            await pilot.press("enter")
            await pilot.pause(0.5)
            # Answer the ask
            prompt2 = pilot.app.query_one("#prompt", ChatTextArea)
            prompt2.insert("answer42")
            await pilot.press("enter")
            await pilot.pause(1.0)
            return _get_log_text(pilot)

    log = asyncio.run(_scenario())
    assert "answer42" in log, (
        f"User's answer should be echoed in the log. Got: {log!r}"
    )


def test_after_ask_completes_next_submit_is_normal(tmp_path: Path) -> None:
    """After the ask bridge is done, the next submit must run run_once (not answer an ask)."""
    session = _make_session_with_stub(tmp_path)

    async def _scenario():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            # First: do /asktest + answer
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            prompt.insert("/asktest")
            await pilot.press("enter")
            await pilot.pause(0.5)
            prompt2 = pilot.app.query_one("#prompt", ChatTextArea)
            prompt2.insert("ok")
            await pilot.press("enter")
            await pilot.pause(1.0)
            # After ask-flow done, submit /printertest — should run as a new command
            prompt3 = pilot.app.query_one("#prompt", ChatTextArea)
            prompt3.insert("/printertest")
            await pilot.press("enter")
            await pilot.pause(1.0)
            return _get_log_text(pilot)

    log = asyncio.run(_scenario())
    # /printertest must have run (its printer output must appear)
    assert "only-printer-sentinel" in log, (
        f"After ask completes, /printertest should run normally. Got: {log!r}"
    )


def test_init_skip_via_ask_bridge(tmp_path: Path) -> None:
    """/init interactive: choose '3' (skip) via the ask bridge; result 'already skipped' text appears."""
    session = _make_session_with_stub(tmp_path)

    async def _scenario():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            prompt.insert("/init")
            await pilot.press("enter")
            await pilot.pause(0.5)
            # /init is not yet initialized, context.ask is set → interactive mode
            # It will ask "请选择 [1/2/3]:" — answer "3" to skip
            prompt2 = pilot.app.query_one("#prompt", ChatTextArea)
            prompt2.insert("3")
            await pilot.press("enter")
            await pilot.pause(1.5)
            return _get_log_text(pilot)

    log = asyncio.run(_scenario())
    assert "已跳过" in log or "skip" in log.lower() or "LLM" in log or "跳过" in log, (
        f"Expected skip/配置 message from /init choice 3. Got: {log!r}"
    )
