from __future__ import annotations

from pathlib import Path

from mcm_agent.config import Settings
from mcm_agent.providers.base import ProviderBundle
from mcm_agent.providers.data_apis import OfficialDataApiRepairProvider
from mcm_agent.providers.embedding import (
    FakeEmbeddingProvider,
    FakeRerankProvider,
    VoyageEmbeddingProvider,
    VoyageRerankProvider,
)
from mcm_agent.providers.humanizer import FakeHumanizerProvider, UShallPassHumanizerProvider
from mcm_agent.providers.latex import LatexProvider
from mcm_agent.providers.llm import (
    AnthropicCompatibleLLMProvider,
    FakeLLMProvider,
    OpenAICompatibleLLMProvider,
)
from mcm_agent.providers.mineru import FakeMinerUProvider, LocalMinerUProvider, RestMinerUProvider
from mcm_agent.providers.search import (
    BraveSearchProvider,
    ExaSearchProvider,
    FallbackSearchProvider,
    FirecrawlProvider,
    TavilyProvider,
)


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


def build_llm_provider(settings: Settings) -> object:
    """Build the LLM provider, choosing the wire protocol from settings.llm_protocol
    ('openai' -> /chat/completions, 'anthropic' -> /v1/messages)."""
    if not settings.openai_api_key or settings.llm_provider == "fake":
        return FakeLLMProvider({"default": ""})
    if settings.llm_protocol == "anthropic":
        return AnthropicCompatibleLLMProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url or "https://api.anthropic.com",
            timeout_seconds=settings.mcm_agent_http_timeout_seconds,
            max_retries=settings.mcm_agent_max_retries,
        )
    return OpenAICompatibleLLMProvider(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        base_url=settings.openai_base_url or "https://api.openai.com/v1",
        timeout_seconds=settings.mcm_agent_http_timeout_seconds,
        max_retries=settings.mcm_agent_max_retries,
    )


def build_provider_bundle(settings: Settings, *, workspace_root: Path) -> ProviderBundle:
    # Offline/demo mode: a fully self-contained bundle (fake LLM + demo
    # search/extract/latex) that needs no network or TeX engine. Used by the CLI
    # smoke and offline tests via `[llm] provider = "fake"` / MAG_LLM_PROVIDER=fake.
    if settings.llm_provider == "fake":
        from mcm_agent.workflows.mvp import _default_demo_providers

        return _default_demo_providers()

    llm = build_llm_provider(settings)

    if settings.mineru_mode == "local":
        mineru = LocalMinerUProvider(settings.mineru_cli)
    elif settings.mineru_mode == "rest":
        mineru = RestMinerUProvider(settings.mineru_api_base_url, settings.mineru_api_key)
    else:
        mineru = FakeMinerUProvider()

    search_providers = []
    if settings.tavily_api_key:
        search_providers.append(TavilyProvider(settings.tavily_api_key))
    if settings.brave_search_api_key:
        search_providers.append(BraveSearchProvider(settings.brave_search_api_key))
    if settings.exa_api_key:
        search_providers.append(ExaSearchProvider(settings.exa_api_key))
    if len(search_providers) > 1:
        search = FallbackSearchProvider(search_providers)
    elif search_providers:
        search = search_providers[0]
    else:
        search = NullSearchProvider()
    extractor = (
        FirecrawlProvider(settings.firecrawl_api_key, workspace_root / "data" / "external")
        if settings.firecrawl_api_key
        else NullExtractProvider()
    )
    official_data = OfficialDataApiRepairProvider(
        fred_api_key=settings.fred_api_key,
        open_meteo_base_url=settings.open_meteo_base_url,
        oecd_base_url=settings.oecd_base_url,
        undata_base_url=settings.undata_base_url,
        us_census_api_key=settings.us_census_api_key,
        us_census_base_url=settings.us_census_base_url,
        noaa_api_key=settings.noaa_api_key,
        noaa_base_url=settings.noaa_base_url,
        nasa_power_base_url=settings.nasa_power_base_url,
        overpass_base_url=settings.overpass_base_url,
    )

    humanizer = (
        UShallPassHumanizerProvider(
            settings.humanizer_api_key,
            settings.humanizer_api_base_url,
        )
        if settings.humanizer_api_key
        else FakeHumanizerProvider({})
    )

    if settings.embedding_provider == "voyage" and settings.voyage_api_key:
        embedding = VoyageEmbeddingProvider(
            settings.voyage_api_key,
            model=settings.embedding_model,
            base_url=settings.embedding_base_url,
            timeout_seconds=settings.mcm_agent_http_timeout_seconds,
        )
        reranker = VoyageRerankProvider(
            settings.voyage_api_key,
            model=settings.rerank_model,
            base_url=settings.embedding_base_url,
            timeout_seconds=settings.mcm_agent_http_timeout_seconds,
        )
    else:
        embedding = FakeEmbeddingProvider()
        reranker = FakeRerankProvider()

    return ProviderBundle(
        llm=llm,
        mineru=mineru,
        search=search,
        extractor=extractor,
        official_data=official_data,
        humanizer=humanizer,
        latex=LatexProvider(),
        embedding=embedding,
        reranker=reranker,
    )
