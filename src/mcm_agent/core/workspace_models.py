from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class WorkspaceMetadata(BaseModel):
    schema_version: int = 1
    workspace_id: str
    created_at: datetime
    updated_at: datetime
    mag_version: str
    status: Literal["initialized", "init_incomplete", "init_complete"] = "initialized"


class WorkspaceInitState(BaseModel):
    completed: bool = False
    llm_configured: bool = False
    problem_imported: bool = False
    rag_documents: int = 0
    data_files: int = 0
    layout_imported: bool = False


class WorkspaceGitState(BaseModel):
    enabled: bool = True
    checkpoint: bool = True
    auto_push: bool = False
    remote: str = "origin"
    branch: str = "main"
    last_checkpoint: str | None = None
    last_push_error: str | None = None


class ImportedResource(BaseModel):
    resource_id: str
    resource_type: Literal["problem", "data", "layout", "rag"]
    source_path: str
    workspace_path: str
    created_at: datetime
    metadata: dict[str, str] = Field(default_factory=dict)


class WorkspaceState(BaseModel):
    init: WorkspaceInitState = Field(default_factory=WorkspaceInitState)
    phase: str = "initialized"
    problem: str | None = None
    last_stage: str | None = None
    blocked_reason: str | None = None
    resources: list[ImportedResource] = Field(default_factory=list)
    git: WorkspaceGitState = Field(default_factory=WorkspaceGitState)
