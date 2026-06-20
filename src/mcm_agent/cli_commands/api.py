from __future__ import annotations

import sys
from pathlib import Path

from mcm_agent.cli_commands.base import CommandContext, CommandResult
from mcm_agent.core.api_console import (
    PROVIDERS,
    check_provider,
    provider_fields,
    provider_status,
    set_provider,
)

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
        interactive = "--no-tui" not in args and self._has_tty()
        if not interactive:
            return CommandResult(self._status_text(root))
        try:
            self._interactive(root)
        except Exception as exc:  # never let the TUI crash the shell
            return CommandResult(f"/api 交互模式不可用（{type(exc).__name__}）。\n\n" + self._status_text(root))
        return CommandResult(self._status_text(root))

    def _has_tty(self) -> bool:
        try:
            return sys.stdin.isatty() and sys.stdout.isatty()
        except Exception:
            return False

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
        lines.append("在终端运行 /api 可上下选择、输入、测试连通；脚本中用 /init 配置。")
        return "\n".join(lines)

    def _interactive(self, root: Path) -> None:
        import questionary

        while True:
            rows = provider_status(root)
            labels = [
                f"{row['label']}  [{'ok' if row['configured'] else 'missing'}]"
                + (f"  {row['detail']}" if row["detail"] else "")
                for row in rows
            ]
            labels.append("退出")
            choice = questionary.select(
                "选择 API（↑/↓ 选择，Enter 确认）", choices=labels
            ).ask()
            if choice is None or choice == "退出":
                return
            row = rows[labels.index(choice)]
            self._provider_menu(root, row)

    def _provider_menu(self, root: Path, row: dict) -> None:
        import questionary

        action = questionary.select(
            f"{row['label']}", choices=["测试连通", "输入/修改", "查看", "返回"]
        ).ask()
        if action == "测试连通":
            result = check_provider(root, row["key"])
            questionary.print(f"连通检查：{result['status']} — {result.get('detail', '')}")
        elif action == "输入/修改":
            answers: dict[str, str] = {}
            for field_name, _env, is_secret in provider_fields(row["key"]):
                prompt = f"{row['label']} {field_name}"
                value = (
                    questionary.password(prompt).ask()
                    if is_secret
                    else questionary.text(prompt).ask()
                )
                if value:
                    answers[field_name] = value
            set_provider(root, row["key"], answers)
            questionary.print(f"已保存 {row['label']} 配置到 .env。")
        elif action == "查看":
            status = "configured" if row["configured"] else "missing"
            questionary.print(f"{row['label']}: {status} {row['detail']}")
