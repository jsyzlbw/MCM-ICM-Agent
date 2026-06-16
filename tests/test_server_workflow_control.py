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


def test_events_stream_replays_after_completion(tmp_path):
    client = _client(tmp_path)
    _seed_workspace(client)
    client.post(
        "/api/workspaces/task_001/run",
        json={"demo": True, "auto_approve": True, "until_stage": "problem_understanding"},
    )
    assert _wait_run_state(client, "done")

    # After completion, a fresh SSE connection replays stage events from file and closes.
    event_types = []
    with client.stream("GET", "/api/workspaces/task_001/events") as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("event:"):
                event_types.append(line.split(":", 1)[1].strip())
            if "run_finished" in line:
                break

    assert "stage_completed" in event_types
    assert "run_finished" in event_types


def test_logs_endpoint_returns_recent_lines(tmp_path):
    client = _client(tmp_path)
    _seed_workspace(client)
    client.post(
        "/api/workspaces/task_001/run",
        json={"demo": True, "auto_approve": True, "until_stage": "problem_understanding"},
    )
    assert _wait_run_state(client, "done")
    logs = client.get("/api/workspaces/task_001/logs").json()
    assert "stages" in logs
    assert any(s["stage_id"] == "problem_understanding" for s in logs["stages"])


def test_run_endpoint_blocks_real_run_without_config(tmp_path):
    client = TestClient(
        create_app(config_path=tmp_path / "missing.json", workspace_base=tmp_path / "workspaces")
    )
    client.post("/api/workspaces", json={"workspace_id": "task_001"})
    client.post(
        "/api/workspaces/task_001/files",
        files={"files": ("problem.md", b"# Problem", "text/markdown")},
        data={"kind": "problem"},
    )
    resp = client.post("/api/workspaces/task_001/run", json={"demo": False, "auto_approve": True})
    assert resp.status_code == 400


def test_task_input_picks_up_user_requirements(tmp_path):
    from mcm_agent.core.workspace import create_workspace
    from mcm_agent.server.routes_workflow import _task_input_from_workspace

    root = create_workspace(tmp_path / "ws").root
    (root / "input" / "problem").mkdir(parents=True, exist_ok=True)
    (root / "input" / "problem" / "p.md").write_text("# P", encoding="utf-8")
    (root / "input" / "user_requirements.md").write_text("prefer interpretable models", encoding="utf-8")

    task_input = _task_input_from_workspace(root)
    assert task_input.user_idea_file is not None
    assert task_input.user_idea_file.name == "user_requirements.md"


def test_run_persists_user_requirements(tmp_path):
    client = _client(tmp_path)
    _seed_workspace(client)
    client.post(
        "/api/workspaces/task_001/run",
        json={
            "demo": True,
            "auto_approve": True,
            "until_stage": "problem_understanding",
            "user_requirements": "use vector-first figures",
        },
    )
    req = tmp_path / "workspaces" / "task_001" / "input" / "user_requirements.md"
    assert req.exists()
    assert "vector-first" in req.read_text(encoding="utf-8")


def test_state_from_files_transitions(tmp_path):
    from mcm_agent.core.workspace import create_workspace
    from mcm_agent.server.routes_workflow import _state_from_files
    from mcm_agent.utils.json_io import read_json, write_json

    root = create_workspace(tmp_path / "ws").root
    assert _state_from_files(root) == "idle"
    (root / "final_submission").mkdir(parents=True, exist_ok=True)
    write_json(root / "final_submission" / "submission_manifest.json", {})
    assert _state_from_files(root) == "done"
    state = read_json(root / "task_state.json", {})
    state["blocked_reason"] = "gate/fail"
    write_json(root / "task_state.json", state)
    assert _state_from_files(root) == "failed"
