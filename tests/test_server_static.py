from fastapi.testclient import TestClient

from mcm_agent.server.app import create_app


def test_root_serves_gui_shell(tmp_path) -> None:
    client = TestClient(create_app(workspace_base=tmp_path / "workspaces"))

    response = client.get("/")

    assert response.status_code == 200
    assert "MCM-ICM Agent" in response.text
    assert "/static/app.js" in response.text


def test_static_assets_are_served(tmp_path) -> None:
    client = TestClient(create_app(workspace_base=tmp_path / "workspaces"))

    assert client.get("/static/styles.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/vendor/alpine.min.js").status_code == 200
