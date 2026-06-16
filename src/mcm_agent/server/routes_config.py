from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter

from mcm_agent.config import load_settings
from mcm_agent.providers.smoke import ProviderSmokeTester
from mcm_agent.server.config_store import mask_config, merge_config, read_config, write_config
from mcm_agent.server.schemas import ProviderTestRequest


def create_config_router(config_path: Path, *, workspace_base: Path) -> APIRouter:
    router = APIRouter(prefix="/api/config", tags=["config"])

    @router.get("")
    def get_config() -> dict[str, Any]:
        return mask_config(read_config(config_path))

    @router.post("")
    def save_config(payload: dict[str, Any]) -> dict[str, Any]:
        merged = merge_config(read_config(config_path), payload)
        write_config(config_path, merged)
        return mask_config(merged)

    @router.post("/test-provider")
    def test_provider(request: ProviderTestRequest) -> dict[str, Any]:
        settings = load_settings(config_file=str(config_path))
        tester = ProviderSmokeTester(
            settings,
            workspace_root=workspace_base / ".smoke",
            mineru_file=Path(request.mineru_file) if request.mineru_file else None,
        )
        result = tester.check(request.provider)
        return result.model_dump(mode="json")

    return router
