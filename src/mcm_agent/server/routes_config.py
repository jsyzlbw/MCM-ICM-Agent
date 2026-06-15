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
