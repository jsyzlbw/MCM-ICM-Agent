from __future__ import annotations

from pathlib import Path

from mcm_agent.cli_commands.base import CommandContext, CommandResult
from mcm_agent.config import load_settings
from mcm_agent.core.research_script import build_initial_research_script, write_research_script
from mcm_agent.core.workspace import load_workspace_state, save_workspace_state
from mcm_agent.core.workspace_safety import WorkspaceSafety
from mcm_agent.core.workflow_adapter import WorkspaceWorkflowAdapter
from mcm_agent.utils.json_io import read_json, write_json


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
        language = self._extract_language(args)
        lock = "--lock" in args
        # Draft path: use the LLM to analyze the problem so the user has something
        # substantive to react to. Lock/run path skips it (the workflow re-analyzes).
        llm = None if lock else self._analysis_llm(root, context)
        script = build_initial_research_script(root, language=language, llm=llm)
        write_research_script(root, script, locked=lock)
        if lock:
            self._persist_language(root, language)
        state.phase = "script_locked" if lock else "discussing"
        save_workspace_state(root, state)
        WorkspaceSafety(root).checkpoint(
            "mag: lock research script" if lock else "mag: draft research script"
        )
        if lock:
            if "--run" in args:
                printer = context.printer
                progress = (lambda text: printer(f"… {text}")) if callable(printer) else None
                WorkspaceWorkflowAdapter(root).run_default_workflow(
                    auto_approve=True, progress=progress
                )
                return CommandResult(
                    "Research script locked and workflow completed. See output/draft and output/package."
                )
            return CommandResult(
                "Research script locked. Next implementation stage can start from workflow adapter."
            )
        if script.analysis:
            return CommandResult(
                f"{script.analysis}\n\n"
                "————\n"
                "（草稿已存到 work/discussion/research_script_draft.md）\n"
                "直接打字和我讨论、调整方向；满意后运行 /start --lock --run 开始求解并写论文。"
            )
        return CommandResult(
            "Research script draft created at work/discussion/research_script_draft.md.\n"
            "（未能生成题目分析——通常是网络/接口问题，可运行 /api 选 [4] 测连通。）\n"
            "直接打字讨论方向，满意后运行 /start --lock --run。"
        )

    def _analysis_llm(self, root: Path, context: CommandContext) -> object | None:
        """Best-effort LLM for problem analysis; None if unavailable (then /start
        degrades to the static template)."""
        try:
            from mcm_agent.providers.factory import build_llm_provider

            provider = build_llm_provider(load_settings(workspace_root=root))
            return None if type(provider).__name__ == "FakeLLMProvider" else provider
        except Exception:
            return None

    def _extract_language(self, args: list[str]) -> str:
        if "--language" in args:
            index = args.index("--language")
            if index + 1 < len(args):
                return args[index + 1]
        return "en"

    def _persist_language(self, root, language: str) -> None:
        lock_path = root / "discussion" / "direction_lock.json"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        payload = read_json(lock_path, {})
        if not isinstance(payload, dict):
            payload = {}
        payload["language"] = language
        write_json(lock_path, payload)
