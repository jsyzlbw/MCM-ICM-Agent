from __future__ import annotations

from pathlib import Path
import shutil

from mcm_agent.agents.discussion import confirmed_language
from mcm_agent.cli_commands.base import CommandContext, CommandResult
from mcm_agent.config import load_settings
from mcm_agent.core.workspace import load_workspace_state
from mcm_agent.core.workspace_safety import WorkspaceSafety


class StatusCommand:
    name = "status"
    summary = "查看当前 workspace 状态。"

    def run(self, args: list[str], context: CommandContext) -> CommandResult:
        root = Path(context.workspace_root)
        state = load_workspace_state(root)
        git_status = WorkspaceSafety(root).status()
        settings = load_settings(workspace_root=root)
        llm_model = settings.openai_model if settings.openai_api_key else "not configured"
        lines = [
            "Workspace status",
            f"Phase: {state.phase}",
            f"Init completed: {state.init.completed}",
            f"LLM configured: {state.init.llm_configured} ({llm_model})",
            f"Problem imported: {state.init.problem_imported}",
            f"RAG documents: {state.init.rag_documents}",
            f"Data files: {state.init.data_files}",
            f"Layout imported: {state.init.layout_imported}",
            f"Paper language: {confirmed_language(root)}",
            f"Last checkpoint: {git_status.last_commit or 'none'}",
        ]
        return CommandResult("\n".join(lines))


class OutputsCommand:
    name = "outputs"
    summary = "查看已生成输出。"

    def run(self, args: list[str], context: CommandContext) -> CommandResult:
        root = Path(context.workspace_root)
        candidates = [
            root / "output/draft/main.pdf",
            root / "output/final/main.pdf",
            root / "output/package/submission_package.zip",
            root / "final_submission/submission_package.zip",
        ]
        present = [path for path in candidates if path.exists()]
        if not present:
            return CommandResult("No outputs generated yet.")
        lines = ["Outputs:", *[str(path.relative_to(root)) for path in present]]
        return CommandResult("\n".join(lines))


class ResetCommand:
    name = "reset"
    summary = "清理或重置 workspace。"

    def run(self, args: list[str], context: CommandContext) -> CommandResult:
        root = Path(context.workspace_root)
        if args == ["rethink"]:
            WorkspaceSafety(root).checkpoint("mag: checkpoint before reset rethink")
            for relative in [".mag/chat", "work", "output"]:
                path = root / relative
                if path.exists():
                    shutil.rmtree(path)
            for relative in [".mag/chat/sessions", "work/discussion", "output/draft"]:
                (root / relative).mkdir(parents=True, exist_ok=True)
            (root / ".mag/chat/messages.jsonl").write_text("", encoding="utf-8")
            WorkspaceSafety(root).checkpoint("mag: reset rethink")
            return CommandResult("Re-think reset complete.")
        return CommandResult("Usage: /reset rethink")
