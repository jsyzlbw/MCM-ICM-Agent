from __future__ import annotations

from pathlib import Path

from mcm_agent.cli_commands.base import CommandContext, CommandResult


class ApiCommand:
    name = "api"
    summary = "查看和配置 API。"

    def run(self, args: list[str], context: CommandContext) -> CommandResult:
        root = Path(context.workspace_root)
        env_text = (root / ".env").read_text(encoding="utf-8") if (root / ".env").exists() else ""
        has_llm = "MAG_LLM_API_KEY=" in env_text and "MAG_LLM_API_KEY=\n" not in env_text
        lines = [
            "API status",
            "",
            "Required:",
            f"  [{'ok' if has_llm else 'missing'}] LLM          required for reasoning",
            "",
            "Recommended:",
            "  [missing] Search       useful for public data",
            "  [missing] arXiv        useful for academic methods",
            "",
            "Optional:",
            "  [disabled] GitHub      local checkpoint only",
            "  [missing] NOAA         not needed yet",
            "  [missing] FRED         not needed yet",
        ]
        return CommandResult("\n".join(lines))
