import importlib.util
from pathlib import Path

import respx
from httpx import Response

from mcm_agent.config import Settings
from mcm_agent.providers.smoke import ProviderSmokeTester, SmokeStatus


def _load_smoke_script():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "smoke_providers.py"
    spec = importlib.util.spec_from_file_location("smoke_providers_script", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_tester_skips_missing_provider_keys(tmp_path: Path) -> None:
    tester = ProviderSmokeTester(Settings(), workspace_root=tmp_path)

    results = tester.run(
        [
            "llm",
            "tavily",
            "brave",
            "exa",
            "firecrawl",
            "humanizer",
            "mineru",
            "fred",
            "noaa",
        ]
    )

    assert {result.provider: result.status for result in results} == {
        "llm": "skipped",
        "tavily": "skipped",
        "brave": "skipped",
        "exa": "skipped",
        "firecrawl": "skipped",
        "humanizer": "skipped",
        "mineru": "skipped",
        "fred": "skipped",
        "noaa": "skipped",
    }


@respx.mock
def test_smoke_tester_checks_openai_compatible_llm(tmp_path: Path) -> None:
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={
                "id": "chatcmpl-test",
                "choices": [{"message": {"content": "OK"}}],
                "usage": {"total_tokens": 3},
            },
        )
    )
    tester = ProviderSmokeTester(
        Settings(
            openai_api_key="test-key",
            openai_base_url="https://api.example.com/v1",
            openai_model="test-model",
        ),
        workspace_root=tmp_path,
    )

    result = tester.check("llm")

    assert result.status == SmokeStatus.PASSED
    assert result.latency_ms >= 0


@respx.mock
def test_smoke_tester_checks_tavily_search(tmp_path: Path) -> None:
    respx.post("https://api.tavily.com/search").mock(
        return_value=Response(
            200,
            json={"results": [{"title": "Official data", "url": "https://data.gov/x"}]},
        )
    )
    tester = ProviderSmokeTester(Settings(tavily_api_key="test-key"), workspace_root=tmp_path)

    result = tester.check("tavily")

    assert result.status == SmokeStatus.PASSED
    assert "1 result" in result.detail


@respx.mock
def test_smoke_tester_checks_brave_search(tmp_path: Path) -> None:
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "title": "Official",
                            "url": "https://data.gov",
                            "description": "Data",
                        }
                    ]
                }
            },
        )
    )
    tester = ProviderSmokeTester(Settings(brave_search_api_key="test-key"), workspace_root=tmp_path)

    result = tester.check("brave")

    assert result.status == SmokeStatus.PASSED


@respx.mock
def test_smoke_tester_checks_exa_search(tmp_path: Path) -> None:
    respx.post("https://api.exa.ai/search").mock(
        return_value=Response(
            200,
            json={"results": [{"title": "Official", "url": "https://data.gov", "text": "Data"}]},
        )
    )
    tester = ProviderSmokeTester(Settings(exa_api_key="test-key"), workspace_root=tmp_path)

    result = tester.check("exa")

    assert result.status == SmokeStatus.PASSED


@respx.mock
def test_smoke_tester_checks_firecrawl_extract(tmp_path: Path) -> None:
    respx.post("https://api.firecrawl.dev/v1/scrape").mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "markdown": "# Example Domain",
                    "metadata": {"title": "Example Domain"},
                }
            },
        )
    )
    tester = ProviderSmokeTester(Settings(firecrawl_api_key="test-key"), workspace_root=tmp_path)

    result = tester.check("firecrawl")

    assert result.status == SmokeStatus.PASSED
    assert (tmp_path / "smoke" / "firecrawl" / "source_001.md").exists()


@respx.mock
def test_smoke_tester_checks_humanizer_job(tmp_path: Path) -> None:
    respx.post("https://leahloveswriting.xyz/api_v2/rewrite/english/jobs").mock(
        return_value=Response(200, json={"success": True, "data": {"task_id": "job_1"}})
    )
    respx.get("https://leahloveswriting.xyz/api_v2/rewrite/english/jobs/job_1").mock(
        return_value=Response(
            200,
            json={"success": True, "data": {"status": "completed", "result": "This is a test."}},
        )
    )
    tester = ProviderSmokeTester(Settings(humanizer_api_key="test-key"), workspace_root=tmp_path)

    result = tester.check("humanizer")

    assert result.status == SmokeStatus.PASSED


def test_smoke_tester_requires_mineru_file_for_rest_mode(tmp_path: Path) -> None:
    tester = ProviderSmokeTester(
        Settings(mineru_mode="rest", mineru_api_key="test-key"),
        workspace_root=tmp_path,
    )

    result = tester.check("mineru")

    assert result.status == SmokeStatus.SKIPPED
    assert "mineru_file" in result.detail


@respx.mock
def test_smoke_tester_checks_no_key_official_data_provider(tmp_path: Path) -> None:
    respx.get("https://archive-api.open-meteo.com/v1/archive").mock(
        return_value=Response(200, json={"daily": {"temperature_2m_max": [1]}})
    )
    tester = ProviderSmokeTester(Settings(), workspace_root=tmp_path)

    result = tester.check("open_meteo")

    assert result.status == SmokeStatus.PASSED


def test_smoke_script_accepts_json_config_file_argument(tmp_path: Path) -> None:
    config_file = tmp_path / "mcm_agent_config.local.json"
    config_file.write_text("{}", encoding="utf-8")

    args = _load_smoke_script().build_parser().parse_args(["--config-file", str(config_file)])

    assert args.config_file == str(config_file)
