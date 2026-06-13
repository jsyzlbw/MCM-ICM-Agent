from __future__ import annotations

from pathlib import Path

from mcm_agent.config import Settings
from mcm_agent.providers.base import ProviderBundle
from mcm_agent.providers.humanizer import FakeHumanizerProvider, UShallPassHumanizerProvider
from mcm_agent.providers.latex import LatexProvider
from mcm_agent.providers.llm import FakeLLMProvider, OpenAICompatibleLLMProvider
from mcm_agent.providers.mineru import FakeMinerUProvider, LocalMinerUProvider, RestMinerUProvider
from mcm_agent.providers.search import FirecrawlProvider, TavilyProvider


class NullSearchProvider:
    def search(self, query: str, *, max_results: int = 5) -> list[object]:
        return []


class NullExtractProvider:
    def extract(self, url: str) -> object:
        return type(
            "ExtractedPage",
            (),
            {"url": url, "title": url, "markdown": "", "metadata": {}},
        )()


def build_provider_bundle(settings: Settings, *, workspace_root: Path) -> ProviderBundle:
    llm = (
        OpenAICompatibleLLMProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url or "https://api.openai.com/v1",
            timeout_seconds=settings.mcm_agent_http_timeout_seconds,
        )
        if settings.openai_api_key
        else FakeLLMProvider({"default": ""})
    )

    if settings.mineru_mode == "local":
        mineru = LocalMinerUProvider(settings.mineru_cli)
    elif settings.mineru_mode == "rest":
        mineru = RestMinerUProvider(settings.mineru_api_base_url, settings.mineru_api_key)
    else:
        mineru = FakeMinerUProvider()

    search = TavilyProvider(settings.tavily_api_key) if settings.tavily_api_key else NullSearchProvider()
    extractor = (
        FirecrawlProvider(settings.firecrawl_api_key, workspace_root / "data" / "external")
        if settings.firecrawl_api_key
        else NullExtractProvider()
    )

    humanizer = (
        UShallPassHumanizerProvider(
            settings.humanizer_api_key,
            settings.humanizer_api_base_url,
        )
        if settings.humanizer_api_key
        else FakeHumanizerProvider({})
    )

    return ProviderBundle(
        llm=llm,
        mineru=mineru,
        search=search,
        extractor=extractor,
        humanizer=humanizer,
        latex=LatexProvider(),
    )
