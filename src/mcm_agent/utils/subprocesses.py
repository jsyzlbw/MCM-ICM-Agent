from __future__ import annotations

import subprocess
import time
from pathlib import Path

from pydantic import BaseModel


class CommandResult(BaseModel):
    command: list[str]
    return_code: int
    stdout: str
    stderr: str
    duration_seconds: float


def run_command(command: list[str], cwd: Path, timeout_seconds: int) -> CommandResult:
    start = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return CommandResult(
            command=command,
            return_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=time.monotonic() - start,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=command,
            return_code=-1,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + "\ntimeout",
            duration_seconds=time.monotonic() - start,
        )
