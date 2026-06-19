from __future__ import annotations

from pathlib import Path

from mcm_agent.cli_commands.base import CommandContext, CommandResult
from mcm_agent.core.workspace_safety import WorkspaceSafety


class GitCommand:
    name = "git"
    summary = "查看 Git checkpoint 和远端同步状态。"

    def run(self, args: list[str], context: CommandContext) -> CommandResult:
        root = Path(context.workspace_root)
        status = WorkspaceSafety(root).status()
        lines = [
            "Git safety net",
            f"Local repository: {'enabled' if status.enabled else 'disabled'}",
            f"Working tree: {'clean' if status.clean else 'dirty'}",
            f"Last checkpoint: {status.last_commit or 'none'}",
            f"Remote: {status.remote or 'not configured'}",
            f"Branch: {status.branch or 'unknown'}",
            f"Auto push: {'enabled' if WorkspaceSafety(root).auto_push_enabled() else 'disabled'}",
        ]
        history = root / ".mag" / "logs" / "git_push_history.jsonl"
        if history.exists():
            last = [line for line in history.read_text(encoding="utf-8").splitlines() if line.strip()]
            if last:
                lines.append(f"Last push record: {last[-1]}")
        return CommandResult("\n".join(lines))
