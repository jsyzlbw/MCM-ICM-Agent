from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mcm_agent.server.routes_artifacts import create_artifact_router
from mcm_agent.server.routes_config import create_config_router
from mcm_agent.server.routes_workspace import create_workspace_router
from mcm_agent.server.routes_workflow import create_workflow_router
from mcm_agent.server.run_registry import RunRegistry

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    *,
    config_path: Path | None = None,
    workspace_base: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="MCM/ICM Agent GUI API")
    app.state.config_path = config_path or Path("mcm_agent_config.local.json")
    app.state.workspace_base = workspace_base or Path(".mcm_agent_workspaces")
    app.include_router(
        create_config_router(
            app.state.config_path,
            workspace_base=app.state.workspace_base,
        )
    )
    app.include_router(create_workspace_router(app.state.workspace_base))
    app.include_router(create_artifact_router(app.state.workspace_base))
    app.state.run_registry = RunRegistry()
    app.include_router(
        create_workflow_router(
            app.state.workspace_base,
            app.state.run_registry,
            app.state.config_path,
        )
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    return app
