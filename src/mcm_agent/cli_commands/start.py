from __future__ import annotations

from pathlib import Path

from mcm_agent.cli_commands.base import CommandContext, CommandResult
from mcm_agent.core.research_script import build_initial_research_script, write_research_script
from mcm_agent.core.workspace import load_workspace_state, save_workspace_state
from mcm_agent.core.workspace_safety import WorkspaceSafety
from mcm_agent.core.workflow_adapter import WorkspaceWorkflowAdapter


class StartCommand:
    name = "start"
    summary = "开始题目分析和研究讨论。"

    def run(self, args: list[str], context: CommandContext) -> CommandResult:
        root = Path(context.workspace_root)
        state = load_workspace_state(root)
        if not state.init.llm_configured:
            return CommandResult("LLM API is required before analysis can start. Run /api or /init.")
        if not state.init.problem_imported:
            return CommandResult("No problem file found. Run /question first.")
        script = build_initial_research_script(root)
        lock = "--lock" in args
        write_research_script(root, script, locked=lock)
        state.phase = "script_locked" if lock else "discussing"
        save_workspace_state(root, state)
        WorkspaceSafety(root).checkpoint(
            "mag: lock research script" if lock else "mag: draft research script"
        )
        if lock:
            if "--run" in args:
                WorkspaceWorkflowAdapter(root).run_default_workflow(auto_approve=True)
                return CommandResult(
                    "Research script locked and workflow completed. See output/draft and output/package."
                )
            return CommandResult(
                "Research script locked. Next implementation stage can start from workflow adapter."
            )
        return CommandResult(
            "Research script draft created at work/discussion/research_script_draft.md.\n"
            "Review it, discuss changes, then run /start --lock when ready."
        )
