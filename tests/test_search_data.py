from pathlib import Path

import respx
from httpx import Response

from mcm_agent.agents.search_data import SearchDataAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.academic import OpenAlexProvider
from mcm_agent.providers.data_apis import OfficialDataApiRepairProvider, WorldBankProvider
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
