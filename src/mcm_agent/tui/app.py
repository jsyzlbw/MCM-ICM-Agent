from __future__ import annotations

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style

from mcm_agent.config import load_settings
from mcm_agent.core.workspace import load_workspace_state
from mcm_agent.tui.completers import MagCompleter
from mcm_agent.tui.keybindings import build_key_bindings
from mcm_agent.tui.statusbar import bottom_toolbar
from mcm_agent.tui.theme import ACCENT

_PROMPT_STYLE = Style.from_dict({"prompt": f"{ACCENT} bold"})


class PromptUI:
    """prompt_toolkit input loop. Owns input only; rich still renders all output.
    run_once stays the single logic entry."""

    def __init__(self, session, *, input=None, output=None) -> None:
        self.session = session
        self._input = input
        self._output = output
        self._completer = MagCompleter(session.commands, session.workspace_root)
        self._toolbar_cache: str | None = None

    def _toolbar(self):
        # prompt_toolkit calls this on every keystroke; the workspace state only
        # changes when a command runs, so cache the rendering between commands.
        if self._toolbar_cache is None:
            state = load_workspace_state(self.session.workspace_root)
            settings = load_settings(workspace_root=self.session.workspace_root)
            self._toolbar_cache = bottom_toolbar(state, settings)
        return self._toolbar_cache

    def _invalidate_caches(self) -> None:
        """Drop per-keystroke caches after a command may have changed the workspace."""
        self._toolbar_cache = None
        self._completer.invalidate()

    def loop(self) -> None:
        history_path = self.session.workspace_root / ".mag" / "history"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        ps = PromptSession(
            history=FileHistory(str(history_path)),
            completer=self._completer,
            complete_while_typing=True,
            key_bindings=build_key_bindings(),
            bottom_toolbar=self._toolbar,
            input=self._input,
            output=self._output,
        )
        self.session._print_welcome()
        while True:
            try:
                with patch_stdout():
                    text = ps.prompt(HTML("<prompt>&gt; </prompt>"), style=_PROMPT_STYLE)
            except KeyboardInterrupt:
                continue
            except EOFError:
                return
            result = self.session.run_once(text)
            self._invalidate_caches()
            if result.message:
                self.session._render_result(result)
            if result.exit_session:
                return
