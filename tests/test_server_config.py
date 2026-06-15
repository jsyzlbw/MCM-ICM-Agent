from fastapi.testclient import TestClient

from mcm_agent.server.app import create_app


def test_server_health_endpoint() -> None:
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
