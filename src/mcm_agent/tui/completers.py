from __future__ import annotations

from prompt_toolkit.completion import Completer, Completion


class SlashCommandCompleter(Completer):
    """Completes '/<name>' from the command registry, showing each summary."""

    def __init__(self, commands: dict[str, object]) -> None:
        self._commands = commands

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/") or " " in text:
            return
        word = text[1:]
        for name in sorted(self._commands):
            if name.startswith(word):
                summary = getattr(self._commands[name], "summary", "")
                yield Completion(
                    name,
                    start_position=-len(word),
                    display=f"/{name}",
                    display_meta=summary,
                )
