from __future__ import annotations

from pathlib import Path
import shutil

from mcm_agent.cli_commands.base import CommandContext, CommandResult
from mcm_agent.config import load_settings
from mcm_agent.core.config_writer import import_env_file
from mcm_agent.core.llm_presets import configure_llm_interactive
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
        # Mode 1 (scriptable): copy an existing .env into the workspace.
        from_env = self._extract_option(args, "--from-env")
        if from_env:
            ok, msg = import_env_file(root, from_env)
            return self._finalize(root, state, msg) if ok else CommandResult(msg)

        # Mode 2 (scriptable): manual flags.
        llm_key = self._extract_option(args, "--llm-key")
        if llm_key:
            self._write_llm_config(
                root,
                llm_key,
                self._extract_option(args, "--llm-base-url"),
                self._extract_option(args, "--llm-model"),
            )
            return self._finalize(root, state, "Init complete. LLM API 已配置（其余可选 API 已跳过）。")

        # Interactive (Claude-Code style) when a real terminal is attached.
        if context.ask is not None:
            return self._interactive_config(root, state, context.ask)

        return CommandResult(
            "如何配置 LLM API：\n"
            "  • 导入已有 .env： /init --from-env <path>（复制到本 workspace）\n"
            "  • 手动配置：     /init --llm-key <key> [--llm-base-url <url>] [--llm-model <model>]\n"
            "  • 在交互式终端直接运行 /init 可逐步引导配置。"
        )

    def _interactive_config(self, root: Path, state: object, ask) -> CommandResult:
        choice = (
            ask(
                "如何配置 LLM API？\n"
                "  1) 导入已有 .env 文件（输入路径，复制到本 workspace）\n"
                "  2) 手动输入 API key\n"
                "  3) 跳过\n"
                "请选择 [1/2/3]: "
            )
            or ""
        ).strip()
        if choice == "1":
            path = (ask(".env 文件路径: ") or "").strip()
            if not path:
                return CommandResult("未输入路径，已取消。")
            ok, msg = import_env_file(root, path)
            return self._finalize(root, state, msg) if ok else CommandResult(msg)
        if choice == "2":
            msg = configure_llm_interactive(root, ask)
            if "已配置" in msg:
                return self._finalize(root, state, msg)
            return CommandResult(msg)
        return CommandResult("已跳过 LLM 配置。稍后可运行 /api 或 /init 配置。")

    def _finalize(self, root: Path, state: object, message: str) -> CommandResult:
        configured = bool(load_settings(workspace_root=root).openai_api_key)
        state.init.llm_configured = configured
        state.init.completed = True
        state.phase = "init_complete"
        save_workspace_state(root, state)
        WorkspaceSafety(root).checkpoint("mag: complete init")
        suffix = "" if configured else "\n（提醒：未检测到 LLM API key，/start 前请先配置。）"
        return CommandResult(message + suffix)

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
        # Upsert only the fields provided so an already-configured base_url/model
        # (e.g. from an /api preset) is PRESERVED. Wiping it would silently send a
        # non-OpenAI key (DeepSeek/SiliconFlow) to the default OpenAI endpoint -> 401.
        from mcm_agent.core.config_writer import set_env_var

        set_env_var(root, "MAG_LLM_API_KEY", key)
        if base_url:
            set_env_var(root, "MAG_LLM_BASE_URL", base_url)
        if model:
            set_env_var(root, "MAG_LLM_MODEL", model)

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
