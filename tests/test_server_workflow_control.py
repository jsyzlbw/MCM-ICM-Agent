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


def test_pause_then_approve_resumes(tmp_path, monkeypatch):
    # Force a pause after "intake" so the bounded demo run pauses deterministically.
    import mcm_agent.server.routes_workflow as rw
    monkeypatch.setattr(rw, "PAUSE_AFTER_DEFAULT", {"intake"})

    client = _client(tmp_path)
    _seed_workspace(client)

    run = client.post(
        "/api/workspaces/task_001/run",
        json={"demo": True, "auto_approve": False, "until_stage": "problem_understanding"},
    )
    assert run.status_code == 200
    assert _wait_run_state(client, "paused")

    status = client.get("/api/workspaces/task_001/run").json()
    checkpoint_id = status["pending_checkpoint_id"]
    assert checkpoint_id is not None

    approve = client.post(
        f"/api/workspaces/task_001/checkpoints/{checkpoint_id}/approve",
        json={"user_message": "looks good"},
    )
    assert approve.status_code == 200
    assert _wait_run_state(client, "done")
