from __future__ import annotations

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style

from mcm_agent.config import load_settings
from mcm_agent.core.workspace import load_workspace_state
from mcm_agent.tui.completers import SlashCommandCompleter
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

    def _toolbar(self):
        state = load_workspace_state(self.session.workspace_root)
        settings = load_settings(workspace_root=self.session.workspace_root)
        return bottom_toolbar(state, settings)

    def loop(self) -> None:
        history_path = self.session.workspace_root / ".mag" / "history"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        ps = PromptSession(
            history=FileHistory(str(history_path)),
            completer=SlashCommandCompleter(self.session.commands),
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
            if result.message:
                self.session._print(result.message)
            if result.exit_session:
                return
