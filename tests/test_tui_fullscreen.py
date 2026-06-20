"""TDD tests for the full-screen prompt_toolkit app (MagFullScreenApp).

Driven entirely via pipe input + DummyOutput so no real TTY is required.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mcm_agent.cli_commands.base import CommandResult
from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workspace import create_workspace
from mcm_agent.tui.fullscreen import MagFullScreenApp, render_to_ansi


# ---------------------------------------------------------------------------
# render_to_ansi
# ---------------------------------------------------------------------------


def test_render_to_ansi_caps_width() -> None:
    from rich.text import Text

    out = render_to_ansi(Text("hello"), width=40)
    # ANSI object exposes its text via .value
    assert "hello" in out.value


def test_render_to_ansi_returns_ansi_type() -> None:
    from prompt_toolkit.formatted_text import ANSI
    from rich.text import Text

    out = render_to_ansi(Text("world"), width=80)
    assert isinstance(out, ANSI)


def test_render_to_ansi_markdown() -> None:
    from rich.markdown import Markdown

    out = render_to_ansi(Markdown("**bold**"), width=60)
    assert out.value  # non-empty


# ---------------------------------------------------------------------------
# MagFullScreenApp — basic submission
# ---------------------------------------------------------------------------


def test_fullscreen_submits_to_run_once(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)
    seen: list[str] = []
    orig = session.run_once
    session.run_once = lambda text: seen.append(text) or orig(text)  # type: ignore

    with create_pipe_input() as inp:
        inp.send_text("?\r")        # a command that run_once handles (shortcuts help)
        inp.send_text("\x04")       # Ctrl-D exits
        MagFullScreenApp(session, input=inp, output=DummyOutput()).run()

    assert "?" in seen  # input was dispatched through run_once


def test_fullscreen_bang_runs_shell(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)

    with create_pipe_input() as inp:
        inp.send_text("!echo fs-ok\r")
        inp.send_text("\x04")
        app = MagFullScreenApp(session, input=inp, output=DummyOutput())
        app.run()

    # the shell output was appended to the transcript
    joined = "".join(frag.value for frag in app._fragments)
    assert "fs-ok" in joined


def test_fullscreen_empty_input_ignored(tmp_path: Path) -> None:
    """Empty enter should not dispatch to run_once."""
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)
    seen: list[str] = []
    orig = session.run_once
    session.run_once = lambda text: seen.append(text) or orig(text)  # type: ignore

    with create_pipe_input() as inp:
        inp.send_text("\r")         # empty enter — should be ignored
        inp.send_text("\x04")       # Ctrl-D exits
        MagFullScreenApp(session, input=inp, output=DummyOutput()).run()

    # empty input must NOT reach run_once
    assert "" not in seen


def test_fullscreen_ctrl_d_exits(tmp_path: Path) -> None:
    """Ctrl-D must cause the app to exit cleanly."""
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)

    with create_pipe_input() as inp:
        inp.send_text("\x04")  # immediate Ctrl-D
        # Must not hang or raise
        MagFullScreenApp(session, input=inp, output=DummyOutput()).run()


def test_fullscreen_result_appended_to_transcript(tmp_path: Path) -> None:
    """run_once result should appear in _fragments."""
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)

    with create_pipe_input() as inp:
        inp.send_text("?\r")   # shortcuts help command
        inp.send_text("\x04")
        app = MagFullScreenApp(session, input=inp, output=DummyOutput())
        app.run()

    joined = "".join(frag.value for frag in app._fragments)
    # The shortcuts help output contains '/'
    assert "/" in joined


# ---------------------------------------------------------------------------
# Non-TTY fallback (cli_session.run() must still call _run_plain)
# ---------------------------------------------------------------------------


def test_run_falls_back_to_plain_on_non_tty(tmp_path: Path, monkeypatch) -> None:
    """cli_session.run() must use _run_plain when stdin/stdout are not a TTY."""
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)

    called: list[str] = []

    def fake_plain():
        called.append("plain")

    monkeypatch.setattr(session, "_run_plain", fake_plain)
    # isatty() returns False in pytest (non-TTY env), so run() should call _run_plain
    session.run()

    assert called == ["plain"]


# ---------------------------------------------------------------------------
# NEW: suppress_live_output flag (Part A fix)
# ---------------------------------------------------------------------------


def test_suppressed_chat_returns_reply_without_printing(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """When suppress_live_output=True, run_once must:
    - return CommandResult with the LLM reply in .message and .markdown=True
    - NOT write anything to stdout (no streaming, no spinner)
    """
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)

    # Fake LLM: .generate returns known string; .generate_stream must NOT be called
    class FakeLLM:
        def generate(self, *args, **kwargs) -> str:
            return "fake-reply-suppressed"

        def generate_stream(self, *args, **kwargs):
            raise AssertionError("generate_stream must not be called when suppress_live_output=True")

    monkeypatch.setattr(session, "_chat_llm", lambda: FakeLLM())

    # Monkeypatch generate_chat_reply where cli_session imports it from
    import mcm_agent.cli_session as cli_mod

    def fake_generate(workspace_root, text, llm, recent, *, attachments=None):
        return llm.generate(text)

    monkeypatch.setattr(cli_mod, "generate_chat_reply", fake_generate)

    # Bypass DialogueGuard so LLM check and problem-import check don't block
    import mcm_agent.core.dialogue_guard as dg_mod
    from mcm_agent.core.dialogue_guard import DialogueGuardResult

    monkeypatch.setattr(
        dg_mod.DialogueGuard,
        "evaluate",
        staticmethod(lambda state, msg: DialogueGuardResult(allowed=True, message="")),
    )

    # Set suppress flag
    session.suppress_live_output = True

    result = session.run_once("讲讲思路")

    # Must have the fake reply
    assert result.message == "fake-reply-suppressed"
    assert result.markdown is True

    # Nothing written to real stdout
    captured = capsys.readouterr()
    assert captured.out == ""


# ---------------------------------------------------------------------------
# NEW: async Enter handler — existing pipe tests must still pass
# ---------------------------------------------------------------------------


def test_fullscreen_submits_to_run_once_async(tmp_path: Path) -> None:
    """After the async Enter handler refactor, ? must still dispatch through run_once."""
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)
    seen: list[str] = []
    orig = session.run_once
    session.run_once = lambda text: seen.append(text) or orig(text)  # type: ignore

    with create_pipe_input() as inp:
        inp.send_text("?\r")
        inp.send_text("\x04")
        MagFullScreenApp(session, input=inp, output=DummyOutput()).run()

    assert "?" in seen


def test_fullscreen_bang_runs_shell_async(tmp_path: Path) -> None:
    """After async Enter handler refactor, !echo must still append output to transcript."""
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)

    with create_pipe_input() as inp:
        inp.send_text("!echo fs-async-ok\r")
        inp.send_text("\x04")
        app = MagFullScreenApp(session, input=inp, output=DummyOutput())
        app.run()

    joined = "".join(frag.value for frag in app._fragments)
    assert "fs-async-ok" in joined
