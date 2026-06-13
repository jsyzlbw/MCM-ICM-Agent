from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ArtifactStatus(str, Enum):
    DRAFT = "draft"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    STALE = "stale"


class ArtifactRecord(BaseModel):
    artifact_id: str
    type: str
    path: str
    producer: str
    depends_on: list[str] = Field(default_factory=list)
    status: ArtifactStatus = ArtifactStatus.DRAFT
    created_at: datetime
    updated_at: datetime | None = None
    quality_checks: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskInput(BaseModel):
    problem_file: Path
    attachments: list[Path] = Field(default_factory=list)
    user_idea_file: Path | None = None
    template_dir: Path | None = None
    language: Literal["en", "zh"] = "en"
    competition: Literal["MCM", "ICM", "unknown"] = "unknown"


class HandoffPacket(BaseModel):
    handoff_id: str
    from_agent: str
    to_agent: str
    task: str
    input_artifacts: list[str]
    expected_outputs: list[str]
    acceptance_criteria: list[str]
    known_risks: list[str] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def require_acceptance_criteria(self) -> HandoffPacket:
        if not self.acceptance_criteria:
            raise ValueError("handoff packet requires at least one acceptance criterion")
        return self


class EventRecord(BaseModel):
    event_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    source: str


class CheckpointDecision(BaseModel):
    checkpoint_id: str
    status: Literal["pending", "approved", "rejected", "changes_requested"]
    user_message: str = ""
    approved_artifacts: list[str] = Field(default_factory=list)
    created_at: datetime


class SourceRecord(BaseModel):
    source_id: str
    title: str
    url: str
    accessed_at: datetime
    license: str
    provider: str
    source_rank: Literal["official", "academic", "reputable", "background_only", "rejected"]
    used_for: str
    citation: str
    local_path: str | None = None


class RetrievalLogEntry(BaseModel):
    time: datetime
    provider: str
    query: str | None = None
    url: str | None = None
    top_urls: list[str] = Field(default_factory=list)
    output: str | None = None
    decision: str

    @model_validator(mode="after")
    def require_query_or_url(self) -> RetrievalLogEntry:
        if not self.query and not self.url:
            raise ValueError("retrieval log entry requires query or url")
        return self


class EvidenceItem(BaseModel):
    evidence_id: str
    claim: str
    value: Any
    source_type: Literal[
        "problem_statement",
        "attachment",
        "external_data",
        "code_output",
        "user_confirmed",
    ]
    source_path: str
    generated_by: str
    used_in: list[str] = Field(default_factory=list)
    verified: bool = False
    lineage_ids: list[str] = Field(default_factory=list)


class DataLineageRecord(BaseModel):
    datum_id: str
    name: str
    value: Any
    unit: str
    entity: str
    time_period: str
    source_id: str
    source_url: str
    source_title: str
    accessed_at: datetime
    local_path: str
    extraction_method: str
    confidence: float = Field(ge=0, le=1)
    used_in: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_source_binding(self) -> DataLineageRecord:
        if not self.source_id.strip():
            raise ValueError("data lineage requires source_id")
        if not self.source_url.strip():
            raise ValueError("data lineage requires source_url")
        if not self.source_title.strip():
            raise ValueError("data lineage requires source_title")
        return self


class CitationCandidate(BaseModel):
    citation_id: str
    source_id: str
    title: str
    url: str
    accessed_at: datetime
    bibtex_key: str | None = None
    bibtex: str | None = None
    citation_note: str = ""

    @model_validator(mode="after")
    def fill_bibtex_fields(self) -> CitationCandidate:
        key = self.bibtex_key or self.source_id.replace("-", "_")
        year = str(self.accessed_at.year)
        bibtex = self.bibtex or "\n".join(
            [
                f"@misc{{{key},",
                f"  title = {{{self.title}}},",
                f"  url = {{{self.url}}},",
                f"  note = {{Accessed {self.accessed_at.date().isoformat()}}},",
                f"  year = {{{year}}}",
                "}",
            ]
        )
        self.bibtex_key = key
        self.bibtex = bibtex
        return self


class FigurePlanItem(BaseModel):
    figure_id: str
    purpose: str
    figure_type: Literal["data_plot", "concept_diagram", "ai_visual_draft"]
    source_data: list[str] = Field(default_factory=list)
    generation_script: str | None = None
    output_formats: list[Literal["pdf", "svg", "png"]]
    target_section: str
    caption_intent: str

    @model_validator(mode="after")
    def require_vector_output_for_data_plot(self) -> FigurePlanItem:
        if self.figure_type == "data_plot" and not {"pdf", "svg"}.intersection(
            self.output_formats
        ):
            raise ValueError("data_plot figures require pdf or svg output")
        return self


class FigureRecord(BaseModel):
    figure_id: str
    type: Literal["data_plot", "concept_diagram", "ai_visual_draft"]
    tool: str
    source_file: str
    outputs: list[str]
    used_in: list[str]
    status: ArtifactStatus


class HumanizerJob(BaseModel):
    job_id: str
    provider: Literal["ushallpass", "fake"]
    language: Literal["en", "zh"]
    endpoint: str
    input_hash: str
    status: Literal["submitted", "completed", "failed", "timeout", "skipped"]
    created_at: datetime
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class ReviewFinding(BaseModel):
    finding_id: str
    severity: Literal["critical", "major", "minor", "suggestion"]
    category: Literal[
        "fit",
        "model",
        "data",
        "evidence",
        "figure",
        "writing",
        "latex",
        "compliance",
    ]
    location: str
    issue: str
    recommendation: str
    blocks_submission: bool


class TaskState(BaseModel):
    workspace_id: str
    current_phase: str
    created_at: datetime
    updated_at: datetime
    checkpoints: list[CheckpointDecision] = Field(default_factory=list)
    unresolved_issue_count: int = 0
