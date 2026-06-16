import time

from fastapi.testclient import TestClient

from mcm_agent.server.app import create_app


def _client(tmp_path):
    return TestClient(create_app(workspace_base=tmp_path / "workspaces"))


def _seed_workspace(client):
    client.post("/api/workspaces", json={"workspace_id": "task_001"})
    client.post(
        "/api/workspaces/task_001/files",
        files={"files": ("problem.md", b"# Problem\nEvaluate three options.", "text/markdown")},
        data={"kind": "problem"},
    )


def _wait_run_state(client, expected, timeout=30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        state = client.get("/api/workspaces/task_001/run").json()["state"]
        if state == expected:
            return True
        time.sleep(0.1)
    return False


def test_run_endpoint_runs_bounded_demo_to_completion(tmp_path):
    client = _client(tmp_path)
    _seed_workspace(client)

    run = client.post(
        "/api/workspaces/task_001/run",
        json={"demo": True, "auto_approve": True, "until_stage": "problem_understanding"},
    )
    assert run.status_code == 200
    assert _wait_run_state(client, "done")

    lines = (tmp_path / "workspaces" / "task_001" / "stage_runs.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    stage_ids = [line for line in lines if "problem_understanding" in line]
    assert stage_ids  # reached problem_understanding


def test_run_endpoint_rejects_double_start(tmp_path):
    client = _client(tmp_path)
    _seed_workspace(client)
    client.post(
        "/api/workspaces/task_001/run",
        json={"demo": True, "auto_approve": True, "until_stage": "submission_packager"},
    )
    second = client.post(
        "/api/workspaces/task_001/run",
        json={"demo": True, "auto_approve": True},
    )
    assert second.status_code == 409


def test_run_endpoint_requires_problem_file(tmp_path):
    client = _client(tmp_path)
    client.post("/api/workspaces", json={"workspace_id": "task_001"})
    resp = client.post("/api/workspaces/task_001/run", json={"demo": True, "auto_approve": True})
    assert resp.status_code == 400
