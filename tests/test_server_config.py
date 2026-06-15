from fastapi.testclient import TestClient

from mcm_agent.server.app import create_app


def test_server_health_endpoint() -> None:
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_config_api_saves_local_json_and_masks_secrets(tmp_path) -> None:
    client = TestClient(create_app(config_path=tmp_path / "mcm_agent_config.local.json"))
    payload = {
        "llm": {
            "provider": "openai_compatible",
            "api_key": "sk-secret-value",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4.1",
            "timeout_seconds": 60,
        },
        "search": {"tavily_api_key": "tvly-secret"},
        "official_data": {"fred_api_key": ""},
        "mineru": {"mode": "fake", "api_key": ""},
        "humanizer": {"api_key": ""},
        "rag": {
            "knowledge_base_dir": "knowledge_base",
            "ingest_extensions": [".md", ".txt", ".pdf"],
        },
        "runtime": {
            "default_language": "en",
            "max_retries": 2,
            "http_timeout_seconds": 60,
            "code_timeout_seconds": 120,
        },
    }

    save_response = client.post("/api/config", json=payload)
    get_response = client.get("/api/config")

    assert save_response.status_code == 200
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["llm"]["api_key_configured"] is True
    assert body["llm"]["api_key_preview"] == "alue"
    assert "sk-secret-value" not in str(body)
    assert (tmp_path / "mcm_agent_config.local.json").exists()
