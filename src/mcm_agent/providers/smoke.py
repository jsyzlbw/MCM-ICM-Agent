from __future__ import annotations

import shutil
import time
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from mcm_agent.config import Settings
from mcm_agent.providers.humanizer import UShallPassHumanizerProvider
from mcm_agent.providers.llm import OpenAICompatibleLLMProvider
from mcm_agent.providers.mineru import RestMinerUProvider
from mcm_agent.providers.search import FirecrawlProvider, TavilyProvider


class SmokeStatus(StrEnum):
    PASSED = "passed"
    SKIPPED = "skipped"
    FAILED = "failed"


class ProviderSmokeResult(BaseModel):
    provider: str
    status: SmokeStatus
    detail: str
    latency_ms: int = 0


class ProviderSmokeTester:
    def __init__(
        self,
        settings: Settings,
        *,
        workspace_root: Path,
        mineru_file: Path | None = None,
    ) -> None:
        self.settings = settings
        self.workspace_root = workspace_root
        self.mineru_file = mineru_file

    def run(self, providers: list[str]) -> list[ProviderSmokeResult]:
        return [self.check(provider) for provider in providers]

    def check(self, provider: str) -> ProviderSmokeResult:
        checks = {
            "llm": self._check_llm,
            "tavily": self._check_tavily,
            "firecrawl": self._check_firecrawl,
            "humanizer": self._check_humanizer,
            "mineru": self._check_mineru,
        }
        if provider not in checks:
            return ProviderSmokeResult(
                provider=provider,
                status=SmokeStatus.FAILED,
                detail=f"Unknown smoke provider: {provider}",
            )
        start = time.monotonic()
        try:
            result = checks[provider]()
        except Exception as exc:
            result = ProviderSmokeResult(
                provider=provider,
                status=SmokeStatus.FAILED,
                detail=f"{exc.__class__.__name__}: {exc}",
            )
        result.latency_ms = int((time.monotonic() - start) * 1000)
        return result

    def _check_llm(self) -> ProviderSmokeResult:
        if not self.settings.openai_api_key:
            return self._skipped("llm", "OPENAI_API_KEY is not configured.")
        provider = OpenAICompatibleLLMProvider(
            api_key=self.settings.openai_api_key,
            model=self.settings.openai_model,
            base_url=self.settings.openai_base_url or "https://api.openai.com/v1",
            timeout_seconds=self.settings.mcm_agent_http_timeout_seconds,
        )
        result = provider.generate(
            "You are a provider smoke test.",
            "Reply with exactly OK.",
            temperature=0,
        )
        if not result.content.strip():
            raise RuntimeError("LLM returned empty content")
        return self._passed("llm", f"LLM responded with {len(result.content.strip())} characters.")

    def _check_tavily(self) -> ProviderSmokeResult:
        if not self.settings.tavily_api_key:
            return self._skipped("tavily", "TAVILY_API_KEY is not configured.")
        results = TavilyProvider(self.settings.tavily_api_key).search(
            "official public population dataset",
            max_results=1,
        )
        if not results:
            raise RuntimeError("Tavily returned no results")
        return self._passed("tavily", f"{len(results)} result(s): {results[0].url}")

    def _check_firecrawl(self) -> ProviderSmokeResult:
        if not self.settings.firecrawl_api_key:
            return self._skipped("firecrawl", "FIRECRAWL_API_KEY is not configured.")
        output_dir = self.workspace_root / "smoke" / "firecrawl"
        page = FirecrawlProvider(self.settings.firecrawl_api_key, output_dir=output_dir).extract(
            "https://example.com"
        )
        if not page.markdown.strip():
            raise RuntimeError("Firecrawl returned empty markdown")
        return self._passed("firecrawl", f"Extracted {len(page.markdown)} markdown characters.")

    def _check_humanizer(self) -> ProviderSmokeResult:
        if not self.settings.humanizer_api_key:
            return self._skipped("humanizer", "HUMANIZER_API_KEY is not configured.")
        provider = UShallPassHumanizerProvider(
            self.settings.humanizer_api_key,
            self.settings.humanizer_api_base_url,
            poll_interval_seconds=0.25,
            max_poll_attempts=20,
        )
        output = provider.humanize("This is a provider connectivity test.", language="en")
        if not output.strip():
            raise RuntimeError("Humanizer returned empty output")
        return self._passed("humanizer", f"Humanizer returned {len(output)} characters.")

    def _check_mineru(self) -> ProviderSmokeResult:
        mode = self.settings.mineru_mode
        if mode == "fake":
            return self._skipped("mineru", "MINERU_MODE=fake; no real MinerU smoke test needed.")
        if mode == "local":
            if shutil.which(self.settings.mineru_cli) is None:
                raise RuntimeError(f"MinerU CLI not found: {self.settings.mineru_cli}")
            if self.mineru_file is None:
                return self._skipped(
                    "mineru",
                    "MinerU CLI exists, but mineru_file was not provided for parse smoke.",
                )
            return self._parse_mineru_local_or_rest()
        if mode == "rest":
            if not self.settings.mineru_api_key:
                return self._skipped("mineru", "MINERU_API_KEY is not configured.")
            if self.mineru_file is None:
                return self._skipped("mineru", "MinerU REST smoke requires mineru_file.")
            return self._parse_mineru_local_or_rest()
        return self._skipped("mineru", f"Unsupported MINERU_MODE={mode!r}.")

    def _parse_mineru_local_or_rest(self) -> ProviderSmokeResult:
        if self.mineru_file is None:
            return self._skipped("mineru", "mineru_file was not provided.")
        if not self.mineru_file.exists():
            raise FileNotFoundError(self.mineru_file)
        if self.settings.mineru_mode == "rest":
            provider = RestMinerUProvider(
                self.settings.mineru_api_base_url,
                self.settings.mineru_api_key,
                poll_interval_seconds=1,
                poll_timeout_seconds=120,
            )
        else:
            from mcm_agent.providers.mineru import LocalMinerUProvider

            provider = LocalMinerUProvider(self.settings.mineru_cli)
        parsed = provider.parse_document(self.mineru_file, self.workspace_root / "smoke" / "mineru")
        markdown = Path(parsed.markdown_path)
        if not markdown.exists():
            raise RuntimeError("MinerU did not produce markdown output")
        return self._passed("mineru", f"Parsed markdown: {markdown}")

    def _passed(self, provider: str, detail: str) -> ProviderSmokeResult:
        return ProviderSmokeResult(provider=provider, status=SmokeStatus.PASSED, detail=detail)

    def _skipped(self, provider: str, detail: str) -> ProviderSmokeResult:
        return ProviderSmokeResult(provider=provider, status=SmokeStatus.SKIPPED, detail=detail)
