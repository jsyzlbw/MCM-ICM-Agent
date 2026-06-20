"""Full-screen prompt_toolkit Application for Mag CLI.

Layout (top → bottom):
  1. Scrolling transcript Window  (FormattedTextControl, focusable=False)
  2. Frame(TextArea, title=<mode-aware callable>)  bordered input box
  3. Status bar Window  (height=1)

FloatContainer wraps the HSplit so CompletionsMenu appears above the cursor.

Usage::

    from mcm_agent.tui.fullscreen import MagFullScreenApp
    MagFullScreenApp(session).run()

Module-level helper::

    from mcm_agent.tui.fullscreen import render_to_ansi
    ansi = render_to_ansi(rich_renderable, width=80)
"""
from __future__ import annotations

import asyncio
import os
import threading
from typing import TYPE_CHECKING

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import ANSI, merge_formatted_text
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.containers import Float, FloatContainer
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.widgets import Frame, TextArea

if TYPE_CHECKING:
    from mcm_agent.cli_session import InteractiveSession


# ---------------------------------------------------------------------------
# render_to_ansi — module-level helper
# ---------------------------------------------------------------------------


def render_to_ansi(renderable: object, width: int = 100) -> ANSI:
    """Render any Rich renderable to an ANSI-escape string, capped at *width*."""
    from rich.console import Console

    con = Console(
        width=width,
        file=None,
        force_terminal=True,
        color_system="standard",
        highlight=False,
    )
    with con.capture() as cap:
        con.print(renderable)
    return ANSI(cap.get())


# ---------------------------------------------------------------------------
# MagFullScreenApp
# ---------------------------------------------------------------------------


class MagFullScreenApp:
    """Full-screen TUI: scrolling transcript + bordered Frame input.

    Parameters
    ----------
    session:
        An :class:`~mcm_agent.cli_session.InteractiveSession` instance.
    input:
        Optional prompt_toolkit input (for testing with pipe input).
    output:
        Optional prompt_toolkit output (for testing with DummyOutput).
    """

    def __init__(
        self,
        session: "InteractiveSession",
        *,
        input: object | None = None,
        output: object | None = None,
    ) -> None:
        self._session = session
        self._pt_input = input
        self._pt_output = output

        # Transcript: list of ANSI fragments rendered by rich
        self._fragments: list[ANSI] = []

        # Track in-flight async submit tasks so run() can await them on exit
        self._pending_tasks: list[asyncio.Task] = []  # type: ignore[type-arg]

        # Determine render width (capped at 100, min terminal minus borders)
        self._width: int = self._calc_width()

        # Ask/printer bridge — allows executor-thread commands to prompt the user
        # through the app instead of raw stdin/stdout.
        self._awaiting_ask: bool = False
        self._ask_event: threading.Event | None = None
        self._ask_answer: str = ""
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thinking_frag: ANSI | None = None
        # Input queue: Enter presses that arrive while a task is in-flight are
        # buffered here so _thread_ask can consume them instead of starting a
        # new top-level submission (fixes the pipe-input race condition).
        self._input_queue: list[str] = []

        # Build the layout components
        self._transcript_window = Window(
            content=FormattedTextControl(self._get_transcript, focusable=False),
            wrap_lines=True,
        )

        from mcm_agent.tui.completers import MagCompleter

        self._input_area = TextArea(
            height=Dimension(min=1, max=8),
            multiline=True,
            completer=MagCompleter(session.commands, session.workspace_root),
            focus_on_click=True,
            prompt="> ",
        )

        body = FloatContainer(
            content=HSplit(
                [
                    self._transcript_window,
                    Frame(
                        self._input_area,
                        title=self._frame_title,
                    ),
                    Window(
                        content=FormattedTextControl(self._status_text),
                        height=1,
                    ),
                ]
            ),
            floats=[
                Float(
                    xcursor=True,
                    ycursor=True,
                    content=CompletionsMenu(max_height=8, scroll_offset=1),
                )
            ],
        )

        kb = self._build_keybindings()

        self._app = Application(
            layout=Layout(body, focused_element=self._input_area),
            key_bindings=kb,
            full_screen=True,
            mouse_support=False,
        )
        if input is not None:
            self._app.input = input  # type: ignore[assignment]
        if output is not None:
            self._app.output = output  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def session(self) -> "InteractiveSession":
        return self._session

    def run(self) -> None:
        """Start the event loop; blocks until the app exits.

        Sets ``session.suppress_live_output = True`` for the duration so that
        LLM replies are returned (not streamed to raw stdout underneath
        prompt_toolkit's alternate screen).  The Enter handler dispatches work
        via ``run_in_executor`` so the UI thread stays responsive.
        """
        # Prepend welcome panel
        self._append_welcome()

        old_suppress = getattr(self._session, "suppress_live_output", False)
        old_io_printer = getattr(self._session, "_io_printer", None)
        old_io_ask = getattr(self._session, "_io_ask", None)
        self._session.suppress_live_output = True
        self._session._io_printer = self._thread_printer
        self._session._io_ask = self._thread_ask
        try:
            asyncio.run(self._run_async_and_drain())
        finally:
            self._session.suppress_live_output = old_suppress
            self._session._io_printer = old_io_printer
            self._session._io_ask = old_io_ask

    async def _run_async_and_drain(self) -> None:
        """Run the app, then wait for any in-flight submit tasks to finish."""
        self._loop = asyncio.get_running_loop()
        await self._app.run_async()
        # Drain any executor tasks that were submitted but not yet complete
        # (e.g. when Ctrl-D arrives while a run_once call is in-flight).
        if self._pending_tasks:
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)
            self._pending_tasks.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calc_width(self) -> int:
        try:
            cols = os.get_terminal_size().columns
        except OSError:
            cols = 100
        return min(cols - 2, 100)

    def _get_transcript(self):
        """Return merged formatted text for the transcript window."""
        if not self._fragments:
            return []
        return merge_formatted_text(list(self._fragments))

    def _frame_title(self) -> str:
        """Dynamic Frame title that reflects the current input mode."""
        text = self._input_area.text
        first = text[:1]
        if first == "!":
            return " shell "
        if first == "/":
            return " 命令 "
        if first == "@":
            return " 文件 "
        return " 讨论 "

    def _status_text(self) -> str:
        text = self._input_area.text
        first = text[:1]
        if first == "!":
            mode = "shell"
        elif first == "/":
            mode = "命令"
        elif first == "@":
            mode = "文件"
        else:
            mode = "讨论"
        try:
            from mcm_agent.config import load_settings
            from mcm_agent.core.workspace import load_workspace_state
            from mcm_agent.tui.statusbar import bottom_toolbar

            state = load_workspace_state(self._session.workspace_root)
            settings = load_settings(workspace_root=self._session.workspace_root)
            base = bottom_toolbar(state, settings)
        except Exception:
            base = "/help 命令 · / 菜单 · ! shell · @ 文件 · ? 快捷键"
        return f"[{mode}] {base}"

    def _append(self, fragment: ANSI) -> None:
        self._fragments.append(fragment)
        self._pin_bottom()

    def _pin_bottom(self) -> None:
        self._transcript_window.vertical_scroll = 10**9  # pt clamps to max

    def _append_welcome(self) -> None:
        try:
            from mcm_agent.config import load_settings
            from mcm_agent.core.workspace import load_workspace_state
            from mcm_agent.tui.welcome import render_welcome_panel
            from mcm_agent.version import __version__

            state = load_workspace_state(self._session.workspace_root)
            settings = load_settings(workspace_root=self._session.workspace_root)
            panel = render_welcome_panel(
                state, settings, __version__, self._session.workspace_root
            )
            self._append(render_to_ansi(panel, width=self._width))
        except Exception:
            pass  # welcome is non-critical

    # ------------------------------------------------------------------
    # Ask/printer bridge — called from executor thread, bridges to UI loop
    # ------------------------------------------------------------------

    def _thread_printer(self, text: str) -> None:
        """Printer called from a command running in the executor thread.
        Routes output into the transcript via call_soon_threadsafe."""
        from rich.text import Text

        def _do() -> None:
            self._append(render_to_ansi(Text(str(text)), width=self._width))
            if self._app.is_running:
                self._app.invalidate()

        if self._loop:
            self._loop.call_soon_threadsafe(_do)

    def _thread_ask(self, prompt: str = "") -> str:
        """Ask function called from the executor thread.
        Shows the prompt in the transcript and blocks until the user answers.

        If a queued input was already buffered (pipe input / fast typing), it is
        consumed immediately without waiting for a new keypress.
        """
        ev = threading.Event()
        self._ask_event = ev
        self._ask_answer = ""

        def _begin() -> None:
            # Remove the transient "正在处理…" indicator while waiting for input
            if self._thinking_frag is not None:
                try:
                    self._fragments.remove(self._thinking_frag)
                except ValueError:
                    pass
                self._thinking_frag = None
            if prompt:
                from rich.text import Text

                self._append(render_to_ansi(Text(str(prompt)), width=self._width))
            # If a queued input is already available (e.g. from pipe), consume it
            # immediately rather than waiting for a new keypress.
            if self._input_queue:
                answer = self._input_queue.pop(0)
                from rich.text import Text as _T

                from mcm_agent.tui.theme import ACCENT

                self._append(render_to_ansi(_T(f"> {answer}", style=ACCENT), width=self._width))
                self._ask_answer = answer
                ev.set()
                if self._app.is_running:
                    self._app.invalidate()
            else:
                self._awaiting_ask = True
                if self._app.is_running:
                    self._app.invalidate()

        if self._loop:
            self._loop.call_soon_threadsafe(_begin)
        ev.wait()
        return self._ask_answer

    def _build_keybindings(self) -> KeyBindings:
        kb = KeyBindings()
        input_area = self._input_area

        # Track Ctrl-C presses for double-tap exit
        _ctrl_c_count: list[int] = [0]

        @kb.add("c-d")
        def _exit(event):
            # Release any blocked _thread_ask before exiting to prevent deadlock
            if self._awaiting_ask:
                self._ask_answer = ""
                self._awaiting_ask = False
                if self._ask_event is not None:
                    self._ask_event.set()
            event.app.exit()

        @kb.add("c-c")
        def _ctrl_c(event):
            buf = input_area.buffer
            if buf.text:
                # First C-c: clear current input
                buf.reset()
                _ctrl_c_count[0] = 0
            else:
                _ctrl_c_count[0] += 1
                if _ctrl_c_count[0] >= 2:
                    # Release any blocked _thread_ask before exiting
                    if self._awaiting_ask:
                        self._ask_answer = ""
                        self._awaiting_ask = False
                        if self._ask_event is not None:
                            self._ask_event.set()
                    event.app.exit()

        @kb.add("escape", "enter")
        def _newline(event):
            """Alt+Enter inserts a newline."""
            input_area.buffer.insert_text("\n")

        @kb.add("enter")
        def _submit(event):
            """Enter submits the current input; work runs off the UI thread."""
            buf = input_area.buffer

            # If a command thread is waiting for an answer via _thread_ask,
            # treat this Enter as the answer — do NOT start a new submission.
            if self._awaiting_ask:
                answer = buf.text
                buf.reset()
                self._awaiting_ask = False
                from rich.text import Text as _T

                from mcm_agent.tui.theme import ACCENT

                self._append(render_to_ansi(_T(f"> {answer}", style=ACCENT), width=self._width))
                self._ask_answer = answer
                if self._ask_event is not None:
                    self._ask_event.set()
                event.app.invalidate()
                return

            text = buf.text
            if not text.strip():
                return
            buf.reset()
            _ctrl_c_count[0] = 0

            # If a task is already in-flight, queue this input so it can be
            # consumed by _thread_ask (handles pipe input / fast typing races).
            if self._pending_tasks:
                self._input_queue.append(text)
                return

            # Schedule actual async work as a task so it can be tracked/drained
            task = asyncio.ensure_future(self._do_submit(event.app, text))
            self._pending_tasks.append(task)

            def _on_done(t: asyncio.Task) -> None:  # type: ignore[type-arg]
                try:
                    self._pending_tasks.remove(t)
                except ValueError:
                    pass

            task.add_done_callback(_on_done)

        return kb

    async def _do_submit(self, app: Application, text: str) -> None:  # type: ignore[type-arg]
        """Async body for the Enter handler — runs executor work off the UI thread."""
        from rich.text import Text as RText

        from mcm_agent.tui.theme import ACCENT

        self._append(
            render_to_ansi(RText(f"> {text}", style=ACCENT), width=self._width)
        )

        # Show a transient "processing" indicator (stored on self so _thread_ask can remove it)
        thinking_frag = ANSI("∑ 正在处理…\n")
        self._thinking_frag = thinking_frag
        self._fragments.append(thinking_frag)
        app.invalidate()

        # Run the blocking work off the UI event loop
        loop = asyncio.get_event_loop()
        if text.startswith("!"):
            shell_cmd = text[1:].strip()
            result = await loop.run_in_executor(
                None, self._session._run_shell, shell_cmd
            )
        else:
            result = await loop.run_in_executor(
                None, self._session.run_once, text
            )

        # Remove the transient fragment (may have been removed by _thread_ask already)
        self._thinking_frag = None
        try:
            self._fragments.remove(thinking_frag)
        except ValueError:
            pass

        # Append rendered result to transcript
        if result.message:
            self._append(
                render_to_ansi(self._rich_result(result), width=self._width)
            )

        if result.exit_session:
            app.exit()

        app.invalidate()

    def _rich_result(self, result: object) -> object:
        """Convert a CommandResult to a Rich renderable."""
        from rich.markdown import Markdown
        from rich.text import Text

        msg = getattr(result, "message", "") or ""
        if getattr(result, "markdown", False):
            return Markdown(msg)
        return Text(msg)
