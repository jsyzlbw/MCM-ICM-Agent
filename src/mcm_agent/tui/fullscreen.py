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

        # Determine render width (capped at 100, min terminal minus borders)
        self._width: int = self._calc_width()

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

    def run(self) -> None:
        """Start the event loop; blocks until the app exits."""
        # Prepend welcome panel
        self._append_welcome()
        self._app.run()

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

    def _build_keybindings(self) -> KeyBindings:
        kb = KeyBindings()
        input_area = self._input_area

        # Track Ctrl-C presses for double-tap exit
        _ctrl_c_count: list[int] = [0]

        @kb.add("c-d")
        def _exit(event):
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
                    event.app.exit()

        @kb.add("escape", "enter")
        def _newline(event):
            """Alt+Enter inserts a newline."""
            input_area.buffer.insert_text("\n")

        @kb.add("enter")
        def _submit(event):
            """Enter submits the current input synchronously."""
            buf = input_area.buffer
            text = buf.text
            if not text.strip():
                return
            buf.reset()
            _ctrl_c_count[0] = 0

            # Echo user input
            from rich.text import Text as RText
            from mcm_agent.tui.theme import ACCENT

            self._append(
                render_to_ansi(RText(f"> {text}", style=ACCENT), width=self._width)
            )

            # Route the input
            if text.startswith("!"):
                shell_cmd = text[1:].strip()
                result = self._session._run_shell(shell_cmd)
                self._append(
                    render_to_ansi(
                        self._rich_result(result), width=self._width
                    )
                )
                if result.exit_session:
                    event.app.exit()
            else:
                result = self._session.run_once(text)
                if result.message:
                    self._append(
                        render_to_ansi(
                            self._rich_result(result), width=self._width
                        )
                    )
                if result.exit_session:
                    event.app.exit()

            self._pin_bottom()
            event.app.invalidate()

        return kb

    def _rich_result(self, result: object) -> object:
        """Convert a CommandResult to a Rich renderable."""
        from rich.markdown import Markdown
        from rich.text import Text

        msg = getattr(result, "message", "") or ""
        if getattr(result, "markdown", False):
            return Markdown(msg)
        return Text(msg)
