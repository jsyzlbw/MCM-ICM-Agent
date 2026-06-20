from __future__ import annotations

from pathlib import Path

from rich.console import Console

from mcm_agent.cli_commands import build_command_registry
from mcm_agent.cli_commands.base import CommandContext, CommandResult
from mcm_agent.core.chat import generate_chat_reply
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
        next_hint = (
            "Type /start to analyze the problem, or just type to discuss."
            if state.init.completed
            else "Type /init to set up this workspace."
        )
        return "\n".join(
            [
                "Mag",
                "MCM/ICM Modeling Agent",
                "",
                f"Workspace: {self.workspace_root.name}",
                f"Status: {state.phase}",
                "",
                next_hint,
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
            lines.append("")
            lines.append("直接输入自然语言即可与 Agent 讨论题目。")
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
            result = command.run(
                args,
                CommandContext(
                    workspace_root=self.workspace_root,
                    printer=self._print,
                    ask=self._make_ask(),
                ),
            )
            if result.message:
                self.session_store.append_message("assistant", result.message)
            self.session_store.append_event("command.finished", {"command": name})
            return result
        result = self._handle_natural_language(stripped)
        if result.message:
            self.session_store.append_message("assistant", result.message)
        return result

    def _print(self, message: str) -> None:
        # Command output is plain text — disable rich markup/highlight so tokens like
        # "[ok]" / "[missing]" are shown literally instead of parsed as style tags.
        self.console.print(message, markup=False, highlight=False)

    def _make_ask(self):
        """A line-prompt callable for interactive commands, or None when there is no
        TTY (tests / pipes) so commands fall back to non-interactive behavior."""
        import sys

        try:
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                return None
        except Exception:
            return None
        return lambda prompt="": self.console.input(prompt, markup=False)

    def run(self) -> None:
        self._print(self.startup_text())
        while True:
            try:
                text = self.console.input("> ", markup=False)
            except (EOFError, KeyboardInterrupt):
                self.console.print()
                return
            result = self.run_once(text)
            if result.message:
                self._print(result.message)
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
        recent = self.session_store.read_recent_messages(limit=8)
        reply = generate_chat_reply(self.workspace_root, text, self._chat_llm(), recent)
        return CommandResult(reply)

    def _chat_llm(self) -> object | None:
        try:
            from mcm_agent.core.workflow_adapter import WorkspaceWorkflowAdapter

            _settings, bundle = WorkspaceWorkflowAdapter(self.workspace_root).build_providers()
            return bundle.llm
        except Exception:
            return None

    def _has_draft(self) -> bool:
        return any(
            path.exists()
            for path in [
                self.workspace_root / "output/draft/main.pdf",
                self.workspace_root / "output/draft/main.tex",
                self.workspace_root / "paper/main.tex",
            ]
        )
