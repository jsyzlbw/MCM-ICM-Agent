"""Textual-based TUI for Mag CLI.

Layout (top → bottom):
  1. Label header (static)
  2. VerticalScroll(id="log") – scrolling transcript, takes all remaining space
  3. ChatTextArea(id="prompt") – bordered input at bottom, auto-height

Usage::

    from mcm_agent.tui.textual_app import MagTuiApp
    MagTuiApp(session).run()
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Label, Static, TextArea

if TYPE_CHECKING:
    from mcm_agent.cli_session import InteractiveSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _render_to_markup(renderable: object, width: int = 100) -> str:
    """Render any Rich renderable to an ANSI-escaped string using MAG_THEME."""
    from rich.console import Console
    from mcm_agent.tui.theme import MAG_THEME

    con = Console(
        width=width,
        file=None,
        force_terminal=True,
        color_system="standard",
        highlight=False,
        theme=MAG_THEME,
    )
    with con.capture() as cap:
        con.print(renderable)
    return cap.get()


# ---------------------------------------------------------------------------
# ChatTextArea — bordered input widget
# ---------------------------------------------------------------------------


class ChatTextArea(TextArea):
    """TextArea subclass that submits on Enter, inserts newline on Alt+Enter / Shift+Enter."""

    class Submitted(Message):
        """Posted when the user presses Enter to submit."""

        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    def on_key(self, event) -> None:
        """Handle Enter (submit) vs Alt+Enter / Shift+Enter (newline)."""
        if event.key == "enter":
            # Plain Enter → submit
            text = self.text
            self.clear()
            event.prevent_default()
            self.post_message(ChatTextArea.Submitted(text))
        elif event.key in ("shift+enter", "escape+enter"):
            # Alt+Enter or Shift+Enter → insert newline
            self.insert("\n")
            event.prevent_default()


# ---------------------------------------------------------------------------
# MagTuiApp
# ---------------------------------------------------------------------------


class MagTuiApp(App):
    """Full-screen Textual TUI: scrolling log + bordered ChatTextArea input.

    Ask/printer bridge (TUI-3)
    --------------------------
    Interactive commands like /api and /init call ctx.ask(prompt) and
    ctx.printer(text) from inside a worker thread. The bridge routes these
    through the Textual UI:

    * _io_printer(text): posts text to the log via call_from_thread so it
      arrives on the UI thread safely.
    * _io_ask(prompt): posts the prompt to the log, enters "ask mode", and
      BLOCKS the worker thread on a threading.Event until the user submits
      an answer from the ChatTextArea.
    * When _ask_mode is True, the submit handler treats the submitted text as
      the answer rather than as a new command.
    """

    CSS = """
    #header {
        background: $surface;
        color: #1D9E75;
        padding: 0 1;
        height: 1;
    }
    #log {
        height: 1fr;
    }
    ChatTextArea {
        border: round #1D9E75;
        min-height: 3;
        max-height: 12;
    }
    ChatTextArea:focus {
        border: round #1D9E75;
    }
    .user-turn {
        color: #1D9E75;
    }
    .system-msg {
        color: $text-muted;
    }
    .ask-prompt {
        color: $warning;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(self, session: "InteractiveSession", **kwargs) -> None:
        super().__init__(**kwargs)
        self.session = session
        self._is_processing = False
        # Ask bridge state
        self._ask_mode: bool = False
        self._ask_event: threading.Event = threading.Event()
        self._ask_answer: str = ""

    # ------------------------------------------------------------------
    # Ask/printer bridge
    # ------------------------------------------------------------------

    def _io_printer(self, text: str) -> None:
        """Called from a worker thread; routes text to the log on the UI thread."""
        self.call_from_thread(self._append_to_log, str(text), classes="system-msg")

    def _io_ask(self, prompt: str = "") -> str:
        """Called from a worker thread; shows prompt, blocks until user answers.

        Returns the answer string. Returns "" if the app exits while waiting.
        """
        # Show the prompt in the log and enter ask mode on the UI thread.
        self._ask_event.clear()
        self._ask_answer = ""
        self.call_from_thread(self._enter_ask_mode, str(prompt))
        # Block the worker thread until the UI thread calls _deliver_ask_answer.
        self._ask_event.wait()
        return self._ask_answer

    def _enter_ask_mode(self, prompt: str) -> None:
        """UI-thread side: show the ask prompt and set _ask_mode = True."""
        if prompt:
            self._append_to_log(prompt, classes="ask-prompt")
        self._ask_mode = True
        # Re-enable and focus input so the user can type
        input_widget = self.query_one("#prompt", ChatTextArea)
        input_widget.disabled = False
        input_widget.border_title = "∑ 请回答…"
        input_widget.focus()

    def _deliver_ask_answer(self, answer: str) -> None:
        """UI-thread side: store the answer, leave ask mode, unblock the worker."""
        self._ask_answer = answer
        self._ask_mode = False
        self._ask_event.set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        """Install the I/O bridge on the session, render welcome, focus input."""
        self.session._io_printer = self._io_printer
        self.session._io_ask = self._io_ask
        self._append_welcome()
        prompt = self.query_one("#prompt", ChatTextArea)
        prompt.focus()

    def on_unmount(self) -> None:
        """Restore session I/O overrides and unblock any waiting worker."""
        self._unblock_ask_on_exit()
        self.session._io_printer = None
        self.session._io_ask = None

    def _unblock_ask_on_exit(self) -> None:
        """If the app exits while a worker is blocked in _io_ask, release it."""
        if self._ask_mode and not self._ask_event.is_set():
            self._ask_answer = ""
            self._ask_mode = False
            self._ask_event.set()

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self) -> str:
        """Build a one-line header from workspace state and settings."""
        try:
            from mcm_agent.config import load_settings
            from mcm_agent.core.workspace import load_workspace_state

            state = load_workspace_state(self.session.workspace_root)
            settings = load_settings(workspace_root=self.session.workspace_root)
            ws_name = self.session.workspace_root.name
            llm_provider = getattr(settings, "llm_provider", "") or "未配置"
            model = getattr(settings, "openai_model", "") or ""
            phase = str(getattr(state, "phase", ""))
            if model:
                llm_part = f"{llm_provider}/{model}"
            else:
                llm_part = llm_provider
            return f"∑ Mag  ws:{ws_name}  llm:{llm_part}  phase:{phase}"
        except Exception:
            return "∑ Mag"

    def compose(self) -> ComposeResult:
        header_text = self._build_header()
        yield Label(header_text, id="header")
        yield VerticalScroll(id="log")
        yield ChatTextArea("", id="prompt")

    def _append_welcome(self) -> None:
        """Mount the welcome panel into the log as rendered ANSI text."""
        try:
            from mcm_agent.config import load_settings
            from mcm_agent.core.workspace import load_workspace_state
            from mcm_agent.tui.welcome import render_welcome_panel
            from mcm_agent.version import __version__

            state = load_workspace_state(self.session.workspace_root)
            settings = load_settings(workspace_root=self.session.workspace_root)
            panel = render_welcome_panel(
                state, settings, __version__, self.session.workspace_root
            )
            ansi_text = _render_to_markup(panel, width=100)
            log_view = self.query_one("#log", VerticalScroll)
            # Use markup=False so ANSI codes are treated as text (Static uses Textual markup by default)
            # We pass the pre-rendered string and disable markup parsing
            log_view.mount(Static(ansi_text, markup=False))
        except Exception:
            pass  # welcome is non-critical

    def _append_to_log(self, text: str, *, is_markdown: bool = False, classes: str = "") -> None:
        """Append content to the log view."""
        log_view = self.query_one("#log", VerticalScroll)
        if is_markdown:
            from textual.widgets import Markdown
            widget = Markdown(text)
        else:
            widget = Static(text, markup=False, classes=classes)
        log_view.mount(widget)
        log_view.scroll_end(animate=False)

    # ------------------------------------------------------------------
    # Submit handler
    # ------------------------------------------------------------------

    def on_chat_text_area_submitted(self, event: ChatTextArea.Submitted) -> None:
        """Handle submitted text.

        If the app is in ask mode, treat the text as the answer to an ongoing
        ctx.ask() call — echo it, deliver the answer to unblock the worker,
        and clear ask mode.  Otherwise start a new run_once worker.
        """
        text = event.text.strip()
        if not text:
            return

        if self._ask_mode:
            # Echo the user's answer to the log
            self._append_to_log(f"> {text}", classes="user-turn")
            # Reset the prompt border title (will be re-set by worker completion)
            prompt = self.query_one("#prompt", ChatTextArea)
            prompt.border_title = "∑ 正在处理…"
            prompt.disabled = True
            # Deliver the answer — this unblocks the worker thread
            self._deliver_ask_answer(text)
            return

        if self._is_processing:
            return  # Ignore new submissions while processing

        # Append user turn to log
        self._append_to_log(f"> {text}", classes="user-turn")

        # Disable input while processing
        prompt = self.query_one("#prompt", ChatTextArea)
        prompt.disabled = True
        prompt.border_title = "∑ 正在处理…"
        self._is_processing = True

        # Run blocking session.run_once() in a thread worker
        self.run_worker(
            lambda: self.session.run_once(text),
            thread=True,
            exit_on_error=False,
        )

    def on_worker_state_changed(self, event) -> None:
        """When the thread worker finishes, handle the result on the UI thread."""
        from textual.worker import WorkerState

        if event.state == WorkerState.SUCCESS:
            result = event.worker.result
            self._handle_result(result)
        elif event.state == WorkerState.ERROR:
            self._handle_error(event.worker)

    def _handle_result(self, result) -> None:
        """Called on the UI thread after the worker completes successfully."""
        try:
            if result is not None and getattr(result, "message", ""):
                msg = result.message
                is_md = getattr(result, "markdown", False)
                self._append_to_log(msg, is_markdown=is_md)

            if result is not None and getattr(result, "exit_session", False):
                self.exit()
        except Exception as e:
            # Log render error but don't fail re-enable
            try:
                self._append_to_log(f"[错误] 渲染失败: {e}", classes="system-msg")
            except Exception:
                pass  # If logging itself fails, silently continue
        finally:
            # Always re-enable input, even if rendering raised
            prompt = self.query_one("#prompt", ChatTextArea)
            prompt.border_title = ""
            prompt.disabled = False
            prompt.focus()
            self._is_processing = False

    def _handle_error(self, worker) -> None:
        """Called on the UI thread if the worker raised an exception."""
        try:
            self._append_to_log(f"[错误] {worker.error}", classes="system-msg")
        except Exception:
            pass  # If logging itself fails, silently continue
        finally:
            # Always re-enable input, even if error logging raised
            prompt = self.query_one("#prompt", ChatTextArea)
            prompt.border_title = ""
            prompt.disabled = False
            prompt.focus()
            self._is_processing = False
