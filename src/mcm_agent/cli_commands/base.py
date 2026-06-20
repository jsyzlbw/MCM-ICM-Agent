from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class CommandContext:
    workspace_root: object
    printer: object | None = None  # optional callable(str) for live progress output
    ask: object | None = None  # optional callable(prompt:str)->str for interactive prompts


@dataclass
class CommandResult:
    message: str
    exit_session: bool = False
    metadata: dict[str, str] = field(default_factory=dict)
    markdown: bool = False


class SlashCommand(Protocol):
    name: str
    summary: str

    def run(self, args: list[str], context: CommandContext) -> CommandResult:
        ...
