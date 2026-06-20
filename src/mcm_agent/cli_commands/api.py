from __future__ import annotations

from pathlib import Path

from mcm_agent.cli_commands.base import CommandContext, CommandResult
from mcm_agent.core.api_console import (
    PROVIDERS,
    check_provider,
    provider_status,
    set_provider,
)
from mcm_agent.core.config_writer import import_env_file

_GROUPS = [
    ("Required", {"llm"}),
    ("Recommended", {"tavily", "brave", "exa", "firecrawl"}),
    ("Optional", {"mineru", "embedding", "humanizer"}),
]


class ApiCommand:
    name = "api"
    summary = "查看和配置 API。"

    def run(self, args: list[str], context: CommandContext) -> CommandResult:
        root = Path(context.workspace_root)
        if context.ask is None or "--status" in args:
            return CommandResult(self._status_text(root))
        printer = context.printer if callable(context.printer) else print
        try:
            self._interactive(root, context.ask, printer)
        except Exception as exc:  # never let the prompt crash the shell
            return CommandResult(f"/api 交互出错（{type(exc).__name__}）。\n\n" + self._status_text(root))
        return CommandResult(self._status_text(root))

    def _interactive(self, root: Path, ask, printer) -> None:
        while True:
            printer(self._status_text(root))
            choice = (
                ask(
                    "\n操作：\n"
                    "  1) 导入 .env 文件（复制到本 workspace）\n"
                    "  2) 手动配置 LLM\n"
                    "  3) 配置其他 provider\n"
                    "  4) 测试连通\n"
                    "  5) 退出\n"
                    "请选择 [1-5]: "
                )
                or ""
            ).strip()
            if choice in ("5", "", "q", "exit"):
                return
            if choice == "1":
                path = (ask(".env 文件路径: ") or "").strip()
                ok, msg = import_env_file(root, path) if path else (False, "未输入路径。")
                printer(msg)
            elif choice == "2":
                self._configure_llm(root, ask, printer)
            elif choice == "3":
                self._configure_other(root, ask, printer)
            elif choice == "4":
                self._test_connectivity(root, ask, printer)
            else:
                printer("无效选择。")

    def _configure_llm(self, root: Path, ask, printer) -> None:
        key = (ask("LLM API key: ") or "").strip()
        if not key:
            printer("未输入 key，已取消。")
            return
        base_url = (ask("Base URL（回车用默认 https://api.openai.com/v1）: ") or "").strip()
        model = (ask("Model（回车用默认 gpt-4.1）: ") or "").strip()
        answers = {"api_key": key}
        if base_url:
            answers["base_url"] = base_url
        if model:
            answers["model"] = model
        set_provider(root, "llm", answers)
        printer("已保存 LLM 配置到 .env。")

    def _configure_other(self, root: Path, ask, printer) -> None:
        others = [p for p in PROVIDERS if p["key"] != "llm"]
        listing = "\n".join(f"  {i + 1}) {p['label']}" for i, p in enumerate(others))
        raw = (ask(f"选择 provider：\n{listing}\n编号: ") or "").strip()
        if not raw.isdigit() or not (1 <= int(raw) <= len(others)):
            printer("无效编号。")
            return
        provider = others[int(raw) - 1]
        key = (ask(f"{provider['label']} API key: ") or "").strip()
        if not key:
            printer("未输入 key，已取消。")
            return
        set_provider(root, provider["key"], {"api_key": key})
        printer(f"已保存 {provider['label']} 配置到 .env。")

    def _test_connectivity(self, root: Path, ask, printer) -> None:
        listing = "\n".join(f"  {i + 1}) {p['label']}" for i, p in enumerate(PROVIDERS))
        raw = (ask(f"测试哪个 provider 的连通？\n{listing}\n编号: ") or "").strip()
        if not raw.isdigit() or not (1 <= int(raw) <= len(PROVIDERS)):
            printer("无效编号。")
            return
        provider = PROVIDERS[int(raw) - 1]
        printer(f"正在测试 {provider['label']} ……")
        result = check_provider(root, provider["key"])
        printer(f"结果：{result['status']} — {result.get('detail', '')}")

    def _status_text(self, root: Path) -> str:
        rows = {row["key"]: row for row in provider_status(root)}
        lines = ["API status", ""]
        for title, keys in _GROUPS:
            lines.append(f"{title}:")
            for provider in PROVIDERS:
                if provider["key"] not in keys:
                    continue
                row = rows[provider["key"]]
                mark = "ok" if row["configured"] else "missing"
                detail = row["detail"] or ("configured" if row["configured"] else "")
                lines.append(f"  [{mark}] {row['label']:<18}{detail}")
            lines.append("")
        lines.append("在交互式终端运行 /api 可导入 .env、手动配置、测试连通；脚本中用 /init 配置。")
        return "\n".join(lines)
