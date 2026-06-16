from __future__ import annotations

import shutil
import time
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from mcm_agent.config import Settings
from mcm_agent.utils.json_io import append_jsonl
from mcm_agent.providers.data_apis import (
    FredProvider,
    NASAPowerProvider,
    NOAAProvider,
    OECDProvider,
    OpenMeteoProvider,
    OverpassProvider,
    USCensusProvider,
    UNDataProvider,
    WorldBankProvider,
)
from mcm_agent.providers.humanizer import UShallPassHumanizerProvider
from mcm_agent.providers.llm import OpenAICompatibleLLMProvider
from mcm_agent.providers.mineru import RestMinerUProvider
from mcm_agent.providers.search import (
    BraveSearchProvider,
    ExaSearchProvider,
    FirecrawlProvider,
    TavilyProvider,
)


DEFAULT_SMOKE_PROVIDERS = [
    "llm",
    "tavily",
    "brave",
    "exa",
    "firecrawl",
    "humanizer",
    "mineru",
    "world_bank",
    "oecd",
    "undata",
    "fred",
    "us_census",
    "noaa",
    "nasa_power",
    "open_meteo",
    "overpass",
    "embedding",
]


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
        history_path: Path | None = None,
    ) -> None:
        self.settings = settings
        self.workspace_root = workspace_root
        self.mineru_file = mineru_file
        self.history_path = history_path

    def run(self, providers: list[str]) -> list[ProviderSmokeResult]:
        results = [self.check(provider) for provider in providers]
        if self.history_path is not None:
            self._append_history(results)
        return results

    def _append_history(self, results: list[ProviderSmokeResult]) -> None:
        counts = {"passed": 0, "skipped": 0, "failed": 0}
        for result in results:
            counts[result.status.value] = counts.get(result.status.value, 0) + 1
        append_jsonl(
            self.history_path,
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "counts": counts,
                "results": [result.model_dump(mode="json") for result in results],
            },
        )

    def check(self, provider: str) -> ProviderSmokeResult:
        checks = {
            "llm": self._check_llm,
            "tavily": self._check_tavily,
            "brave": self._check_brave,
            "exa": self._check_exa,
            "firecrawl": self._check_firecrawl,
            "humanizer": self._check_humanizer,
            "mineru": self._check_mineru,
            "world_bank": self._check_world_bank,
            "oecd": self._check_oecd,
            "undata": self._check_undata,
            "fred": self._check_fred,
            "us_census": self._check_us_census,
            "noaa": self._check_noaa,
            "nasa_power": self._check_nasa_power,
            "open_meteo": self._check_open_meteo,
            "overpass": self._check_overpass,
            "embedding": self._check_embedding,
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

    def _check_brave(self) -> ProviderSmokeResult:
        if not self.settings.brave_search_api_key:
            return self._skipped("brave", "BRAVE_SEARCH_API_KEY is not configured.")
        results = BraveSearchProvider(self.settings.brave_search_api_key).search(
            "official public population dataset",
            max_results=1,
        )
        if not results:
            raise RuntimeError("Brave returned no results")
        return self._passed("brave", f"{len(results)} result(s): {results[0].url}")

    def _check_exa(self) -> ProviderSmokeResult:
        if not self.settings.exa_api_key:
            return self._skipped("exa", "EXA_API_KEY is not configured.")
        results = ExaSearchProvider(self.settings.exa_api_key).search(
            "official public population dataset",
            max_results=1,
        )
        if not results:
            raise RuntimeError("Exa returned no results")
        return self._passed("exa", f"{len(results)} result(s): {results[0].url}")

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

    def _check_embedding(self) -> ProviderSmokeResult:
        if self.settings.embedding_provider != "voyage" or not self.settings.voyage_api_key:
            return self._skipped(
                "embedding", "Voyage embedding key is not configured (embedding provider)."
            )
        from mcm_agent.providers.embedding import VoyageEmbeddingProvider

        vectors = VoyageEmbeddingProvider(
            self.settings.voyage_api_key,
            model=self.settings.embedding_model,
            base_url=self.settings.embedding_base_url,
            timeout_seconds=self.settings.mcm_agent_http_timeout_seconds,
        ).embed(["provider connectivity test"])
        if not vectors or not vectors[0]:
            raise RuntimeError("Voyage returned no embedding")
        return self._passed("embedding", f"Voyage embedding dim={len(vectors[0])}.")

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

    def _check_world_bank(self) -> ProviderSmokeResult:
        source = WorldBankProvider(self.workspace_root / "smoke" / "official_data").fetch_indicator(
            "US",
            "SP.POP.TOTL",
        )
        return self._passed("world_bank", f"Fetched {source.source_id}.")

    def _check_oecd(self) -> ProviderSmokeResult:
        source = OECDProvider(
            self.workspace_root / "smoke" / "official_data",
            base_url=self.settings.oecd_base_url,
        ).fetch_dataset("DF_DP_LIVE/.USA.POP.TOT...A", params={"contentType": "csv"})
        return self._passed("oecd", f"Fetched {source.source_id}.")

    def _check_undata(self) -> ProviderSmokeResult:
        source = UNDataProvider(
            self.workspace_root / "smoke" / "official_data",
            base_url=self.settings.undata_base_url,
        ).fetch_dataset("WDI")
        return self._passed("undata", f"Fetched {source.source_id}.")

    def _check_fred(self) -> ProviderSmokeResult:
        if not self.settings.fred_api_key:
            return self._skipped("fred", "FRED_API_KEY is not configured.")
        source = FredProvider(
            self.workspace_root / "smoke" / "official_data",
            api_key=self.settings.fred_api_key,
        ).fetch_series("GDP")
        return self._passed("fred", f"Fetched {source.source_id}.")

    def _check_us_census(self) -> ProviderSmokeResult:
        source = USCensusProvider(
            self.workspace_root / "smoke" / "official_data",
            api_key=self.settings.us_census_api_key,
            base_url=self.settings.us_census_base_url,
        ).fetch_dataset("2022/pep/population", {"get": "NAME,POP", "for": "state:06"})
        return self._passed("us_census", f"Fetched {source.source_id}.")

    def _check_noaa(self) -> ProviderSmokeResult:
        if not self.settings.noaa_api_key:
            return self._skipped("noaa", "NOAA_API_KEY is not configured.")
        source = NOAAProvider(
            self.workspace_root / "smoke" / "official_data",
            api_key=self.settings.noaa_api_key,
            base_url=self.settings.noaa_base_url,
        ).fetch_data(
            {
                "datasetid": "GHCND",
                "datatypeid": "TMAX",
                "stationid": "GHCND:USW00094728",
                "startdate": "2024-01-01",
                "enddate": "2024-01-01",
                "limit": "1",
            }
        )
        return self._passed("noaa", f"Fetched {source.source_id}.")

    def _check_nasa_power(self) -> ProviderSmokeResult:
        source = NASAPowerProvider(
            self.workspace_root / "smoke" / "official_data",
            base_url=self.settings.nasa_power_base_url,
        ).fetch_point(
            {
                "latitude": "38.9",
                "longitude": "-77.0",
                "start": "20240101",
                "end": "20240101",
                "parameters": "T2M",
            }
        )
        return self._passed("nasa_power", f"Fetched {source.source_id}.")

    def _check_open_meteo(self) -> ProviderSmokeResult:
        source = OpenMeteoProvider(
            self.workspace_root / "smoke" / "official_data",
            base_url=self.settings.open_meteo_base_url,
        ).fetch_archive(
            {
                "latitude": "38.9",
                "longitude": "-77.0",
                "start_date": "2024-01-01",
                "end_date": "2024-01-01",
                "daily": "temperature_2m_max",
            }
        )
        return self._passed("open_meteo", f"Fetched {source.source_id}.")

    def _check_overpass(self) -> ProviderSmokeResult:
        source = OverpassProvider(
            self.workspace_root / "smoke" / "official_data",
            base_url=self.settings.overpass_base_url,
        ).fetch_query("[out:json][timeout:5];node(0,0,0.01,0.01);out count;")
        return self._passed("overpass", f"Fetched {source.source_id}.")

    def _passed(self, provider: str, detail: str) -> ProviderSmokeResult:
        return ProviderSmokeResult(provider=provider, status=SmokeStatus.PASSED, detail=detail)

    def _skipped(self, provider: str, detail: str) -> ProviderSmokeResult:
        return ProviderSmokeResult(provider=provider, status=SmokeStatus.SKIPPED, detail=detail)
