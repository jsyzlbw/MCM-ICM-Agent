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
    """Full-screen Textual TUI: scrolling log + bordered ChatTextArea input."""

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
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(self, session: "InteractiveSession", **kwargs) -> None:
        super().__init__(**kwargs)
        self.session = session
        self._is_processing = False

    def compose(self) -> ComposeResult:
        header_text = self._build_header()
        yield Label(header_text, id="header")
        yield VerticalScroll(id="log")
        yield ChatTextArea("", id="prompt")

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

    def on_mount(self) -> None:
        """Render welcome panel and focus the input."""
        self._append_welcome()
        prompt = self.query_one("#prompt", ChatTextArea)
        prompt.focus()

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
        """Handle submitted text: append user turn and run session in a worker thread."""
        text = event.text.strip()
        if not text:
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
        if result is not None and getattr(result, "message", ""):
            msg = result.message
            is_md = getattr(result, "markdown", False)
            self._append_to_log(msg, is_markdown=is_md)

        # Re-enable input
        prompt = self.query_one("#prompt", ChatTextArea)
        prompt.border_title = ""
        prompt.disabled = False
        prompt.focus()
        self._is_processing = False

        if result is not None and getattr(result, "exit_session", False):
            self.exit()

    def _handle_error(self, worker) -> None:
        """Called on the UI thread if the worker raised an exception."""
        self._append_to_log(f"[错误] {worker.error}", classes="system-msg")

        prompt = self.query_one("#prompt", ChatTextArea)
        prompt.border_title = ""
        prompt.disabled = False
        prompt.focus()
        self._is_processing = False
