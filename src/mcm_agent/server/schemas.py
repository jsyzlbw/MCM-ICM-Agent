from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class ProviderTestRequest(BaseModel):
    provider: str
    mineru_file: str | None = None
