from __future__ import annotations

from pathlib import Path

from rich.console import Console

from mcm_agent.cli_commands import build_command_registry
from mcm_agent.cli_commands.base import CommandContext, CommandResult
from mcm_agent.core.dialogue_guard import DialogueGuard
from mcm_agent.core.revision_plan import create_revision_plan
from mcm_agent.core.session_store import SessionStore
from mcm_agent.core.workspace import create_workspace, is_mag_workspace, load_workspace_state
from mcm_agent.core.workspace_safety import WorkspaceSafety


class InteractiveSession:
    def __init__(self, workspace_root: Path, console: Console | None = None):
        self.workspace_root = workspace_root.resolve()
        self.console = console or Console()
        self.commands = build_command_registry()
        self.session_store = SessionStore(self.workspace_root)

    @classmethod
    def prepare(cls, cwd: Path, console: Console | None = None) -> "InteractiveSession":
        cwd = cwd.resolve()
        if is_mag_workspace(cwd):
            return cls(cwd, console=console)
        if any(cwd.iterdir()):
            raise ValueError(
                "当前文件夹不为空，并且没有发现 Mag workspace。请在空文件夹中运行 mag，"
                "或显式运行 mag init --force。"
            )
        create_workspace(cwd)
        return cls(cwd, console=console)

    def startup_text(self) -> str:
        state = load_workspace_state(self.workspace_root)
        return "\n".join(
            [
                "Mag",
                "MCM/ICM Modeling Agent",
                "",
                f"Workspace: {self.workspace_root.name}",
                f"Status: {state.phase}",
                "",
                "Type /init to set up this workspace.",
                "Type /help to see commands.",
            ]
        )

    def run_once(self, text: str) -> CommandResult:
        stripped = text.strip()
        if not stripped:
            return CommandResult("")
        self.session_store.append_message("user", stripped)
        if stripped == "/help":
            self.session_store.append_event("command.started", {"command": "help"})
            lines = ["Commands:"]
            for name in sorted(self.commands):
                command = self.commands[name]
                lines.append(f"  /{name} - {command.summary}")
            result = CommandResult("\n".join(lines))
            self.session_store.append_message("assistant", result.message)
            self.session_store.append_event("command.finished", {"command": "help"})
            return result
        if stripped.startswith("/"):
            parts = stripped[1:].split()
            name, args = parts[0], parts[1:]
            command = self.commands.get(name)
            if command is None:
                result = CommandResult(f"Unknown command: /{name}")
                self.session_store.append_message("assistant", result.message)
                return result
            self.session_store.append_event("command.started", {"command": name})
            result = command.run(args, CommandContext(workspace_root=self.workspace_root))
            if result.message:
                self.session_store.append_message("assistant", result.message)
            self.session_store.append_event("command.finished", {"command": name})
            return result
        result = self._handle_natural_language(stripped)
        if result.message:
            self.session_store.append_message("assistant", result.message)
        return result

    def run(self) -> None:
        self.console.print(self.startup_text())
        while True:
            try:
                text = self.console.input("> ")
            except (EOFError, KeyboardInterrupt):
                self.console.print()
                return
            result = self.run_once(text)
            if result.message:
                self.console.print(result.message)
            if result.exit_session:
                return

    def _handle_natural_language(self, text: str) -> CommandResult:
        state = load_workspace_state(self.workspace_root)
        guard = DialogueGuard.evaluate(state, text)
        if not guard.allowed:
            return CommandResult(guard.message)
        if guard.message:
            return CommandResult(guard.message)
        if self._has_draft():
            plan = create_revision_plan(self.workspace_root, text)
            WorkspaceSafety(self.workspace_root).checkpoint(f"mag: create {plan.revision_id}")
            return CommandResult(
                f"Revision plan created: work/revisions/{plan.revision_id}.md\n"
                "请确认后再执行修订，当前论文尚未被修改。"
            )
        return CommandResult("我已收到你的想法。正式分析请运行 /start。")

    def _has_draft(self) -> bool:
        return any(
            path.exists()
            for path in [
                self.workspace_root / "output/draft/main.pdf",
                self.workspace_root / "output/draft/main.tex",
                self.workspace_root / "paper/main.tex",
            ]
        )
