from fastapi.testclient import TestClient

from mcm_agent.server.app import create_app


def test_workspace_api_creates_workspace_and_uploads_files(tmp_path) -> None:
    client = TestClient(create_app(workspace_base=tmp_path / "workspaces"))

    create_response = client.post("/api/workspaces", json={"workspace_id": "task_001"})
    upload_response = client.post(
        "/api/workspaces/task_001/files",
        files={"files": ("problem.md", b"# Problem\nSolve this.", "text/markdown")},
        data={"kind": "problem"},
    )
    status_response = client.get("/api/workspaces/task_001/status")

    assert create_response.status_code == 200
    assert upload_response.status_code == 200
    assert status_response.status_code == 200
    assert (tmp_path / "workspaces" / "task_001" / "input" / "problem" / "problem.md").exists()
    assert status_response.json()["workspace_id"] == "task_001"


def test_artifact_api_lists_and_reads_safe_workspace_files(tmp_path) -> None:
    client = TestClient(create_app(workspace_base=tmp_path / "workspaces"))
    client.post("/api/workspaces", json={"workspace_id": "task_001"})
    report = tmp_path / "workspaces" / "task_001" / "reports" / "demo.md"
    report.write_text("# Demo Report\n", encoding="utf-8")

    list_response = client.get("/api/workspaces/task_001/artifacts")
    content_response = client.get(
        "/api/workspaces/task_001/artifacts/content",
        params={"path": "reports/demo.md"},
    )
    escape_response = client.get(
        "/api/workspaces/task_001/artifacts/content",
        params={"path": "../secret.txt"},
    )

    assert list_response.status_code == 200
    assert "reports/demo.md" in list_response.json()["artifacts"]
    assert content_response.json()["content"] == "# Demo Report\n"
    assert escape_response.status_code == 400
