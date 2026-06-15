from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from mcm_agent.server.routes_config import create_config_router


def create_app(
    *,
    config_path: Path | None = None,
    workspace_base: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="MCM/ICM Agent GUI API")
    app.state.config_path = config_path or Path("mcm_agent_config.local.json")
    app.state.workspace_base = workspace_base or Path(".mcm_agent_workspaces")
    app.include_router(create_config_router(app.state.config_path))

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
