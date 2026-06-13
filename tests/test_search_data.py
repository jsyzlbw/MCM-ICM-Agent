from pathlib import Path

import respx
from httpx import Response

from mcm_agent.agents.search_data import SearchDataAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.academic import OpenAlexProvider
from mcm_agent.providers.data_apis import WorldBankProvider
from mcm_agent.providers.search import (
    BraveSearchProvider,
    ExaSearchProvider,
    FallbackSearchProvider,
    FirecrawlProvider,
    SearchResult,
    TavilyProvider,
)
from mcm_agent.utils.json_io import read_json


@respx.mock
def test_tavily_provider_maps_results() -> None:
    respx.post("https://api.tavily.com/search").mock(
        return_value=Response(
            200,
            json={
                "results": [
                    {
                        "title": "Official data",
                        "url": "https://example.org/data",
                        "content": "Data snippet",
                        "score": 0.9,
                    }
                ]
            },
        )
    )

    results = TavilyProvider("key").search("population data")

    assert results == [
        SearchResult(
            title="Official data",
            url="https://example.org/data",
            snippet="Data snippet",
            score=0.9,
        )
    ]


@respx.mock
def test_brave_search_provider_maps_web_results() -> None:
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "title": "Brave official data",
                            "url": "https://example.gov/data",
                            "description": "Government dataset.",
                        }
                    ]
                }
            },
        )
    )

    results = BraveSearchProvider("key").search("official data", max_results=3)

    request = respx.calls.last.request
    assert request.headers["X-Subscription-Token"] == "key"
    assert request.url.params["q"] == "official data"
    assert request.url.params["count"] == "3"
    assert results == [
        SearchResult(
            title="Brave official data",
            url="https://example.gov/data",
            snippet="Government dataset.",
            score=None,
        )
    ]


@respx.mock
def test_exa_search_provider_maps_results() -> None:
    respx.post("https://api.exa.ai/search").mock(
        return_value=Response(
            200,
            json={
                "results": [
                    {
                        "title": "Exa method paper",
                        "url": "https://arxiv.org/abs/1234.5678",
                        "text": "A useful modeling method.",
                        "score": 0.8,
                    }
                ]
            },
        )
    )

    results = ExaSearchProvider("key").search("modeling method", max_results=2)

    request = respx.calls.last.request
    assert request.headers["x-api-key"] == "key"
    assert b'"numResults":2' in request.content
    assert results == [
        SearchResult(
            title="Exa method paper",
            url="https://arxiv.org/abs/1234.5678",
            snippet="A useful modeling method.",
            score=0.8,
        )
    ]


def test_fallback_search_provider_uses_next_provider_after_failure() -> None:
    class BrokenSearch:
        def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
            raise RuntimeError("upstream failed")

    class BackupSearch:
        def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
            return [SearchResult(title="Backup", url="https://example.org", snippet="ok")]

    results = FallbackSearchProvider([BrokenSearch(), BackupSearch()]).search("data")

    assert results[0].title == "Backup"


@respx.mock
def test_firecrawl_provider_extracts_markdown(tmp_path: Path) -> None:
    respx.post("https://api.firecrawl.dev/v1/scrape").mock(
        return_value=Response(
            200,
            json={"data": {"markdown": "# Extracted", "metadata": {"title": "Page"}}},
        )
    )

    page = FirecrawlProvider("key", output_dir=tmp_path).extract("https://example.org/page")

    assert page.markdown == "# Extracted"
    assert (tmp_path / "source_001.md").exists()


@respx.mock
def test_worldbank_provider_saves_raw_json(tmp_path: Path) -> None:
    respx.get("https://api.worldbank.org/v2/country/US/indicator/SP.POP.TOTL").mock(
        return_value=Response(200, json=[{"page": 1}, [{"date": "2023", "value": 1}]])
    )

    source = WorldBankProvider(tmp_path).fetch_indicator("US", "SP.POP.TOTL")

    assert source.source_rank == "official"
    assert (tmp_path / "raw" / "worldbank_US_SP.POP.TOTL.json").exists()


@respx.mock
def test_openalex_provider_maps_academic_sources() -> None:
    respx.get("https://api.openalex.org/works").mock(
        return_value=Response(
            200,
            json={
                "results": [
                    {
                        "id": "https://openalex.org/W1",
                        "display_name": "A useful method paper",
                        "doi": "https://doi.org/10.1/test",
                    }
                ]
            },
        )
    )

    sources = OpenAlexProvider().search_works("optimization", max_results=1)

    assert sources[0].source_rank == "academic"
    assert sources[0].title == "A useful method paper"


def test_search_data_agent_logs_and_registers_sources(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "experiment_plan.md").write_text(
        "# Experiment Plan\n\n## Required Datasets\n- population data\n",
        encoding="utf-8",
    )

    class FakeSearch:
        def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
            return [
                SearchResult(
                    title="Official statistics",
                    url="https://data.gov/example",
                    snippet="official source",
                    score=0.99,
                ),
                SearchResult(
                    title="SEO blog",
                    url="https://blog.example/post",
                    snippet="blog source",
                    score=0.3,
                ),
            ]

    class FakeExtractor:
        def extract(self, url: str):
            return type(
                "Extracted",
                (),
                {"url": url, "title": "Extracted page", "markdown": "# Page", "metadata": {}},
            )()

    SearchDataAgent(FakeSearch(), FakeExtractor()).run(workspace.root)

    sources = read_json(workspace.root / "data" / "source_registry.json", [])
    retrieval_log = (workspace.root / "data" / "retrieval_log.jsonl").read_text(
        encoding="utf-8"
    )
    assert sources[0]["source_rank"] == "official"
    assert sources[1]["source_rank"] == "background_only"
    assert "population data" in retrieval_log
    citations = read_json(workspace.root / "data" / "citation_candidates.json", [])
    lineage = read_json(workspace.root / "data" / "data_lineage.json", [])
    assert citations[0]["source_id"] == "web_001"
    assert citations[0]["url"] == "https://data.gov/example"
    assert citations[1]["source_id"] == "web_002"
    assert lineage[0]["source_id"] == "web_001"
    assert lineage[0]["source_url"] == "https://data.gov/example"
