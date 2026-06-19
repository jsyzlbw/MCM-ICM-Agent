from __future__ import annotations

from pathlib import Path
import shutil

from mcm_agent.cli_commands.base import CommandContext, CommandResult
from mcm_agent.core.workspace import create_workspace, load_workspace_state, save_workspace_state
from mcm_agent.core.workspace_safety import WorkspaceSafety


class InitCommand:
    name = "init"
    summary = "初始化 workspace 配置和资源。"

    def run(self, args: list[str], context: CommandContext) -> CommandResult:
        root = Path(context.workspace_root)
        state = load_workspace_state(root)
        if args and args[0] == "rethink":
            WorkspaceSafety(root).checkpoint("mag: checkpoint before rethink")
            self._rethink(root)
            state.phase = "init_incomplete"
            state.init.completed = False
            save_workspace_state(root, state)
            WorkspaceSafety(root).checkpoint("mag: rethink workspace")
            return CommandResult("Re-think complete. API/RAG/input files were kept.")
        if len(args) >= 2 and args[0] == "full-reset" and args[1] == "RESET":
            WorkspaceSafety(root).checkpoint("mag: checkpoint before full reset")
            self._full_reset(root)
            create_workspace(root)
            return CommandResult("Workspace fully reset.")
        if state.init.completed:
            return CommandResult(
                "This workspace has already been initialized.\n"
                "Use /init rethink or /init full-reset RESET."
            )
        llm_key = self._extract_option(args, "--llm-key")
        if not llm_key:
            return CommandResult(
                "LLM API 尚未配置。Usage: /init --llm-key <key> "
                "[--llm-base-url <url>] [--llm-model <model>]"
            )
        base_url = self._extract_option(args, "--llm-base-url")
        model = self._extract_option(args, "--llm-model")
        self._write_llm_config(root, llm_key, base_url, model)
        state.init.llm_configured = True
        state.init.completed = True
        state.phase = "init_complete"
        save_workspace_state(root, state)
        WorkspaceSafety(root).checkpoint("mag: complete init")
        return CommandResult("Init complete. LLM API configured; optional APIs skipped.")

    def _extract_option(self, args: list[str], option: str) -> str | None:
        if option not in args:
            return None
        index = args.index(option)
        if index + 1 >= len(args):
            return None
        return args[index + 1]

    def _write_llm_config(
        self, root: Path, key: str, base_url: str | None, model: str | None
    ) -> None:
        env_path = root / ".env"
        managed = {"MAG_LLM_API_KEY", "MAG_LLM_BASE_URL", "MAG_LLM_MODEL"}
        lines = []
        if env_path.exists():
            lines = [
                line
                for line in env_path.read_text(encoding="utf-8").splitlines()
                if line.split("=", 1)[0] not in managed
            ]
        lines.append(f"MAG_LLM_API_KEY={key}")
        if base_url:
            lines.append(f"MAG_LLM_BASE_URL={base_url}")
        if model:
            lines.append(f"MAG_LLM_MODEL={model}")
        env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def _rethink(self, root: Path) -> None:
        for relative in [".mag/chat", "work", "output"]:
            path = root / relative
            if path.exists():
                shutil.rmtree(path)
        for relative in [
            ".mag/chat/sessions",
            "work/discussion",
            "work/results",
            "work/paper",
            "output/draft",
            "output/final",
            "output/package",
        ]:
            (root / relative).mkdir(parents=True, exist_ok=True)
        (root / ".mag/chat/messages.jsonl").write_text("", encoding="utf-8")

    def _full_reset(self, root: Path) -> None:
        for child in root.iterdir():
            if child.name == ".git":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
