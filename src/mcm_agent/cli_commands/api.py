from __future__ import annotations

from pathlib import Path

from mcm_agent.cli_commands.base import CommandContext, CommandResult
from mcm_agent.core.api_console import PROVIDERS, check_provider, provider_status, set_provider
from mcm_agent.core.config_writer import import_env_file
from mcm_agent.core.llm_presets import configure_llm_interactive


class ApiCommand:
    name = "api"
    summary = "查看和配置 API。"

    def run(self, args: list[str], context: CommandContext) -> CommandResult:
        root = Path(context.workspace_root)
        status = self._status_text(root)
        if context.ask is None or "--status" in args:
            return CommandResult(status)
        printer = context.printer if callable(context.printer) else print
        printer(status)
        # One focused action per invocation (Claude-Code style), then return to the prompt.
        choice = (
            context.ask("配置: [1]LLM [2]其他provider [3]导入.env [4]测连通  [回车]返回: ") or ""
        ).strip()
        if choice == "1":
            return CommandResult(configure_llm_interactive(root, context.ask))
        if choice == "2":
            return CommandResult(self._configure_other(root, context.ask))
        if choice == "3":
            path = (context.ask(".env 文件路径: ") or "").strip()
            ok, msg = import_env_file(root, path) if path else (False, "未输入路径。")
            return CommandResult(msg)
        if choice == "4":
            return CommandResult(self._test_connectivity(root, context.ask, printer))
        return CommandResult("")

    def _configure_other(self, root: Path, ask) -> str:
        others = [p for p in PROVIDERS if p["key"] != "llm"]
        listing = "\n".join(f"  {i + 1}) {p['label']}" for i, p in enumerate(others))
        raw = (ask(f"选择 provider：\n{listing}\n编号: ") or "").strip()
        if not raw.isdigit() or not (1 <= int(raw) <= len(others)):
            return "无效编号。"
        provider = others[int(raw) - 1]
        key = (ask(f"{provider['label']} API key: ") or "").strip()
        if not key:
            return "未输入 key，已取消。"
        set_provider(root, provider["key"], {"api_key": key})
        return f"✓ 已保存 {provider['label']} 配置到 .env。"

    def _test_connectivity(self, root: Path, ask, printer) -> str:
        listing = "\n".join(f"  {i + 1}) {p['label']}" for i, p in enumerate(PROVIDERS))
        raw = (ask(f"测试哪个 provider？\n{listing}\n编号: ") or "").strip()
        if not raw.isdigit() or not (1 <= int(raw) <= len(PROVIDERS)):
            return "无效编号。"
        provider = PROVIDERS[int(raw) - 1]
        printer(f"正在测试 {provider['label']} ……")
        result = check_provider(root, provider["key"])
        return f"{provider['label']}: {result['status']} — {result.get('detail', '')}"

    def _status_text(self, root: Path) -> str:
        rows = {row["key"]: row for row in provider_status(root)}

        def mark(key: str) -> str:
            return "[ok]" if rows[key]["configured"] else "[--]"

        search_ok = [
            rows[k]["label"].split()[0]
            for k in ("tavily", "brave", "exa", "firecrawl")
            if rows[k]["configured"]
        ]
        return "\n".join(
            [
                f"LLM       {mark('llm')} {rows['llm']['detail'] or '未配置'}",
                f"Search    {'[ok] ' + ', '.join(search_ok) if search_ok else '[--] 未配置'}",
                f"可选      MinerU{mark('mineru')}  Embedding{mark('embedding')}  "
                f"Humanizer{mark('humanizer')}",
            ]
        )
