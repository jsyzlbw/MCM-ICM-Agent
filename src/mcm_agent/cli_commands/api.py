from __future__ import annotations

from pathlib import Path

from mcm_agent.cli_commands.base import CommandContext, CommandResult
from mcm_agent.config import load_settings


class ApiCommand:
    name = "api"
    summary = "查看和配置 API。"

    def run(self, args: list[str], context: CommandContext) -> CommandResult:
        root = Path(context.workspace_root)
        settings = load_settings(workspace_root=root)
        has_llm = bool(settings.openai_api_key) and settings.llm_provider != "fake"
        has_search = any(
            [
                settings.tavily_api_key,
                settings.brave_search_api_key,
                settings.exa_api_key,
                settings.firecrawl_api_key,
            ]
        )
        has_mineru = settings.mineru_mode == "local" or (
            settings.mineru_mode == "rest" and bool(settings.mineru_api_key)
        )
        has_embed = settings.embedding_provider == "voyage" and bool(settings.voyage_api_key)
        has_humanizer = bool(settings.humanizer_api_key)

        def row(ok: bool, name: str, detail: str) -> str:
            return f"  [{'ok' if ok else 'missing'}] {name:<11}{detail}"

        lines = [
            "API status",
            "",
            "Required:",
            row(has_llm, "LLM", settings.openai_model if has_llm else "required for reasoning"),
            "",
            "Recommended:",
            row(has_search, "Search", "configured" if has_search else "useful for public data"),
            "",
            "Optional:",
            row(has_mineru, "MinerU", "PDF parsing"),
            row(has_embed, "Embedding", "RAG vector search"),
            row(has_humanizer, "Humanizer", "style polish"),
            "",
            "Configure with: /init --llm-key <key> --llm-base-url <url> --llm-model <model>",
        ]
        return CommandResult("\n".join(lines))
