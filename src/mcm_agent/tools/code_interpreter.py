from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ExecResult:
    stdout: str
    error: str
    had_error: bool
    images: tuple[str, ...] = field(default=())


@runtime_checkable
class CodeInterpreter(Protocol):
    def add_section(self, title: str) -> None: ...
    def execute(self, code: str) -> ExecResult: ...
    def save_notebook(self) -> None: ...
    def shutdown(self) -> None: ...
