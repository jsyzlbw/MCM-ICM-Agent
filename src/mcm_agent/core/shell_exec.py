from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ShellResult:
    exit_code: int
    stdout: str
    stderr: str


def run_shell(
    workspace_root: Path, command: str, *, timeout_seconds: int = 120
) -> ShellResult:
    """Run a shell command in the workspace dir, capturing output. Never raises;
    a timeout returns exit_code 124 with a note appended to stderr."""
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return ShellResult(proc.returncode, proc.stdout, proc.stderr)
    except subprocess.TimeoutExpired as exc:
        def _decode(value: object) -> str:
            if isinstance(value, bytes):
                return value.decode("utf-8", "replace")
            return value or ""

        return ShellResult(
            124,
            _decode(exc.stdout),
            _decode(exc.stderr) + f"\n[timed out after {timeout_seconds}s]",
        )
