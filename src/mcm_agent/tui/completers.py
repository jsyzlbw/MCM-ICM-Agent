from __future__ import annotations

from pathlib import Path

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


_IGNORE_DIRS = {"work", "output", ".git", ".mag", "node_modules", "__pycache__"}


class AtFileCompleter(Completer):
    """Completes '@<path>' with workspace files, skipping noise/output dirs."""

    def __init__(self, workspace_root: Path) -> None:
        self._root = Path(workspace_root)
        self._cache: list[str] | None = None

    def invalidate(self) -> None:
        """Drop the cached file list so the next completion re-scans the workspace."""
        self._cache = None

    def _scan(self) -> list[str]:
        out: list[str] = []
        for path in self._root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(self._root)
            if any(part in _IGNORE_DIRS for part in rel.parts):
                continue
            out.append(rel.as_posix())
        return sorted(out)

    def _candidates(self) -> list[str]:
        if self._cache is None:
            self._cache = self._scan()
        return self._cache

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        at = text.rfind("@")
        if at == -1:
            return
        word = text[at + 1 :]
        if " " in word:
            return
        for rel in self._candidates():
            if rel.startswith(word):
                yield Completion(rel, start_position=-len(word), display=f"@{rel}")


class MagCompleter(Completer):
    """Dispatch to slash or file completion by the active token's prefix."""

    def __init__(self, commands: dict[str, object], workspace_root: Path) -> None:
        self._slash = SlashCommandCompleter(commands)
        self._at = AtFileCompleter(workspace_root)

    def invalidate(self) -> None:
        """Refresh the cached file list (call after the workspace may have changed)."""
        self._at.invalidate()

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/"):
            yield from self._slash.get_completions(document, complete_event)
        elif "@" in text:
            yield from self._at.get_completions(document, complete_event)
