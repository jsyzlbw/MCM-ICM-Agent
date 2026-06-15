# GUI Service Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the K-route backend service foundation for the future GUI: FastAPI app, config APIs, per-provider connectivity checks, workspace upload APIs, progress events, and background workflow run/resume endpoints.

**Architecture:** Keep the existing CLI/workflow as the source of truth and add a thin `mcm_agent.server` layer around it. The server reads/writes local ignored JSON config, stores task files in normal workspaces, records GUI-oriented progress events as `progress_events.jsonl`, and starts workflow runs through a background runner. No frontend is built in this route; L will consume these APIs.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Typer, pytest, FastAPI TestClient, existing `mcm_agent` workspace/workflow/provider modules.

---

## File Structure

- Modify `pyproject.toml`: add FastAPI, Uvicorn, and multipart upload dependencies.
- Modify `src/mcm_agent/cli.py`: add `mcm-agent gui` command.
- Create `src/mcm_agent/server/__init__.py`: server package marker.
- Create `src/mcm_agent/server/app.py`: FastAPI app factory.
- Create `src/mcm_agent/server/schemas.py`: request/response models.
- Create `src/mcm_agent/server/config_store.py`: safe config loading/saving/masking helpers.
- Create `src/mcm_agent/server/routes_config.py`: config and provider test endpoints.
- Create `src/mcm_agent/server/routes_workspace.py`: workspace create/list/detail/upload/run/resume/stop/status endpoints.
- Create `src/mcm_agent/server/routes_events.py`: progress event read/write helpers and endpoint.
- Create `src/mcm_agent/server/routes_artifacts.py`: artifact listing/content/download endpoint.
- Create `src/mcm_agent/server/background.py`: in-process background task registry.
- Modify `src/mcm_agent/core/stage_executor.py`: emit progress events at stage start/pass/fail.
- Modify `src/mcm_agent/core/workspace.py`: initialize `progress_events.jsonl`.
- Create `tests/test_server_config.py`: config API and per-provider test API.
- Create `tests/test_server_workspace.py`: workspace create/upload/status/artifact APIs.
- Create `tests/test_progress_events.py`: stage executor progress events.

## Task 1: Server Dependencies And App Skeleton

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/mcm_agent/cli.py`
- Create: `src/mcm_agent/server/__init__.py`
- Create: `src/mcm_agent/server/app.py`
- Create: `src/mcm_agent/server/schemas.py`
- Test: `tests/test_server_config.py`

- [ ] **Step 1: Write failing health/app test**

Create `tests/test_server_config.py`:

```python
from fastapi.testclient import TestClient

from mcm_agent.server.app import create_app


def test_server_health_endpoint() -> None:
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_server_config.py::test_server_health_endpoint -q
```

Expected: FAIL because `mcm_agent.server` does not exist.

- [ ] **Step 3: Add dependencies and minimal app**

In `pyproject.toml`, add runtime dependencies:

```toml
"fastapi>=0.115.0",
"uvicorn>=0.30.6",
"python-multipart>=0.0.9",
```

Create `src/mcm_agent/server/__init__.py`:

```python
"""FastAPI service layer for the local GUI."""
```

Create `src/mcm_agent/server/app.py`:

```python
from __future__ import annotations

from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="MCM/ICM Agent GUI API")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
```

Create `src/mcm_agent/server/schemas.py`:

```python
from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
```

- [ ] **Step 4: Add CLI `gui` command**

In `src/mcm_agent/cli.py`, add:

```python
@app.command("gui")
def gui(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8787, "--port"),
) -> None:
    """Start the local GUI API server."""
    import uvicorn

    typer.echo(f"Starting MCM Agent GUI API at http://{host}:{port}")
    uvicorn.run("mcm_agent.server.app:create_app", factory=True, host=host, port=port)
```

- [ ] **Step 5: Run test**

Run:

```bash
pytest tests/test_server_config.py::test_server_health_endpoint -q
ruff check src/mcm_agent/server src/mcm_agent/cli.py tests/test_server_config.py
```

Expected: PASS.

- [ ] **Step 6: Commit and push**

```bash
git add pyproject.toml src/mcm_agent/cli.py src/mcm_agent/server tests/test_server_config.py
git commit -m "feat: add gui api server skeleton"
git push origin main
```

## Task 2: Config Read/Write API With Secret Masking

**Files:**
- Create: `src/mcm_agent/server/config_store.py`
- Modify: `src/mcm_agent/server/app.py`
- Modify: `src/mcm_agent/server/routes_config.py`
- Modify: `src/mcm_agent/server/schemas.py`
- Test: `tests/test_server_config.py`

- [ ] **Step 1: Add failing config API test**

Append to `tests/test_server_config.py`:

```python
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
        "rag": {"knowledge_base_dir": "knowledge_base", "ingest_extensions": [".md", ".txt", ".pdf"]},
        "runtime": {"default_language": "en", "max_retries": 2, "http_timeout_seconds": 60, "code_timeout_seconds": 120},
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
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_server_config.py::test_config_api_saves_local_json_and_masks_secrets -q
```

Expected: FAIL because config routes do not exist.

- [ ] **Step 3: Implement config store and routes**

Create `src/mcm_agent/server/config_store.py` with:

- `default_config() -> dict[str, object]`
- `read_config(path: Path) -> dict[str, object]`
- `write_config(path: Path, payload: dict[str, object]) -> None`
- `mask_config(payload: dict[str, object]) -> dict[str, object]`

Rules:

- Missing config returns default config.
- `mask_config` replaces keys ending with `api_key` or named `api_key` with:
  - `<key>_configured: bool`
  - `<key>_preview: last 4 chars or ""`
  - no raw secret value.
- Non-secret values are returned unchanged.

Create `src/mcm_agent/server/routes_config.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter

from mcm_agent.server.config_store import mask_config, read_config, write_config


def create_config_router(config_path: Path) -> APIRouter:
    router = APIRouter(prefix="/api/config", tags=["config"])

    @router.get("")
    def get_config() -> dict[str, Any]:
        return mask_config(read_config(config_path))

    @router.post("")
    def save_config(payload: dict[str, Any]) -> dict[str, Any]:
        write_config(config_path, payload)
        return mask_config(payload)

    return router
```

Modify `create_app(config_path: Path | None = None, workspace_base: Path | None = None)` to include router.

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/test_server_config.py -q
ruff check src/mcm_agent/server tests/test_server_config.py
```

Expected: PASS.

- [ ] **Step 5: Commit and push**

```bash
git add src/mcm_agent/server tests/test_server_config.py
git commit -m "feat: add gui config api"
git push origin main
```

## Task 3: Per-Provider Connectivity Test API

**Files:**
- Modify: `src/mcm_agent/server/routes_config.py`
- Modify: `src/mcm_agent/server/schemas.py`
- Test: `tests/test_server_config.py`

- [ ] **Step 1: Add failing per-provider test**

Append:

```python
def test_config_api_tests_single_provider_without_running_all_smokes(tmp_path) -> None:
    config_path = tmp_path / "mcm_agent_config.local.json"
    client = TestClient(create_app(config_path=config_path, workspace_base=tmp_path / "workspaces"))
    client.post(
        "/api/config",
        json={
            "llm": {"api_key": "", "model": "gpt-4.1", "base_url": "", "timeout_seconds": 60},
            "search": {"tavily_api_key": ""},
            "official_data": {},
            "mineru": {"mode": "fake", "api_key": ""},
            "humanizer": {"api_key": ""},
            "rag": {"knowledge_base_dir": "knowledge_base", "ingest_extensions": [".md", ".txt", ".pdf"]},
            "runtime": {"default_language": "en", "max_retries": 2, "http_timeout_seconds": 60, "code_timeout_seconds": 120},
        },
    )

    response = client.post("/api/config/test-provider", json={"provider": "llm"})

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "llm"
    assert body["status"] == "skipped"
    assert "not configured" in body["detail"]
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_server_config.py::test_config_api_tests_single_provider_without_running_all_smokes -q
```

Expected: FAIL because `/api/config/test-provider` does not exist.

- [ ] **Step 3: Implement endpoint**

In `schemas.py` add:

```python
class ProviderTestRequest(BaseModel):
    provider: str
    mineru_file: str | None = None
```

In `routes_config.py`, add POST `/test-provider`:

- Read raw config from local JSON.
- Build `Settings` by calling `load_settings(config_file=str(config_path))`.
- Create `ProviderSmokeTester(settings, workspace_root=workspace_base / ".smoke", mineru_file=...)`.
- Call `.check(request.provider)`.
- Return `result.model_dump(mode="json")`.

This endpoint is the backend for the GUI requirement: every API config row can have its own "test connectivity" button.

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/test_server_config.py -q
ruff check src/mcm_agent/server tests/test_server_config.py
```

Expected: PASS.

- [ ] **Step 5: Commit and push**

```bash
git add src/mcm_agent/server tests/test_server_config.py
git commit -m "feat: add per-provider gui connectivity checks"
git push origin main
```

## Task 4: Workspace Create, List, Upload, Status, Artifact APIs

**Files:**
- Create: `src/mcm_agent/server/routes_workspace.py`
- Create: `src/mcm_agent/server/routes_artifacts.py`
- Modify: `src/mcm_agent/server/app.py`
- Modify: `src/mcm_agent/server/schemas.py`
- Test: `tests/test_server_workspace.py`

- [ ] **Step 1: Add failing workspace API tests**

Create `tests/test_server_workspace.py`:

```python
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
```

Add:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_server_workspace.py -q
```

Expected: FAIL because workspace/artifact routes do not exist.

- [ ] **Step 3: Implement routes**

`routes_workspace.py`:

- POST `/api/workspaces`: calls `create_workspace(workspace_base / workspace_id)`.
- GET `/api/workspaces`: lists directories containing `task_state.json`.
- GET `/api/workspaces/{workspace_id}`: returns root, task_state, recent stage runs.
- POST `/api/workspaces/{workspace_id}/files`: saves uploaded files under:
  - `kind=problem` -> `input/problem`
  - `kind=attachment` -> `input/attachments`
  - `kind=template` -> `input/template`
  - `kind=chat` -> `input/chat_uploads`
- GET `/api/workspaces/{workspace_id}/status`: returns `task_state.json`, latest failed gate, stage runs summary.

`routes_artifacts.py`:

- GET `/api/workspaces/{workspace_id}/artifacts`: returns safe relative paths under workspace, excluding large transient caches.
- GET `/api/workspaces/{workspace_id}/artifacts/content?path=...`: reads text files after path traversal check.
- GET `/api/workspaces/{workspace_id}/artifacts/download?path=...`: returns `FileResponse`.

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/test_server_workspace.py -q
ruff check src/mcm_agent/server tests/test_server_workspace.py
```

Expected: PASS.

- [ ] **Step 5: Commit and push**

```bash
git add src/mcm_agent/server tests/test_server_workspace.py
git commit -m "feat: add gui workspace and artifact APIs"
git push origin main
```

## Task 5: Progress Events From Stage Execution

**Files:**
- Modify: `src/mcm_agent/core/workspace.py`
- Modify: `src/mcm_agent/core/stage_executor.py`
- Create: `src/mcm_agent/server/routes_events.py`
- Modify: `src/mcm_agent/server/app.py`
- Test: `tests/test_progress_events.py`

- [ ] **Step 1: Add failing progress event test**

Create `tests/test_progress_events.py`:

```python
import json

from mcm_agent.core.stage_executor import StageExecutor
from mcm_agent.core.workspace import create_workspace


def test_stage_executor_writes_progress_events(tmp_path) -> None:
    workspace = create_workspace(tmp_path / "task")
    executor = StageExecutor(
        workspace.root,
        handlers={"intake": lambda root: ["input_manifest.json"]},
    )

    executor.run_stage("intake")

    events = [
        json.loads(line)
        for line in (workspace.root / "progress_events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    statuses = [event["status"] for event in events]
    assert statuses == ["running", "passed"]
    assert events[0]["stage_id"] == "intake"
```

Add event route test:

```python
def test_events_api_reads_progress_events(tmp_path) -> None:
    from fastapi.testclient import TestClient
    from mcm_agent.server.app import create_app

    workspace = create_workspace(tmp_path / "workspaces" / "task_001")
    (workspace.root / "progress_events.jsonl").write_text(
        '{"event_id":"evt_001","timestamp":"2026-06-15T00:00:00Z","workspace_id":"task_001","stage_id":"intake","agent":"StageExecutor","level":"info","status":"running","message":"Starting intake.","artifact_paths":[]}\n',
        encoding="utf-8",
    )
    client = TestClient(create_app(workspace_base=tmp_path / "workspaces"))

    response = client.get("/api/workspaces/task_001/events")

    assert response.status_code == 200
    assert response.json()["events"][0]["event_id"] == "evt_001"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_progress_events.py -q
```

Expected: FAIL because progress events are not written and route does not exist.

- [ ] **Step 3: Implement progress events**

In `workspace.py`, add `progress_events.jsonl` to `EMPTY_TEXT_FILES`.

In `stage_executor.py`, add helper `_append_progress_event(stage_id, status, message, outputs=None, error=None)` that writes JSONL with:

- `event_id`
- `timestamp`
- `workspace_id`
- `stage_id`
- `agent="StageExecutor"`
- `level`
- `status`
- `message`
- `artifact_paths`

Call it:

- before handler: `running`
- after success: `passed`
- in exception path: `failed`

Create `routes_events.py`:

- GET `/api/workspaces/{workspace_id}/events`
- Optional `after` filters events after matching event id.

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/test_progress_events.py tests/test_stage_executor.py -q
ruff check src/mcm_agent/core/stage_executor.py src/mcm_agent/core/workspace.py src/mcm_agent/server tests/test_progress_events.py
```

Expected: PASS.

- [ ] **Step 5: Commit and push**

```bash
git add src/mcm_agent/core/stage_executor.py src/mcm_agent/core/workspace.py src/mcm_agent/server/routes_events.py src/mcm_agent/server/app.py tests/test_progress_events.py
git commit -m "feat: emit gui progress events"
git push origin main
```

## Task 6: Background Run, Resume, Stop API

**Files:**
- Create: `src/mcm_agent/server/background.py`
- Modify: `src/mcm_agent/server/routes_workspace.py`
- Modify: `src/mcm_agent/server/schemas.py`
- Test: `tests/test_server_workspace.py`

- [ ] **Step 1: Add failing background run test**

Append to `tests/test_server_workspace.py`:

```python
def test_workspace_api_starts_demo_run_in_background(tmp_path) -> None:
    client = TestClient(create_app(workspace_base=tmp_path / "workspaces"))
    client.post("/api/workspaces", json={"workspace_id": "demo"})

    response = client.post("/api/workspaces/demo/run", json={"mode": "demo", "auto_approve": True})

    assert response.status_code == 200
    body = response.json()
    assert body["workspace_id"] == "demo"
    assert body["status"] in {"queued", "running", "completed"}
    assert body["run_id"].startswith("run_")
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_server_workspace.py::test_workspace_api_starts_demo_run_in_background -q
```

Expected: FAIL because run endpoint/background runner does not exist.

- [ ] **Step 3: Implement background runner**

Create `background.py`:

- `RunStatus` model fields: `run_id`, `workspace_id`, `status`, `started_at`, `finished_at`, `error`.
- `BackgroundRunRegistry` with in-memory dict and `ThreadPoolExecutor`.
- `start_demo(workspace_root: Path, auto_approve: bool)`.
- `start_real(workspace_root: Path, task_input: TaskInput, config_path: Path, auto_approve: bool)`.
- `stop(run_id)` marks stop requested. First implementation may report unsupported cancellation for running sync workflows; endpoint still exists and records requested status.

Modify run endpoint:

- POST `/run` accepts:
  - `mode`: `"demo"` or `"real"`
  - `auto_approve`
  - for real mode: `problem_file`, `attachments`, `user_idea_file`, `template_dir`
- demo mode calls `run_demo_workflow`.
- real mode loads config, builds providers, calls `run_mvp_workflow`.
- returns current run status.

Add:

- POST `/resume`
- POST `/stop`

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/test_server_workspace.py -q
ruff check src/mcm_agent/server tests/test_server_workspace.py
```

Expected: PASS.

- [ ] **Step 5: Focused K verification**

Run:

```bash
pytest tests/test_server_config.py tests/test_server_workspace.py tests/test_progress_events.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit and push**

```bash
git add src/mcm_agent/server tests/test_server_workspace.py
git commit -m "feat: add gui background workflow runs"
git push origin main
```

## Task 7: K Documentation And Full Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/WORKFLOW.md`
- Modify: `docs/PROJECT_STATUS.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update docs**

Document:

- `mcm-agent gui`
- local API URL
- config API behavior and masked secrets
- per-provider connectivity test endpoint for GUI row buttons
- workspace upload/run/event/artifact APIs
- `progress_events.jsonl`
- K complete, L next

- [ ] **Step 2: Run focused verification**

Run:

```bash
pytest tests/test_server_config.py tests/test_server_workspace.py tests/test_progress_events.py tests/test_docs.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full verification**

Run:

```bash
pytest -q
ruff check src tests scripts
```

Expected: PASS.

- [ ] **Step 4: Commit and push docs**

```bash
git add README.md docs/WORKFLOW.md docs/PROJECT_STATUS.md docs/IMPLEMENTATION_PLAN.md docs/superpowers/plans/2026-06-15-gui-service-foundation.md
git commit -m "docs: describe gui service foundation"
git push origin main
```

## Self-Review

- Spec coverage: Covers K route plus the user's added requirement that each API row can test connectivity through `/api/config/test-provider`.
- Placeholder scan: No TBD/TODO placeholders are used as requirements.
- Type consistency: API names, file names, `progress_events.jsonl`, and run status names are consistent across tasks.
- Scope control: This route intentionally does not build the frontend. L will build the GUI buttons and pages on top of these APIs.
