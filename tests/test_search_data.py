from pathlib import Path

import respx
from httpx import Response

from mcm_agent.agents.search_data import SearchDataAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.academic import OpenAlexProvider
from mcm_agent.providers.data_apis import (
    FredProvider,
    NASAPowerProvider,
    NOAAProvider,
    OECDProvider,
    OfficialDataApiRepairProvider,
    OpenMeteoProvider,
    OverpassProvider,
    UNDataProvider,
    USCensusProvider,
    WorldBankProvider,
)
from mcm_agent.providers.search import (
    BraveSearchProvider,
    ExaSearchProvider,
    FallbackSearchProvider,
    FirecrawlProvider,
    SearchResult,
    TavilyProvider,
)
from mcm_agent.utils.json_io import read_json
from mcm_agent.utils.json_io import write_json


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
def test_oecd_provider_saves_raw_json(tmp_path: Path) -> None:
    respx.get("https://sdmx.example/DF_POP").mock(
        return_value=Response(200, json={"data": {"sets": []}})
    )

    source = OECDProvider(tmp_path, base_url="https://sdmx.example").fetch_dataset(
        "DF_POP",
        {"REF_AREA": "USA"},
    )

    assert source.provider == "oecd_api"
    assert source.source_rank == "official"
    assert (tmp_path / "raw" / "oecd_DF_POP.json").exists()


@respx.mock
def test_undata_provider_saves_raw_json(tmp_path: Path) -> None:
    respx.get("https://undata.example").mock(return_value=Response(200, text="value\n1\n"))

    source = UNDataProvider(tmp_path, base_url="https://undata.example").fetch_dataset("POP")

    assert source.provider == "undata_api"
    assert source.source_rank == "official"
    assert (tmp_path / "raw" / "undata_POP.json").exists()


@respx.mock
def test_fred_provider_saves_raw_json(tmp_path: Path) -> None:
    respx.get("https://api.stlouisfed.org/fred/series/observations").mock(
        return_value=Response(200, json={"observations": [{"date": "2024-01-01", "value": "1"}]})
    )

    source = FredProvider(tmp_path, api_key="key").fetch_series("GDP")

    assert source.provider == "fred_api"
    assert source.source_rank == "official"
    assert (tmp_path / "raw" / "fred_GDP.json").exists()


@respx.mock
def test_us_census_provider_saves_raw_json(tmp_path: Path) -> None:
    respx.get("https://census.example/2022/acs/acs5").mock(
        return_value=Response(200, json=[["NAME", "B01003_001E"], ["Alabama", "1"]])
    )

    source = USCensusProvider(
        tmp_path,
        api_key="key",
        base_url="https://census.example",
    ).fetch_dataset(
        "2022/acs/acs5",
        {"get": "NAME,B01003_001E", "for": "state:*"},
    )

    assert source.provider == "us_census_api"
    assert source.source_rank == "official"
    assert (tmp_path / "raw" / "us_census_2022_acs_acs5.json").exists()


@respx.mock
def test_noaa_provider_saves_raw_json(tmp_path: Path) -> None:
    respx.get("https://noaa.example/data").mock(
        return_value=Response(200, json={"results": [{"id": "GHCND"}]})
    )

    source = NOAAProvider(
        tmp_path,
        api_key="key",
        base_url="https://noaa.example",
    ).fetch_data({"datasetid": "GHCND"})

    assert source.provider == "noaa_api"
    assert source.source_rank == "official"
    assert (tmp_path / "raw" / "noaa_GHCND.json").exists()


@respx.mock
def test_nasa_power_provider_saves_raw_json(tmp_path: Path) -> None:
    respx.get("https://nasa.example").mock(return_value=Response(200, json={"properties": {}}))

    source = NASAPowerProvider(tmp_path, base_url="https://nasa.example").fetch_point(
        {"latitude": "39", "longitude": "-77", "parameters": "PRECTOTCORR"}
    )

    assert source.provider == "nasa_power_api"
    assert source.source_rank == "official"
    assert (tmp_path / "raw" / "nasa_power_PRECTOTCORR.json").exists()


@respx.mock
def test_open_meteo_provider_saves_raw_json(tmp_path: Path) -> None:
    respx.get("https://weather.example/archive").mock(
        return_value=Response(200, json={"daily": {"temperature_2m_max": [1]}})
    )

    source = OpenMeteoProvider(
        tmp_path,
        base_url="https://weather.example/archive",
    ).fetch_archive({"latitude": "39", "longitude": "-77", "daily": "temperature_2m_max"})

    assert source.provider == "open_meteo_api"
    assert source.source_rank == "official"
    assert (tmp_path / "raw" / "open_meteo_temperature_2m_max.json").exists()


@respx.mock
def test_overpass_provider_saves_raw_json(tmp_path: Path) -> None:
    respx.post("https://overpass.example").mock(
        return_value=Response(200, json={"elements": [{"type": "node"}]})
    )

    source = OverpassProvider(tmp_path, base_url="https://overpass.example").fetch_query(
        "[out:json];node(0,0,1,1);out;"
    )

    assert source.provider == "overpass_api"
    assert source.source_rank == "official"
    assert (tmp_path / "raw" / "overpass_query.json").exists()


@respx.mock
def test_official_data_api_repair_provider_fetches_population_from_worldbank(
    tmp_path: Path,
) -> None:
    respx.get("https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL").mock(
        return_value=Response(200, json=[{"page": 1}, [{"date": "2023", "value": 1}]])
    )

    records = OfficialDataApiRepairProvider().repair(
        tmp_path,
        {
            "need_id": "need_001",
            "target_dataset": "public population data",
            "query": "public population data public dataset official",
        },
    )

    assert records[0]["source_id"] == "worldbank_all_SP.POP.TOTL"
    assert records[0]["provider"] == "world_bank_api"
    assert records[0]["local_path"] == "data/raw/worldbank_all_SP.POP.TOTL.json"


@respx.mock
def test_official_data_api_repair_provider_routes_multiple_data_needs(
    tmp_path: Path,
) -> None:
    respx.get("https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL").mock(
        return_value=Response(200, json=[{"page": 1}, [{"date": "2023", "value": 1}]])
    )
    respx.get("https://api.stlouisfed.org/fred/series/observations").mock(
        return_value=Response(200, json={"observations": [{"date": "2024-01-01", "value": "1"}]})
    )
    respx.get("https://weather.example/archive").mock(
        return_value=Response(200, json={"daily": {"precipitation_sum": [1]}})
    )
    respx.get("https://census.example/2022/acs/acs5").mock(
        return_value=Response(200, json=[["NAME", "B01003_001E"], ["Alabama", "1"]])
    )
    respx.post("https://overpass.example").mock(
        return_value=Response(200, json={"elements": [{"type": "node"}]})
    )
    provider = OfficialDataApiRepairProvider(
        fred_api_key="fred-key",
        open_meteo_base_url="https://weather.example/archive",
        us_census_api_key="census-key",
        us_census_base_url="https://census.example",
        overpass_base_url="https://overpass.example",
    )

    population = provider.repair(tmp_path, {"target_dataset": "public population data"})
    economic = provider.repair(tmp_path, {"target_dataset": "GDP economic indicators"})
    weather = provider.repair(tmp_path, {"target_dataset": "weather climate rainfall data"})
    census = provider.repair(tmp_path, {"target_dataset": "US census population by state"})
    roads = provider.repair(tmp_path, {"target_dataset": "road network nodes edges"})

    assert population[0]["provider"] == "world_bank_api"
    assert economic[0]["provider"] == "fred_api"
    assert weather[0]["provider"] == "open_meteo_api"
    assert census[0]["provider"] == "us_census_api"
    assert roads[0]["provider"] == "overpass_api"


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


def test_search_data_agent_allows_attachment_only_workflow_without_search_results(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "experiment_plan.md").write_text(
        "# Experiment Plan\n\n## Required Datasets\n- cleaned attachment tables\n",
        encoding="utf-8",
    )
    attachment = workspace.root / "input" / "attachments" / "data.csv"
    attachment.parent.mkdir(parents=True, exist_ok=True)
    attachment.write_text("x,y\n1,2\n", encoding="utf-8")

    class EmptySearch:
        def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
            return []

    class UnusedExtractor:
        def extract(self, url: str):
            raise AssertionError("extractor should not be called")

    SearchDataAgent(EmptySearch(), UnusedExtractor()).run(workspace.root)

    gate = read_json(workspace.root / "review" / "source_gate.json", {})
    assert gate["status"] == "pass"


def test_search_data_agent_builds_route_aware_search_plan(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "experiment_plan.md").write_text(
        "# Experiment Plan\n\n## Required Datasets\n- cleaned attachment tables\n",
        encoding="utf-8",
    )
    (workspace.root / "reports" / "model_decision.md").write_text(
        "\n".join(
            [
                "# Model Decision",
                "",
                "## Selected Route",
                "multi_criteria_evaluation + constrained_optimization. Weighted score: 8.60.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    class RecordingSearch:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
            self.queries.append(query)
            return [
                SearchResult(
                    title="Official statistics",
                    url="https://data.gov/example",
                    snippet="official source",
                    score=0.99,
                )
            ]

    class FakeExtractor:
        def extract(self, url: str):
            return type(
                "Extracted",
                (),
                {"url": url, "title": "Extracted page", "markdown": "# Page", "metadata": {}},
            )()

    search = RecordingSearch()
    SearchDataAgent(search, FakeExtractor()).run(workspace.root)

    plan = read_json(workspace.root / "data" / "search_plan.json", {})
    assert "multi_criteria_evaluation" in plan["selected_routes"]
    assert any("priority indicator" in query for query in search.queries)
    assert any("resource allocation constraint" in query for query in search.queries)
    assert any(need["route_id"] == "constrained_optimization" for need in plan["data_needs"])


def test_search_data_agent_includes_feasibility_matrix_needs(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "experiment_plan.md").write_text(
        "# Experiment Plan\n\n## Required Datasets\n- cleaned attachment tables\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "data" / "data_feasibility_matrix.json",
        [
            {
                "need_id": "need_001",
                "target_dataset": "public population data",
                "query": "public population data public dataset official",
                "availability": "available",
                "confidence": 0.75,
                "top_urls": ["https://data.gov/population"],
                "proxy_variables": [],
                "recommended_action": "Use public population data.",
            },
            {
                "need_id": "need_002",
                "target_dataset": "football player salary and bonus contracts",
                "query": "football player salary and bonus contracts public dataset official",
                "availability": "private_or_unavailable",
                "confidence": 0.9,
                "top_urls": [],
                "proxy_variables": ["Market value or transfer fee"],
                "recommended_action": "Reframe with proxy variables.",
            },
        ],
    )

    class RecordingSearch:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
            self.queries.append(query)
            return []

    class UnusedExtractor:
        def extract(self, url: str):
            raise AssertionError("extractor should not be called")

    search = RecordingSearch()
    SearchDataAgent(search, UnusedExtractor()).run(workspace.root)

    plan = read_json(workspace.root / "data" / "search_plan.json", {})
    assert "public population data public dataset official" in search.queries
    assert "football player salary and bonus contracts public dataset official" not in search.queries
    assert any(need["source"] == "data_feasibility_matrix" for need in plan["data_needs"])
    assert any(need["status"] == "skipped_private_or_unavailable" for need in plan["data_needs"])


def test_search_data_sources_keep_data_need_trace(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "experiment_plan.md").write_text(
        "# Experiment Plan\n\n## Required Datasets\n- cleaned attachment tables\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "data" / "data_feasibility_matrix.json",
        [
            {
                "need_id": "need_001",
                "target_dataset": "public population data",
                "query": "public population data public dataset official",
                "availability": "available",
                "confidence": 0.75,
                "top_urls": ["https://data.gov/population"],
                "proxy_variables": [],
                "recommended_action": "Use public population data.",
            }
        ],
    )

    class FakeSearch:
        def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
            if "population" not in query:
                return []
            return [
                SearchResult(
                    title="Official population data",
                    url="https://data.gov/population",
                    snippet="official source",
                    score=0.99,
                )
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
    lineage = read_json(workspace.root / "data" / "data_lineage.json", [])
    assert sources[0]["data_need_id"] == "need_001"
    assert sources[0]["target_dataset"] == "public population data"
    assert sources[0]["source_query"] == "public population data public dataset official"
    assert lineage[0]["used_in"] == ["data/source_registry.json", "data/data_feasibility_matrix.json"]


def test_source_gate_fails_when_searchable_data_need_has_no_trusted_source(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "experiment_plan.md").write_text(
        "# Experiment Plan\n\n## Required Datasets\n- cleaned attachment tables\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "data" / "data_feasibility_matrix.json",
        [
            {
                "need_id": "need_001",
                "target_dataset": "public population data",
                "query": "public population data public dataset official",
                "availability": "available",
                "confidence": 0.75,
                "top_urls": [],
                "proxy_variables": [],
                "recommended_action": "Use public population data.",
            }
        ],
    )

    class BlogOnlySearch:
        def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
            if "population" not in query:
                return []
            return [
                SearchResult(
                    title="Population blog",
                    url="https://blog.example/population",
                    snippet="unofficial commentary",
                    score=0.4,
                )
            ]

    class FakeExtractor:
        def extract(self, url: str):
            return type(
                "Extracted",
                (),
                {"url": url, "title": "Extracted page", "markdown": "# Page", "metadata": {}},
            )()

    SearchDataAgent(BlogOnlySearch(), FakeExtractor()).run(workspace.root)

    gate = read_json(workspace.root / "review" / "source_gate.json", {})
    assert gate["status"] == "fail"
    assert gate["failure_reason"] == "source_unreliable"
    assert "need_001" in gate["blocking_findings"][0]
    assert "public population data" in gate["blocking_findings"][0]


def test_search_repair_report_explains_uncovered_data_need(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "experiment_plan.md").write_text(
        "# Experiment Plan\n\n## Required Datasets\n- cleaned attachment tables\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "data" / "data_feasibility_matrix.json",
        [
            {
                "need_id": "need_001",
                "target_dataset": "public population data",
                "query": "public population data public dataset official",
                "availability": "available",
                "confidence": 0.75,
                "top_urls": [],
                "proxy_variables": [],
                "recommended_action": "Use public population data.",
            }
        ],
    )

    class BlogOnlySearch:
        def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
            if "population" not in query:
                return []
            return [
                SearchResult(
                    title="Population blog",
                    url="https://blog.example/population",
                    snippet="unofficial commentary",
                    score=0.4,
                )
            ]

    class FakeExtractor:
        def extract(self, url: str):
            return type(
                "Extracted",
                (),
                {"url": url, "title": "Extracted page", "markdown": "# Page", "metadata": {}},
            )()

    SearchDataAgent(BlogOnlySearch(), FakeExtractor()).run(workspace.root)

    report = (workspace.root / "reports" / "search_repair_report.md").read_text(
        encoding="utf-8"
    )
    actions = read_json(workspace.root / "data" / "search_repair_actions.json", [])
    assert "need_001" in report
    assert "public population data public dataset official" in report
    assert "https://blog.example/population" in report
    assert actions[0]["data_need_id"] == "need_001"
    assert actions[0]["recommended_action"] == "try_official_api_or_reframe"
    assert "World Bank" in actions[0]["official_api_candidates"]


def test_search_data_repairs_uncovered_need_with_official_api_provider(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "experiment_plan.md").write_text(
        "# Experiment Plan\n\n## Required Datasets\n- cleaned attachment tables\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "data" / "data_feasibility_matrix.json",
        [
            {
                "need_id": "need_001",
                "target_dataset": "public population data",
                "query": "public population data public dataset official",
                "availability": "available",
                "confidence": 0.75,
                "top_urls": [],
                "proxy_variables": [],
                "recommended_action": "Use public population data.",
            }
        ],
    )

    class BlogOnlySearch:
        def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
            if "population" not in query:
                return []
            return [
                SearchResult(
                    title="Population blog",
                    url="https://blog.example/population",
                    snippet="unofficial commentary",
                    score=0.4,
                )
            ]

    class FakeExtractor:
        def extract(self, url: str):
            return type(
                "Extracted",
                (),
                {"url": url, "title": "Extracted page", "markdown": "# Page", "metadata": {}},
            )()

    class FakeOfficialApiRepair:
        def repair(self, workspace_root: Path, need: dict[str, str]):
            return [
                {
                    "source_id": "worldbank_population",
                    "title": "World Bank population data",
                    "url": "https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
                    "license": "World Bank open data",
                    "provider": "world_bank_api",
                    "local_path": "data/raw/worldbank_population.json",
                }
            ]

    SearchDataAgent(BlogOnlySearch(), FakeExtractor(), FakeOfficialApiRepair()).run(
        workspace.root
    )

    gate = read_json(workspace.root / "review" / "source_gate.json", {})
    sources = read_json(workspace.root / "data" / "source_registry.json", [])
    lineage = read_json(workspace.root / "data" / "data_lineage.json", [])
    assert gate["status"] == "pass"
    assert any(source["provider"] == "world_bank_api" for source in sources)
    official_source = next(source for source in sources if source["provider"] == "world_bank_api")
    assert official_source["data_need_id"] == "need_001"
    assert official_source["target_dataset"] == "public population data"
    assert any(item["source_id"] == "worldbank_population" for item in lineage)
    assert not (workspace.root / "reports" / "search_repair_report.md").exists()


def test_source_gate_allows_generic_feasibility_need_when_attachment_exists(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "experiment_plan.md").write_text(
        "# Experiment Plan\n\n## Required Datasets\n- cleaned attachment tables\n",
        encoding="utf-8",
    )
    attachment = workspace.root / "input" / "attachments" / "data.csv"
    attachment.parent.mkdir(parents=True, exist_ok=True)
    attachment.write_text("x,y\n1,2\n", encoding="utf-8")
    write_json(
        workspace.root / "data" / "data_feasibility_matrix.json",
        [
            {
                "need_id": "need_001",
                "target_dataset": "problem-specific modeling data",
                "query": "problem-specific modeling data public dataset official",
                "availability": "unknown",
                "confidence": 0.55,
                "top_urls": [],
                "proxy_variables": [],
                "recommended_action": "Run deeper search.",
            }
        ],
    )

    class EmptySearch:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
            self.queries.append(query)
            return []

    class UnusedExtractor:
        def extract(self, url: str):
            raise AssertionError("extractor should not be called")

    search = EmptySearch()
    SearchDataAgent(search, UnusedExtractor()).run(workspace.root)

    plan = read_json(workspace.root / "data" / "search_plan.json", {})
    gate = read_json(workspace.root / "review" / "source_gate.json", {})
    assert gate["status"] == "pass"
    assert any(need["status"] == "covered_by_attachment" for need in plan["data_needs"])
    assert "problem-specific modeling data public dataset official" not in search.queries


def test_search_data_agent_tolerates_extraction_failure(tmp_path: Path) -> None:
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
                )
            ]

    class FailingExtractor:
        def extract(self, url: str):
            raise RuntimeError("Firecrawl scrape failed: 403")

    # One blocked URL must not crash the whole stage.
    SearchDataAgent(FakeSearch(), FailingExtractor()).run(workspace.root)

    retrieval_log = (workspace.root / "data" / "retrieval_log.jsonl").read_text(encoding="utf-8")
    assert "extraction_failed" in retrieval_log
    sources = read_json(workspace.root / "data" / "source_registry.json", [])
    assert not any(s.get("url") == "https://data.gov/example" for s in sources)


def test_source_gate_respects_user_provided_assumptions_strategy(
    tmp_path: Path,
) -> None:
    """When the discussion stage locked user_provided_assumptions, an unknown/
    uncovered feasibility-matrix data need is exempted (mirrors modeling_quality_gate)."""
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "experiment_plan.md").write_text(
        "# Experiment Plan\n\n## Required Datasets\n- problem-specific modeling data\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "data" / "data_feasibility_matrix.json",
        [
            {
                "need_id": "need_001",
                "target_dataset": "problem-specific modeling data",
                "query": "problem-specific modeling data public dataset official",
                "availability": "unknown",
                "confidence": 0.55,
                "top_urls": [],
                "proxy_variables": [],
                "recommended_action": "Run deeper search.",
            }
        ],
    )
    (workspace.root / "discussion").mkdir(parents=True, exist_ok=True)
    write_json(
        workspace.root / "discussion" / "direction_lock.json",
        {"adopted_reframing_strategy": "user_provided_assumptions", "language": "en"},
    )

    class BlogOnlySearch:
        def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
            return [
                SearchResult(
                    title="Blog",
                    url="https://blog.example/post",
                    snippet="background",
                    score=0.3,
                )
            ]

    class FakeExtractor:
        def extract(self, url: str):
            return type(
                "Extracted",
                (),
                {"url": url, "title": "P", "markdown": "# Page", "metadata": {}},
            )()

    SearchDataAgent(BlogOnlySearch(), FakeExtractor()).run(workspace.root)

    gate = read_json(workspace.root / "review" / "source_gate.json", {})
    assert gate["status"] == "pass", gate


def test_source_gate_still_fails_when_no_user_strategy_and_unknown_need(
    tmp_path: Path,
) -> None:
    """Without the user_provided_assumptions lock, the unknown need still blocks."""
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "experiment_plan.md").write_text(
        "# Experiment Plan\n\n## Required Datasets\n- problem-specific modeling data\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "data" / "data_feasibility_matrix.json",
        [
            {
                "need_id": "need_001",
                "target_dataset": "problem-specific modeling data",
                "query": "problem-specific modeling data public dataset official",
                "availability": "unknown",
                "confidence": 0.55,
                "top_urls": [],
                "proxy_variables": [],
                "recommended_action": "Run deeper search.",
            }
        ],
    )

    class BlogOnlySearch:
        def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
            return [
                SearchResult(
                    title="Blog",
                    url="https://blog.example/post",
                    snippet="background",
                    score=0.3,
                )
            ]

    class FakeExtractor:
        def extract(self, url: str):
            return type(
                "Extracted",
                (),
                {"url": url, "title": "P", "markdown": "# Page", "metadata": {}},
            )()

    SearchDataAgent(BlogOnlySearch(), FakeExtractor()).run(workspace.root)

    gate = read_json(workspace.root / "review" / "source_gate.json", {})
    assert gate["status"] == "fail"
    assert gate["failure_reason"] == "source_unreliable"
