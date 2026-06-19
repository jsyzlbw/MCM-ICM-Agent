from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class GitPushResult:
    success: bool
    message: str


class GitPushAdapter:
    def push(self, root: Path, remote: str = "origin", branch: str | None = None) -> GitPushResult:
        args = ["git", "push", remote]
        if branch:
            args.append(branch)
        result = subprocess.run(
            args,
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode == 0:
            return GitPushResult(success=True, message=result.stdout.strip())
        return GitPushResult(success=False, message=(result.stderr or result.stdout).strip())
