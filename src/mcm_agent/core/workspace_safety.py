from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from mcm_agent.providers.github import GitPushAdapter
from mcm_agent.utils.json_io import append_jsonl


DEFAULT_GITIGNORE_LINES = [
    ".env",
    ".mag/cache/",
    ".mag/logs/*.debug.json",
    ".mag/logs/*raw*",
    "__pycache__/",
    ".DS_Store",
]


@dataclass(frozen=True)
class WorkspaceGitStatus:
    enabled: bool
    clean: bool
    last_commit: str | None
    remote: str | None
    branch: str | None


class WorkspaceSafety:
    """Git-backed recovery helpers for Mag workspaces."""

    def __init__(self, root: Path, push_adapter: GitPushAdapter | None = None):
        self.root = root.resolve()
        self.push_adapter = push_adapter or GitPushAdapter()

    def ensure_git_repo(self) -> None:
        if not (self.root / ".git").exists():
            self._git("init")

    def ensure_gitignore(self) -> None:
        path = self.root / ".gitignore"
        existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        lines = list(existing)
        for line in DEFAULT_GITIGNORE_LINES:
            if line not in lines:
                lines.append(line)
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def checkpoint(self, message: str) -> str | None:
        self.ensure_git_repo()
        self.ensure_gitignore()
        self._git("add", "-A")
        if self._is_index_clean():
            return self.status().last_commit
        self._git(
            "-c",
            "user.name=Mag",
            "-c",
            "user.email=mag@example.local",
            "commit",
            "-m",
            message,
        )
        status = self.status()
        if self.auto_push_enabled():
            result = self.push_adapter.push(self.root, status.remote or "origin", status.branch)
            append_jsonl(
                self.root / ".mag" / "logs" / "git_push_history.jsonl",
                {
                    "success": result.success,
                    "message": result.message,
                    "remote": status.remote or "origin",
                    "branch": status.branch or "",
                },
            )
        return status.last_commit

    def auto_push_enabled(self) -> bool:
        config_path = self.root / ".mag" / "config.toml"
        if not config_path.exists():
            return False
        return "auto_push = true" in config_path.read_text(encoding="utf-8")

    def status(self) -> WorkspaceGitStatus:
        enabled = (self.root / ".git").exists()
        if not enabled:
            return WorkspaceGitStatus(
                enabled=False,
                clean=True,
                last_commit=None,
                remote=None,
                branch=None,
            )
        clean = self._run_git("status", "--porcelain").stdout.strip() == ""
        last_commit_result = self._run_git("rev-parse", "--short", "HEAD", check=False)
        last_commit = (
            last_commit_result.stdout.strip()
            if last_commit_result.returncode == 0
            else None
        )
        remote_result = self._run_git("remote", "get-url", "origin", check=False)
        remote = remote_result.stdout.strip() if remote_result.returncode == 0 else None
        branch_result = self._run_git("branch", "--show-current", check=False)
        branch = branch_result.stdout.strip() or None
        return WorkspaceGitStatus(
            enabled=True,
            clean=clean,
            last_commit=last_commit,
            remote=remote,
            branch=branch,
        )

    def _is_index_clean(self) -> bool:
        return self._run_git("diff", "--cached", "--quiet", check=False).returncode == 0

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self._run_git(*args, check=True)

    def _run_git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=check,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
