"""Textual-based TUI for Mag CLI.

Layout (top → bottom):
  1. Label header (static)
  2. VerticalScroll(id="log") – scrolling transcript, takes all remaining space
  3. [SlashCompleteWidget] – mounted dynamically before #prompt when "/" typed
  4. ChatTextArea(id="prompt") – bordered input at bottom, auto-height

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
from textual.css.query import NoMatches
from textual.message import Message
from textual.widgets import Label, Static, TextArea

from rich.markdown import Markdown as _RichMarkdown

if TYPE_CHECKING:
    from mcm_agent.cli_session import InteractiveSession

# Teal accent colour (also defined in theme.ACCENT)
_ACCENT = "#1D9E75"


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


def _mode_badge(text: str) -> str:
    """Return the mode label based on the first character of the input text."""
    if not text:
        return "讨论"
    first = text[0]
    if first == "!":
        return "shell"
    if first == "/":
        return "命令"
    if first == "@":
        return "文件"
    return "讨论"


# ---------------------------------------------------------------------------
# LLMStreamBlock — accumulates streaming tokens, renders Markdown when done
# ---------------------------------------------------------------------------


class LLMStreamBlock(Static):
    """Accumulates LLM streaming tokens in a single widget.

    While streaming, each ``append_token`` call extends the raw text and
    refreshes the display.  ``finalize_markdown()`` replaces the plain text
    with a rendered Rich Markdown renderable once the stream is complete.
    """

    DEFAULT_CSS = "LLMStreamBlock { padding: 0 1; color: $text; }"

    def __init__(self) -> None:
        super().__init__("")
        self._text: str = ""
        self._finalized: bool = False

    def append_token(self, token: str) -> None:
        """Append *token* to the accumulated text and refresh the display."""
        if self._finalized:
            return
        self._text += token
        self.update(self._text)

    def finalize_markdown(self) -> None:
        """Render accumulated text as Rich Markdown (called once streaming ends)."""
        if self._finalized:
            return
        self._finalized = True
        if self._text.strip():
            self.update(_RichMarkdown(self._text, code_theme="monokai"))


# ---------------------------------------------------------------------------
# SlashCompleteWidget — / autocomplete dropdown
# ---------------------------------------------------------------------------


class SlashCompleteWidget(Static):
    """Slash-command autocomplete popup.

    Displays a filtered list of available commands.  Navigation and selection
    are driven by ChatTextArea._on_key routing ↑/↓/Tab/Esc to this widget.
    When a selection is made, posts ``Selected`` — MagTuiApp handles it.
    """

    can_focus = False

    DEFAULT_CSS = f"""
    SlashCompleteWidget {{
        height: auto;
        padding: 0 1;
        margin: 0 2;
        background: $surface;
        border: round {_ACCENT};
    }}
    """

    class Selected(Message):
        """Posted when the user selects a command from the dropdown."""

        def __init__(self, name: str) -> None:
            self.name = name
            super().__init__()

    def __init__(self, items: list[tuple[str, str]]) -> None:
        super().__init__("")
        self._all_items: list[tuple[str, str]] = items
        self._filtered: list[tuple[str, str]] = list(items)
        self._cursor: int = 0

    def set_query(self, query: str) -> None:
        """Filter items by *query* (case-insensitive substring match on name)."""
        q = query.lower()
        self._filtered = [(n, d) for n, d in self._all_items if not q or q in n.lower()]
        self._cursor = min(self._cursor, max(0, len(self._filtered) - 1))
        if self.is_attached:
            self._redraw()

    def move_up(self) -> None:
        if self._filtered:
            self._cursor = (self._cursor - 1) % len(self._filtered)
            self._redraw()

    def move_down(self) -> None:
        if self._filtered:
            self._cursor = (self._cursor + 1) % len(self._filtered)
            self._redraw()

    def select_current(self) -> None:
        if self._filtered:
            self.post_message(self.Selected(self._filtered[self._cursor][0]))

    def has_selection(self) -> bool:
        return bool(self._filtered)

    def on_mount(self) -> None:
        self._redraw()

    def _redraw(self) -> None:
        if not self._filtered:
            self.update("[dim]  no matching commands[/dim]")
            return
        lines: list[str] = []
        for i, (name, desc) in enumerate(self._filtered):
            desc_part = f"  [dim]{desc}[/dim]" if desc else ""
            if i == self._cursor:
                lines.append(f"  [bold]❯ /{name}[/bold]{desc_part}")
            else:
                lines.append(f"    /{name}{desc_part}")
        lines.append("[dim]  ↑↓ navigate   tab/enter select   esc dismiss[/dim]")
        self.update("\n".join(lines))


# ---------------------------------------------------------------------------
# ChatTextArea — bordered input widget
# ---------------------------------------------------------------------------


class ChatTextArea(TextArea):
    """TextArea subclass that submits on Enter, inserts newline on Alt+Enter / Shift+Enter.

    Also posts SlashChanged messages when text starts with "/" so MagTuiApp
    can show/hide/update the SlashCompleteWidget.  Keys ↑↓/Tab/Esc are
    routed to the popup when it is open.
    """

    class Submitted(Message):
        """Posted when the user presses Enter to submit."""

        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    class SlashChanged(Message):
        """Posted when slash-command prefix changes.

        ``query`` is the text after "/" (may be "").  ``None`` means the
        text no longer looks like a slash-command → dismiss popup.
        """

        def __init__(self, query: str | None) -> None:
            self.query = query
            super().__init__()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Detect slash prefix and emit SlashChanged; update mode badge."""
        text = self.text
        # Slash-command detection: starts with "/" and no space yet
        if text.startswith("/") and " " not in text:
            self.post_message(ChatTextArea.SlashChanged(query=text[1:]))
        else:
            self.post_message(ChatTextArea.SlashChanged(query=None))
        # Mode badge in border_title (only update when not in special states)
        # We only update the badge when the app has NOT set a custom title
        # (e.g. "∑ 正在处理…") — we detect that by checking the app's processing flag.
        app = self.app  # type: ignore[attr-defined]
        if not getattr(app, "_is_processing", False) and not getattr(app, "_ask_mode", False):
            badge = _mode_badge(text)
            # border_title uses Textual markup: wrap in plain text, not brackets
            # which would be treated as style tags. Use a prefix to make it visible.
            self.border_title = badge

    async def _on_key(self, event) -> None:
        """Route keys to popup when open; handle Enter submit / newline insert."""
        key = event.key

        # Find popup if present
        popup: SlashCompleteWidget | None = None
        try:
            popup = self.app.query_one(SlashCompleteWidget)  # type: ignore[attr-defined]
        except NoMatches:
            popup = None

        if key == "enter":
            event.stop()
            event.prevent_default()
            # In ask mode, always deliver answer — never let popup swallow it
            if getattr(self.app, "_ask_mode", False):  # type: ignore[attr-defined]
                text = self.text
                self.clear()
                self.post_message(self.Submitted(text))
                return
            # Normal mode: if popup open and has items, select the item
            if popup is not None and popup.has_selection():
                popup.select_current()
                return
            # Otherwise submit
            if self.text.strip():
                text = self.text
                self.clear()
                self.post_message(self.Submitted(text))
            return

        if key in ("shift+enter", "escape+enter", "alt+enter"):
            event.stop()
            event.prevent_default()
            if not self.read_only:
                self.insert("\n")
            return

        if popup is not None:
            if key == "up":
                event.stop()
                event.prevent_default()
                popup.move_up()
                return
            elif key == "down":
                event.stop()
                event.prevent_default()
                popup.move_down()
                return
            elif key == "tab":
                event.stop()
                event.prevent_default()
                popup.select_current()
                return
            elif key == "escape":
                event.stop()
                event.prevent_default()
                self.post_message(ChatTextArea.SlashChanged(query=None))
                return

        await super()._on_key(event)


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

    Slash completion (TUI-2)
    ------------------------
    When the user types "/" in the prompt, a SlashCompleteWidget is mounted
    before #prompt showing all registered commands filtered by the query.
    ↑↓ navigate, Tab/Enter select (fills input with "/{name} " and dismisses),
    Esc dismisses.  In ask mode Enter always delivers the answer.
    """

    CSS = f"""
    #header {{
        background: $surface;
        color: {_ACCENT};
        padding: 0 1;
        height: 1;
    }}
    #log {{
        height: 1fr;
    }}
    ChatTextArea {{
        border: round {_ACCENT};
        min-height: 3;
        max-height: 12;
    }}
    ChatTextArea:focus {{
        border: round {_ACCENT};
    }}
    .user-turn {{
        color: {_ACCENT};
    }}
    .system-msg {{
        color: $text-muted;
    }}
    .ask-prompt {{
        color: $warning;
    }}
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
        self._ask_event.clear()
        self._ask_answer = ""
        self.call_from_thread(self._enter_ask_mode, str(prompt))
        self._ask_event.wait()
        return self._ask_answer

    def _enter_ask_mode(self, prompt: str) -> None:
        """UI-thread side: show the ask prompt and set _ask_mode = True."""
        if prompt:
            self._append_to_log(prompt, classes="ask-prompt")
        self._ask_mode = True
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
    # Slash completion — event handlers
    # ------------------------------------------------------------------

    def _build_slash_items(self) -> list[tuple[str, str]]:
        """Build list of (name, summary) for all registered commands + 'help'."""
        items: list[tuple[str, str]] = []
        try:
            for name, command in self.session.commands.items():
                items.append((name, getattr(command, "summary", "")))
        except Exception:
            pass
        # Ensure "help" is present
        if not any(n == "help" for n, _ in items):
            items.append(("help", "show help"))
        return items

    def on_chat_text_area_slash_changed(self, event: ChatTextArea.SlashChanged) -> None:
        """Mount, update, or remove the SlashCompleteWidget based on query."""
        query = event.query
        if query is None:
            # Dismiss popup
            try:
                self.query_one(SlashCompleteWidget).remove()
            except NoMatches:
                pass
            return
        # Don't show popup in ask mode
        if self._ask_mode:
            return
        try:
            popup = self.query_one(SlashCompleteWidget)
            popup.set_query(query)
        except NoMatches:
            items = self._build_slash_items()
            popup = SlashCompleteWidget(items)
            self.mount(popup, before="#prompt")
            popup.set_query(query)

    def on_slash_complete_widget_selected(self, event: SlashCompleteWidget.Selected) -> None:
        """Fill input with the selected command name and dismiss the popup."""
        try:
            prompt = self.query_one("#prompt", ChatTextArea)
            prompt.text = f"/{event.name} "
            prompt.move_cursor(prompt.document.end)
        except NoMatches:
            pass
        try:
            self.query_one(SlashCompleteWidget).remove()
        except NoMatches:
            pass

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

    @staticmethod
    def _is_nl_chat(text: str) -> bool:
        """Return True if *text* is a natural-language chat turn (not a command)."""
        if not text:
            return False
        first = text[0]
        return first not in ("/", "!", "?")

    def on_chat_text_area_submitted(self, event: ChatTextArea.Submitted) -> None:
        """Handle submitted text.

        * Ask mode: deliver the answer to unblock the waiting worker.
        * NL chat (no / ! ? prefix): run the streaming path if the LLM has
          ``generate_stream``; otherwise fall back to the run_once path.
        * Commands / shell / shortcuts: unchanged run_once path.
        """
        text = event.text.strip()

        if self._ask_mode:
            # Echo the user's answer to the log (show "(default)" if empty)
            display = f"> {text}" if text else "> (default)"
            self._append_to_log(display, classes="user-turn")
            # Reset the prompt border title (will be re-set by worker completion)
            prompt = self.query_one("#prompt", ChatTextArea)
            prompt.border_title = "∑ 正在处理…"
            prompt.disabled = True
            # Deliver the answer — this unblocks the worker thread.
            self._deliver_ask_answer(text)
            return

        # Normal (non-ask) mode: ignore empty / whitespace-only submissions
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

        if self._is_nl_chat(text):
            # Natural-language chat: try streaming path, fall back to run_once.
            # GUARD: Skip streaming if a draft exists — _has_draft() returns True,
            # meaning NL should create a REVISION PLAN (via _handle_natural_language)
            # instead of a normal chat reply. Only stream when NO draft exists.
            if not self.session._has_draft():
                llm = self.session._chat_llm()
                if llm is not None and hasattr(llm, "generate_stream"):
                    # Streaming path: append an empty LLMStreamBlock, stream into it.
                    block = LLMStreamBlock()
                    log_view = self.query_one("#log", VerticalScroll)
                    log_view.mount(block)
                    log_view.scroll_end(animate=False)

                    def _stream_worker():
                        from mcm_agent.core.chat import stream_chat_reply

                        recent = self.session.session_store.read_recent_messages(limit=8)
                        attachments = self.session._collect_attachments(text)
                        # Record the user turn in session_store (run_once does this
                        # via the call path, so we mirror it here for the streaming path).
                        self.session.session_store.append_message("user", text)
                        full_text = ""
                        try:
                            for chunk in stream_chat_reply(
                                self.session.workspace_root, text, llm, recent,
                                attachments=attachments
                            ):
                                self.call_from_thread(block.append_token, chunk)
                                full_text += chunk
                        finally:
                            self.call_from_thread(block.finalize_markdown)
                        if full_text:
                            self.session.session_store.append_message("assistant", full_text)
                        # Return a sentinel so on_worker_state_changed knows it's streaming
                        return _StreamingDone()

                    self.run_worker(_stream_worker, thread=True, exit_on_error=False)
                    return
            # Fall through: LLM is None/unconfigured or has no generate_stream
            # or _has_draft() is True (revisions use run_once path) →
            # use the standard run_once path (handles DialogueGuard blocking too).

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
            if isinstance(result, _StreamingDone):
                # Streaming path completed — just re-enable input.
                self._finish_processing()
            else:
                self._handle_result(result)
        elif event.state == WorkerState.ERROR:
            self._handle_error(event.worker)

    def _finish_processing(self) -> None:
        """Re-enable the input prompt after any worker (streaming or run_once) finishes."""
        prompt = self.query_one("#prompt", ChatTextArea)
        prompt.border_title = ""
        prompt.disabled = False
        prompt.focus()
        self._is_processing = False

    def _handle_result(self, result) -> None:
        """Called on the UI thread after the run_once worker completes successfully."""
        try:
            if result is not None and getattr(result, "message", ""):
                msg = result.message
                is_md = getattr(result, "markdown", False)
                self._append_to_log(msg, is_markdown=is_md)

            if result is not None and getattr(result, "exit_session", False):
                self.exit()
        except Exception as e:
            try:
                self._append_to_log(f"[错误] 渲染失败: {e}", classes="system-msg")
            except Exception:
                pass
        finally:
            # Always re-enable input, even if rendering raised
            self._finish_processing()

    def _handle_error(self, worker) -> None:
        """Called on the UI thread if the worker raised an exception."""
        try:
            self._append_to_log(f"[错误] {worker.error}", classes="system-msg")
        except Exception:
            pass
        finally:
            self._finish_processing()


# ---------------------------------------------------------------------------
# Internal sentinel — returned by the streaming worker to signal completion
# ---------------------------------------------------------------------------


class _StreamingDone:
    """Sentinel returned from the streaming worker thread.

    ``on_worker_state_changed`` checks ``isinstance(result, _StreamingDone)``
    to distinguish the streaming path from the run_once path.
    """
