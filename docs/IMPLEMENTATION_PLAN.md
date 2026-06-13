# MCM/ICM Math Modeling Agent MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` recommended, or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable MVP of the MCM/ICM math modeling agent that can create a task workspace, parse inputs, plan modeling routes, retrieve data, run code, generate vector-first figures, write and compile a LaTeX paper, humanize text with fact protection, review the draft, and iterate with user feedback.

**Architecture:** Use a Python package with a CLI-first workflow. The system is coordinated by an event-driven `Coordinator`, with every agent communicating through typed artifacts, JSON registries, and handoff packets stored in a task workspace. External services such as MinerU, Tavily, Firecrawl, UShallPass, and academic or official data APIs are accessed through provider adapters so tests can use deterministic fake providers.

**Tech Stack:** Python 3.12, Typer, Pydantic v2, httpx, tenacity, pandas, numpy, matplotlib, seaborn, scipy, scikit-learn, Jinja2, SQLite FTS5, pytest, respx, python-dotenv, latexmk, Mermaid CLI, Graphviz, optional MinerU CLI or REST API.

---

## 0. Implementation Scope

This plan implements the first production-shaped MVP, not a research prototype hidden in notebooks.

The MVP must support:

- English MCM/ICM paper workflow.
- PDF problem statement and CSV/XLSX attachments.
- Optional LaTeX template.
- Optional user idea file.
- API-based search with Tavily and Firecrawl as first-class providers.
- Official and academic data provider interfaces with at least one working public API example.
- MinerU document extraction adapter with local CLI, REST, and fake provider modes.
- UShallPass humanization adapter with fact lock and fact regression check.
- Supervisor-Skills methodology import as RAG documents and review checklists.
- Figure planning and vector-first figure generation.
- LaTeX PDF compilation.
- End-to-end dry run using fake providers.

The MVP does not include:

- A browser UI.
- Multi-user authentication.
- Hosted SaaS deployment.
- Guaranteed contest award prediction.
- Any claim that humanization can bypass AI detection.
- infmind as a final data figure generator.
- MCP as a core runtime dependency.

---

## 1. Target Repository Layout

All implementation files for this new agent live under:

`/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/`

Create this structure:

```text
MathModelAgentDesign/
├── DESIGN.md
├── IMPLEMENTATION_PLAN.md
└── reference_implementation/
    ├── README.md
    ├── pyproject.toml
    ├── .env.example
    ├── src/
    │   └── mcm_agent/
    │       ├── __init__.py
    │       ├── cli.py
    │       ├── config.py
    │       ├── core/
    │       │   ├── __init__.py
    │       │   ├── models.py
    │       │   ├── workspace.py
    │       │   ├── registry.py
    │       │   ├── events.py
    │       │   ├── handoff.py
    │       │   └── coordinator.py
    │       ├── providers/
    │       │   ├── __init__.py
    │       │   ├── base.py
    │       │   ├── llm.py
    │       │   ├── mineru.py
    │       │   ├── search.py
    │       │   ├── data_apis.py
    │       │   ├── academic.py
    │       │   ├── humanizer.py
    │       │   └── latex.py
    │       ├── agents/
    │       │   ├── __init__.py
    │       │   ├── intake.py
    │       │   ├── extraction.py
    │       │   ├── problem_understanding.py
    │       │   ├── discussion.py
    │       │   ├── modeling.py
    │       │   ├── search_data.py
    │       │   ├── rag.py
    │       │   ├── eda.py
    │       │   ├── solver.py
    │       │   ├── validation.py
    │       │   ├── visualization.py
    │       │   ├── writer.py
    │       │   ├── compliance.py
    │       │   ├── reviewer.py
    │       │   └── revision.py
    │       ├── workflows/
    │       │   ├── __init__.py
    │       │   ├── mvp.py
    │       │   └── demo_fixtures.py
    │       ├── templates/
    │       │   ├── paper/
    │       │   │   ├── main.tex.j2
    │       │   │   ├── references.bib.j2
    │       │   │   └── sections/
    │       │   │       ├── abstract.tex.j2
    │       │   │       ├── introduction.tex.j2
    │       │   │       ├── assumptions.tex.j2
    │       │   │       ├── model.tex.j2
    │       │   │       ├── results.tex.j2
    │       │   │       ├── sensitivity.tex.j2
    │       │   │       └── conclusion.tex.j2
    │       │   └── prompts/
    │       │       ├── problem_understanding.md
    │       │       ├── model_candidates.md
    │       │       ├── model_judge.md
    │       │       ├── paper_writer.md
    │       │       └── reviewer.md
    │       └── utils/
    │           ├── __init__.py
    │           ├── json_io.py
    │           ├── markdown.py
    │           ├── text_locks.py
    │           └── subprocesses.py
    ├── tests/
    │   ├── conftest.py
    │   ├── fixtures/
    │   │   ├── sample_problem.md
    │   │   ├── sample_attachment.csv
    │   │   ├── supervisor_skill_excerpt.md
    │   │   └── sample_template.tex
    │   ├── test_core_models.py
    │   ├── test_workspace_registry.py
    │   ├── test_coordinator.py
    │   ├── test_mineru_provider.py
    │   ├── test_search_data.py
    │   ├── test_rag.py
    │   ├── test_humanizer.py
    │   ├── test_visualization.py
    │   ├── test_latex.py
    │   └── test_mvp_workflow.py
    └── examples/
        └── demo_task/
            ├── input/
            │   ├── problem.md
            │   ├── attachments/
            │   │   └── sample_attachment.csv
            │   └── user_idea.md
            └── expected_outputs.md
```

---

## 2. Configuration Contract

Create `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/.env.example`:

```bash
# LLM provider
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=gpt-4.1

# Search providers
TAVILY_API_KEY=
FIRECRAWL_API_KEY=
BRAVE_SEARCH_API_KEY=
EXA_API_KEY=

# Humanization provider
HUMANIZER_API_KEY=
HUMANIZER_API_BASE_URL=https://leahloveswriting.xyz

# MinerU provider
MINERU_MODE=fake
MINERU_CLI=mineru
MINERU_API_BASE_URL=
MINERU_API_KEY=

# Runtime
MCM_AGENT_DEFAULT_LANGUAGE=en
MCM_AGENT_MAX_RETRIES=2
MCM_AGENT_HTTP_TIMEOUT_SECONDS=60
MCM_AGENT_CODE_TIMEOUT_SECONDS=120
```

Rules:

- Missing optional provider keys must not crash CLI startup.
- Missing keys must fail only when the matching provider is invoked.
- `MINERU_MODE=fake` must work without network and without MinerU installed.
- UShallPass defaults to English endpoint for MCM/ICM.

---

## 3. Core Runtime Data Contracts

These types are the backbone of the system. Implement them first and keep names stable.

### 3.1 Required Pydantic Models

Create `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/core/models.py` with these models:

```python
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
    def require_acceptance_criteria(self) -> "HandoffPacket":
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
    def require_query_or_url(self) -> "RetrievalLogEntry":
        if not self.query and not self.url:
            raise ValueError("retrieval log entry requires query or url")
        return self


class EvidenceItem(BaseModel):
    evidence_id: str
    claim: str
    value: Any
    source_type: Literal["problem_statement", "attachment", "external_data", "code_output", "user_confirmed"]
    source_path: str
    generated_by: str
    used_in: list[str] = Field(default_factory=list)
    verified: bool = False


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
    def require_vector_output_for_data_plot(self) -> "FigurePlanItem":
        if self.figure_type == "data_plot" and not {"pdf", "svg"}.intersection(self.output_formats):
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
    category: Literal["fit", "model", "data", "evidence", "figure", "writing", "latex", "compliance"]
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
```

Validation rules:

- A `HandoffPacket` is valid only if it has at least one acceptance criterion.
- A `RetrievalLogEntry` is valid only if at least one of `query` or `url` is present.
- A `FigurePlanItem` with `figure_type="data_plot"` is valid only if it includes PDF or SVG output.

---

## 4. Implementation Milestones

### Milestone M0: Project Scaffolding

Outcome: package installs in editable mode, CLI responds, tests run.

### Milestone M1: Core Workspace, Registry, Events

Outcome: the system can create a complete task workspace and record artifacts, events, handoff packets, sources, evidence, and figures.

### Milestone M2: Input and MinerU Extraction

Outcome: user inputs are normalized and parsed into `parsed/` with an extraction quality report.

### Milestone M3: Planning Agents

Outcome: problem understanding, user direction, model candidates, model decision, and experiment plan are generated as reviewable artifacts.

### Milestone M4: Retrieval and Methodology RAG

Outcome: Tavily/Firecrawl provider adapters, official data API adapter, academic API adapter, source registry, retrieval log, and Supervisor-Skills RAG are working.

### Milestone M5: Data, Code, Evidence, Validation

Outcome: EDA, solver code execution, evidence registry, validation report, sensitivity outputs, and robustness outputs are produced.

### Milestone M6: Figures and Paper

Outcome: figure plan, vector-first figure registry, LaTeX source, and draft PDF are produced.

### Milestone M7: Humanization, Review, Revision

Outcome: UShallPass adapter, fact regression, automatic reviewer, methodology checklist report, and revision loop are working.

### Milestone M8: End-to-End Demo

Outcome: a fake-provider dry run creates the full workspace tree and all required MVP artifacts.

---

## 5. Task Plan

### Task 1: Scaffold Python Package

**Files:**

- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/pyproject.toml`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/README.md`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/.env.example`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/__init__.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/cli.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/tests/conftest.py`

- [ ] **Step 1: Write `pyproject.toml`**

Use this content:

```toml
[project]
name = "mcm-agent"
version = "0.1.0"
description = "MCM/ICM math modeling agent MVP"
requires-python = ">=3.12"
dependencies = [
  "typer>=0.12.5",
  "rich>=13.7.1",
  "pydantic>=2.8.2",
  "pydantic-settings>=2.4.0",
  "python-dotenv>=1.0.1",
  "httpx>=0.27.2",
  "tenacity>=8.5.0",
  "pandas>=2.2.2",
  "numpy>=2.0.1",
  "openpyxl>=3.1.5",
  "matplotlib>=3.9.1",
  "seaborn>=0.13.2",
  "scipy>=1.14.0",
  "scikit-learn>=1.5.1",
  "jinja2>=3.1.4",
  "pyyaml>=6.0.2"
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3.2",
  "pytest-cov>=5.0.0",
  "respx>=0.21.1",
  "freezegun>=1.5.1",
  "ruff>=0.5.7"
]
geo = [
  "geopandas>=1.0.1",
  "cartopy>=0.23.0"
]

[project.scripts]
mcm-agent = "mcm_agent.cli:app"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py312"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Write the initial CLI**

Create `src/mcm_agent/cli.py`:

```python
from __future__ import annotations

import typer

app = typer.Typer(help="MCM/ICM math modeling agent CLI.")


@app.command()
def version() -> None:
    """Print package version."""
    typer.echo("mcm-agent 0.1.0")
```

- [ ] **Step 3: Run the CLI smoke test**

Run:

```bash
cd /Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation
python -m pip install -e ".[dev]"
mcm-agent version
```

Expected:

```text
mcm-agent 0.1.0
```

- [ ] **Step 4: Commit scaffold**

Run:

```bash
git add MathModelAgentDesign/reference_implementation
git commit -m "feat: scaffold mcm agent package"
```

### Task 2: Implement Core Models

**Files:**

- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/core/models.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/core/__init__.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/tests/test_core_models.py`

- [ ] **Step 1: Write tests for required schemas**

Create `tests/test_core_models.py`:

```python
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from mcm_agent.core.models import (
    ArtifactRecord,
    ArtifactStatus,
    EvidenceItem,
    FigurePlanItem,
    HandoffPacket,
    RetrievalLogEntry,
    TaskInput,
)


NOW = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)


def test_artifact_record_accepts_dependencies() -> None:
    record = ArtifactRecord(
        artifact_id="problem_understanding_v1",
        type="problem_understanding_report",
        path="reports/problem_understanding.md",
        producer="ProblemUnderstandingAgent",
        depends_on=["parsed_problem_v1"],
        status=ArtifactStatus.REVIEW_REQUIRED,
        created_at=NOW,
    )

    assert record.depends_on == ["parsed_problem_v1"]
    assert record.status == ArtifactStatus.REVIEW_REQUIRED


def test_task_input_defaults_to_english_unknown_competition(tmp_path: Path) -> None:
    task_input = TaskInput(problem_file=tmp_path / "problem.pdf")

    assert task_input.language == "en"
    assert task_input.competition == "unknown"
    assert task_input.attachments == []


def test_handoff_packet_requires_acceptance_criteria() -> None:
    with pytest.raises(ValidationError):
        HandoffPacket(
            handoff_id="handoff_001",
            from_agent="ModelJudge",
            to_agent="SolverCoderAgent",
            task="implement_problem_1",
            input_artifacts=["reports/model_decision.md"],
            expected_outputs=["code/problem1.py"],
            acceptance_criteria=[],
            created_at=NOW,
        )


def test_retrieval_log_requires_query_or_url() -> None:
    with pytest.raises(ValidationError):
        RetrievalLogEntry(
            time=NOW,
            provider="tavily",
            decision="missing query and url",
        )


def test_evidence_item_records_verified_code_output() -> None:
    item = EvidenceItem(
        evidence_id="q1_rmse_001",
        claim="The model achieves RMSE = 2.31.",
        value=2.31,
        source_type="code_output",
        source_path="results/problem1_metrics.json",
        generated_by="code/problem1.py",
        used_in=["paper/sections/results.tex"],
        verified=True,
    )

    assert item.verified is True


def test_figure_plan_item_rejects_raster_only_data_plot() -> None:
    with pytest.raises(ValidationError):
        FigurePlanItem(
            figure_id="fig_q1_prediction",
            purpose="show prediction performance",
            figure_type="data_plot",
            source_data=["results/problem1_predictions.csv"],
            generation_script="code/plot_problem1.py",
            output_formats=["png"],
            target_section="paper/sections/results.tex",
            caption_intent="Prediction performance comparison.",
        )
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/test_core_models.py -v
```

Expected:

```text
FAILED tests/test_core_models.py
```

because `mcm_agent.core.models` does not exist yet.

- [ ] **Step 3: Implement models**

Use the complete model definitions from section 3.1. Confirm the following validators are present in the matching classes:

```python
@model_validator(mode="after")
def require_acceptance_criteria(self) -> "HandoffPacket":
    if not self.acceptance_criteria:
        raise ValueError("handoff packet requires at least one acceptance criterion")
    return self


@model_validator(mode="after")
def require_query_or_url(self) -> "RetrievalLogEntry":
    if not self.query and not self.url:
        raise ValueError("retrieval log entry requires query or url")
    return self


@model_validator(mode="after")
def require_vector_output_for_data_plot(self) -> "FigurePlanItem":
    if self.figure_type == "data_plot" and not {"pdf", "svg"}.intersection(self.output_formats):
        raise ValueError("data_plot figures require pdf or svg output")
    return self
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
pytest tests/test_core_models.py -v
```

Expected:

```text
6 passed
```

- [ ] **Step 5: Commit core models**

Run:

```bash
git add MathModelAgentDesign/reference_implementation/src/mcm_agent/core MathModelAgentDesign/reference_implementation/tests/test_core_models.py
git commit -m "feat: add core runtime schemas"
```

### Task 3: Implement Workspace Creation and Registries

**Files:**

- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/core/workspace.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/core/registry.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/core/events.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/utils/json_io.py`
- Modify: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/cli.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/tests/test_workspace_registry.py`

- [ ] **Step 1: Write failing tests for workspace tree**

Test must verify these files are created:

```text
task_state.json
artifact_registry.json
event_log.jsonl
unresolved_issues.md
data/source_registry.json
data/retrieval_log.jsonl
results/evidence_registry.json
figures/figure_plan.json
figures/figure_registry.json
review/methodology_checklist_report.md
review/humanization_diff.md
review/fact_regression_report.md
```

Use this test:

```python
from pathlib import Path

from mcm_agent.core.workspace import create_workspace


def test_create_workspace_initializes_required_files(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")

    required = [
        "task_state.json",
        "artifact_registry.json",
        "event_log.jsonl",
        "unresolved_issues.md",
        "data/source_registry.json",
        "data/retrieval_log.jsonl",
        "results/evidence_registry.json",
        "figures/figure_plan.json",
        "figures/figure_registry.json",
        "review/methodology_checklist_report.md",
        "review/humanization_diff.md",
        "review/fact_regression_report.md",
    ]

    for relative_path in required:
        assert (workspace.root / relative_path).exists(), relative_path
```

- [ ] **Step 2: Implement JSON IO**

Create `utils/json_io.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
```

- [ ] **Step 3: Implement workspace creator**

`create_workspace(root: Path)` must create every directory shown in section 1 and initialize JSON files with deterministic empty structures:

```json
[]
```

for registries that are lists, and:

```json
{"workspace_id":"run_001","current_phase":"initialized","checkpoints":[],"unresolved_issue_count":0}
```

for `task_state.json`, with real timestamps added by the implementation.

- [ ] **Step 4: Implement registry operations**

Create an `ArtifactRegistry` class with these public methods:

- `__init__(self, path: Path) -> None`
- `list(self) -> list[ArtifactRecord]`
- `get(self, artifact_id: str) -> ArtifactRecord`
- `add(self, record: ArtifactRecord) -> None`
- `update_status(self, artifact_id: str, status: ArtifactStatus) -> None`
- `dependents_of(self, artifact_id: str) -> list[ArtifactRecord]`
- `mark_dependents_stale(self, artifact_id: str) -> list[str]`

If `add` receives an existing `artifact_id`, raise `ValueError("artifact already exists: <artifact_id>")`.

- [ ] **Step 5: Implement event log**

Create an `EventLog` class with these public methods:

- `__init__(self, path: Path) -> None`
- `append(self, event: EventRecord) -> None`
- `read_all(self) -> list[EventRecord]`

`read_all` must ignore blank lines and raise `ValueError` with the line number if a JSONL line is invalid.

- [ ] **Step 6: Add CLI command**

Add:

```bash
mcm-agent init-workspace /absolute/path/to/workspace
```

Expected output:

```text
Workspace initialized: /absolute/path/to/workspace
```

- [ ] **Step 7: Run tests**

Run:

```bash
pytest tests/test_workspace_registry.py -v
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit workspace and registries**

Run:

```bash
git add MathModelAgentDesign/reference_implementation/src/mcm_agent MathModelAgentDesign/reference_implementation/tests/test_workspace_registry.py
git commit -m "feat: add workspace and registry runtime"
```

### Task 4: Implement Coordinator and Handoff Packets

**Files:**

- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/core/handoff.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/core/coordinator.py`
- Modify: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/cli.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/tests/test_coordinator.py`

- [ ] **Step 1: Write tests for event transition**

The test must verify:

- `input.received` moves phase to `input_received`.
- `document.parsed` moves phase to `document_parsed`.
- `problem.understanding.ready` creates a pending checkpoint.
- Approval of the checkpoint marks listed artifacts as `approved`.

- [ ] **Step 2: Implement coordinator transition table**

Use this exact phase map:

```python
EVENT_PHASES = {
    "input.received": "input_received",
    "document.parsed": "document_parsed",
    "problem.understanding.ready": "awaiting_problem_understanding_approval",
    "user.direction.confirmed": "direction_confirmed",
    "model.candidates.ready": "model_candidates_ready",
    "model.decision.ready": "awaiting_model_decision_approval",
    "model.decision.approved": "model_decision_approved",
    "data.ready": "data_ready",
    "code.completed": "code_completed",
    "validation.failed": "validation_failed",
    "validation.passed": "validation_passed",
    "figures.ready": "figures_ready",
    "paper.draft.ready": "awaiting_draft_review",
    "paper.review.failed": "paper_review_failed",
    "paper.review.passed": "paper_review_passed",
    "user.revision.requested": "revision_requested",
    "submission.ready": "submission_ready",
}
```

- [ ] **Step 3: Implement checkpoint creation**

Create checkpoints for:

```text
problem.understanding.ready
model.decision.ready
paper.draft.ready
submission.ready
```

Each checkpoint must include the event payload key `artifact_ids`.

- [ ] **Step 4: Add CLI commands**

Add:

```bash
mcm-agent status /absolute/path/to/workspace
mcm-agent emit /absolute/path/to/workspace input.received
mcm-agent approve-checkpoint /absolute/path/to/workspace <checkpoint_id>
```

`status` prints:

```text
Phase: <current_phase>
Unresolved issues: <count>
Pending checkpoints: <count>
```

- [ ] **Step 5: Run coordinator tests**

Run:

```bash
pytest tests/test_coordinator.py -v
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit coordinator**

Run:

```bash
git add MathModelAgentDesign/reference_implementation/src/mcm_agent/core MathModelAgentDesign/reference_implementation/src/mcm_agent/cli.py MathModelAgentDesign/reference_implementation/tests/test_coordinator.py
git commit -m "feat: add workflow coordinator"
```

### Task 5: Implement Provider Interfaces

**Files:**

- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/providers/base.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/providers/llm.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/config.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/tests/test_provider_interfaces.py`

- [ ] **Step 1: Define provider result types**

Create:

```python
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderResult:
    content: str
    metadata: dict[str, object]


class TextGenerationProvider(Protocol):
    def generate(self, system: str, prompt: str, *, temperature: float = 0.2) -> ProviderResult:
        raise NotImplementedError


@dataclass(frozen=True)
class ProviderBundle:
    llm: TextGenerationProvider
    mineru: object
    search: object
    extractor: object
    humanizer: object
    latex: object
```

- [ ] **Step 2: Implement fake LLM provider**

`FakeLLMProvider` returns deterministic content from a dictionary keyed by prompt name:

```python
class FakeLLMProvider:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses

    def generate(self, system: str, prompt: str, *, temperature: float = 0.2) -> ProviderResult:
        key = prompt.splitlines()[0].strip() if prompt.strip() else "default"
        return ProviderResult(content=self.responses.get(key, self.responses.get("default", "")), metadata={"fake": True})
```

- [ ] **Step 3: Implement settings**

Use `pydantic-settings` to load `.env` fields from section 2. Expose:

```python
def load_settings(env_file: str | None = None) -> Settings:
    return Settings(_env_file=env_file)
```

- [ ] **Step 4: Test fake provider and settings**

Run:

```bash
pytest tests/test_provider_interfaces.py -v
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit provider base**

Run:

```bash
git add MathModelAgentDesign/reference_implementation/src/mcm_agent/providers MathModelAgentDesign/reference_implementation/src/mcm_agent/config.py MathModelAgentDesign/reference_implementation/tests/test_provider_interfaces.py
git commit -m "feat: add provider interfaces"
```

### Task 6: Implement Intake and MinerU Extraction

**Files:**

- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/providers/mineru.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/intake.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/extraction.py`
- Modify: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/cli.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/tests/test_mineru_provider.py`

- [ ] **Step 1: Define MinerU provider contract**

`MinerUProvider.parse_document(input_path: Path, output_dir: Path) -> ParsedDocument`

`ParsedDocument` fields:

```python
class ParsedDocument(BaseModel):
    markdown_path: str
    json_path: str
    layout_path: str | None = None
    table_paths: list[str] = []
    image_paths: list[str] = []
    formula_path: str | None = None
    page_count: int | None = None
    warnings: list[str] = []
```

- [ ] **Step 2: Implement fake MinerU provider**

Fake provider reads `.md` files directly and writes:

```text
parsed/problem.md
parsed/problem.json
parsed/problem_layout.json
parsed/formulas.json
```

For `.pdf`, fake provider writes a Markdown file containing:

```markdown
# Parsed Problem

Fake MinerU output for <filename>.
```

- [ ] **Step 3: Implement local CLI provider**

`LocalMinerUProvider` must run:

```bash
$MINERU_CLI -p <input_path> -o <output_dir>
```

Capture stdout and stderr into `parsed/mineru_cli.log`. If the command exits non-zero, raise `RuntimeError` with the exit code and log path.

- [ ] **Step 4: Implement REST provider**

`RestMinerUProvider` must:

- POST the file to `$MINERU_API_BASE_URL/parse`.
- Send `Authorization: Bearer $MINERU_API_KEY` only when the key is non-empty.
- Save returned Markdown and JSON into `parsed/`.
- Raise `RuntimeError("MinerU REST parse failed: <status_code>")` for non-2xx responses.

- [ ] **Step 5: Implement Intake Agent**

`IntakeAgent.run(workspace_root: Path, problem_file: Path, attachments: list[Path], user_idea: Path | None, template_dir: Path | None)` must:

- Copy the problem file to `input/problem.<ext>`.
- Copy attachments to `input/attachments/`.
- Copy template files to `input/template/`.
- Copy user idea to `input/user_idea.md`.
- Write `input_manifest.json`.
- Write `reports/attachment_inventory.md`.
- Emit `input.received`.

- [ ] **Step 6: Implement Extraction Agent**

`DocumentExtractionAgent.run(workspace_root: Path)` must:

- Parse `input/problem.*`.
- Save outputs in `parsed/`.
- Write `reports/extraction_quality_report.md` with page count, warning count, extracted table count, extracted image count, formula count, and parser mode.
- Register artifact `parsed_problem_v1`.
- Emit `document.parsed`.

- [ ] **Step 7: Run extraction tests**

Run:

```bash
pytest tests/test_mineru_provider.py -v
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit intake and extraction**

Run:

```bash
git add MathModelAgentDesign/reference_implementation/src/mcm_agent MathModelAgentDesign/reference_implementation/tests/test_mineru_provider.py
git commit -m "feat: add intake and mineru extraction"
```

### Task 7: Implement Problem Understanding and User Direction

**Files:**

- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/problem_understanding.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/discussion.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/templates/prompts/problem_understanding.md`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/tests/test_problem_understanding.py`

- [ ] **Step 1: Write prompt template**

The prompt must require these exact headings:

```markdown
# 题意理解报告

## 题目背景
## 子问题拆解
## 输入与输出
## 约束条件
## 评价指标
## 模糊表述与歧义
## 隐含条件
## 初步建模方向
## 需要用户确认的问题
```

- [ ] **Step 2: Implement ProblemUnderstandingAgent**

Inputs:

- `parsed/problem.md`
- `input_manifest.json`
- `reports/attachment_inventory.md`

Outputs:

- `reports/problem_understanding.md`
- artifact `problem_understanding_v1` with status `review_required`
- event `problem.understanding.ready` with `artifact_ids=["problem_understanding_v1"]`

Acceptance:

- If any required heading is missing, raise `ValueError("problem understanding report missing heading: <heading>")`.

- [ ] **Step 3: Implement UserDiscussionAgent**

`UserDiscussionAgent.confirm_direction(workspace_root: Path, mode: str, user_idea_summary: str, selected_route: str, paper_outline: str, decisions_to_preserve: list[str])` must write:

```markdown
# Confirmed Direction

## User Mode
## User Idea Summary
## Selected Modeling Route
## Paper Outline
## Decisions To Preserve
```

Outputs:

- `discussion/user_brief.md`
- `discussion/confirmed_direction.md`
- artifact `confirmed_direction_v1`
- event `user.direction.confirmed`

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/test_problem_understanding.py -v
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit planning checkpoint agents**

Run:

```bash
git add MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/problem_understanding.py MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/discussion.py MathModelAgentDesign/reference_implementation/src/mcm_agent/templates/prompts/problem_understanding.md MathModelAgentDesign/reference_implementation/tests/test_problem_understanding.py
git commit -m "feat: add problem understanding checkpoint"
```

### Task 8: Implement Modeling Council and Model Judge

**Files:**

- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/modeling.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/templates/prompts/model_candidates.md`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/templates/prompts/model_judge.md`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/tests/test_modeling.py`

- [ ] **Step 1: Define council roles**

Use exactly four role IDs:

```python
COUNCIL_ROLES = [
    "simple_interpretable_modeler",
    "high_accuracy_modeler",
    "optimization_modeler",
    "judge_perspective_modeler",
]
```

- [ ] **Step 2: Implement candidate generation**

`ModelingCouncil.run(workspace_root: Path, problem_report_path: Path, confirmed_direction_path: Path)` writes `reports/model_candidates.md` with sections:

```markdown
# Model Candidates

## Candidate Summary Table
## simple_interpretable_modeler
## high_accuracy_modeler
## optimization_modeler
## judge_perspective_modeler
## Cross-Candidate Risks
```

- [ ] **Step 3: Implement model judge scoring**

`ModelJudge.run(workspace_root: Path, candidates_path: Path)` scores each candidate on:

- problem fit
- data feasibility
- explainability
- implementation risk
- paper quality potential

The selected route must be the highest weighted score using:

```python
WEIGHTS = {
    "problem_fit": 0.30,
    "data_feasibility": 0.25,
    "explainability": 0.20,
    "implementation_risk": 0.15,
    "paper_quality_potential": 0.10,
}
```

- [ ] **Step 4: Generate model decision and experiment plan**

Write:

- `reports/model_decision.md`
- `reports/experiment_plan.md`

`model_decision.md` must include:

```markdown
# Model Decision

## Selected Route
## Rejected Alternatives
## Mathematical Formulation
## Objective Functions
## Constraints
## Data Requirements
## Figure Requirements
## Sensitivity Analysis Plan
```

`experiment_plan.md` must include:

```markdown
# Experiment Plan

## Required Datasets
## Preprocessing Steps
## Problem 1 Experiments
## Problem 2 Experiments
## Problem 3 Experiments
## Metrics
## Expected Code Outputs
```

- [ ] **Step 5: Emit model checkpoint**

Register:

- `model_candidates_v1`
- `model_decision_v1`
- `experiment_plan_v1`

Emit:

```text
model.candidates.ready
model.decision.ready
```

- [ ] **Step 6: Run modeling tests**

Run:

```bash
pytest tests/test_modeling.py -v
```

Expected:

```text
passed
```

- [ ] **Step 7: Commit modeling agents**

Run:

```bash
git add MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/modeling.py MathModelAgentDesign/reference_implementation/src/mcm_agent/templates/prompts/model_candidates.md MathModelAgentDesign/reference_implementation/src/mcm_agent/templates/prompts/model_judge.md MathModelAgentDesign/reference_implementation/tests/test_modeling.py
git commit -m "feat: add modeling council and judge"
```

### Task 9: Implement Search and External Data Governance

**Files:**

- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/providers/search.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/providers/data_apis.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/providers/academic.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/search_data.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/tests/test_search_data.py`

- [ ] **Step 1: Implement provider interfaces**

Create:

```python
class SearchProvider(Protocol):
    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        raise NotImplementedError


class ExtractProvider(Protocol):
    def extract(self, url: str) -> ExtractedPage:
        raise NotImplementedError
```

Models:

```python
class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    score: float | None = None


class ExtractedPage(BaseModel):
    url: str
    title: str
    markdown: str
    metadata: dict[str, object] = {}
```

- [ ] **Step 2: Implement Tavily provider**

Use:

```text
POST https://api.tavily.com/search
```

Request body:

```json
{"api_key":"<key>","query":"<query>","max_results":5,"include_answer":false}
```

On non-2xx, raise:

```python
RuntimeError(f"Tavily search failed: {response.status_code}")
```

- [ ] **Step 3: Implement Firecrawl provider**

Use:

```text
POST https://api.firecrawl.dev/v1/scrape
```

Headers:

```text
Authorization: Bearer <FIRECRAWL_API_KEY>
Content-Type: application/json
```

Request body:

```json
{"url":"<url>","formats":["markdown"]}
```

Store Markdown in `data/external/source_<n>.md`.

- [ ] **Step 4: Implement official data API example**

Implement `WorldBankProvider.fetch_indicator(country: str, indicator: str)`.

Use URL:

```text
https://api.worldbank.org/v2/country/{country}/indicator/{indicator}?format=json
```

Save raw JSON to:

```text
data/raw/worldbank_<country>_<indicator>.json
```

Register source with `source_rank="official"`.

- [ ] **Step 5: Implement academic API example**

Implement `OpenAlexProvider.search_works(query: str, max_results: int)`.

Use URL:

```text
https://api.openalex.org/works?search=<query>&per-page=<max_results>
```

Register source with `source_rank="academic"` for accepted works.

- [ ] **Step 6: Implement SearchDataAgent**

The agent must:

- Read `reports/experiment_plan.md`.
- Create `data/retrieval_log.jsonl` entries for each query and extraction.
- Write accepted sources to `data/source_registry.json`.
- Write `data/external_data_notes.md`.
- Reject sources with no URL, no title, or no provider.
- Mark general web pages as `background_only` unless configured as official or academic.

- [ ] **Step 7: Run provider tests with `respx`**

Run:

```bash
pytest tests/test_search_data.py -v
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit retrieval layer**

Run:

```bash
git add MathModelAgentDesign/reference_implementation/src/mcm_agent/providers/search.py MathModelAgentDesign/reference_implementation/src/mcm_agent/providers/data_apis.py MathModelAgentDesign/reference_implementation/src/mcm_agent/providers/academic.py MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/search_data.py MathModelAgentDesign/reference_implementation/tests/test_search_data.py
git commit -m "feat: add search and data governance"
```

### Task 10: Implement Supervisor-Skills Methodology RAG

**Files:**

- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/rag.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/tests/test_rag.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/tests/fixtures/supervisor_skill_excerpt.md`

- [ ] **Step 1: Implement local SQLite FTS store**

Create `MethodologyHit`:

```python
class MethodologyHit(BaseModel):
    source: str
    title: str
    content: str
    rank: int
```

Create `MethodologyStore` with these public methods:

- `__init__(self, db_path: Path) -> None`
- `initialize(self) -> None`
- `add_document(self, source: str, title: str, content: str) -> None`
- `search(self, query: str, limit: int = 5) -> list[MethodologyHit]`

Use SQLite FTS5 table:

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS methodology_docs
USING fts5(source, title, content);
```

- [ ] **Step 2: Implement Supervisor-Skills importer**

`import_supervisor_skills(source_dir: Path, store: MethodologyStore)` must ingest only files matching:

```text
**/idea-evaluator*/SKILL.md
**/figure-designer*/SKILL.md
**/pre-submission-reviewer*/SKILL.md
**/intro-drafter*/SKILL.md
**/tech-paper-template*/SKILL.md
```

For missing files, write a warning to `rag/retrieval_notes.md` and continue.

- [ ] **Step 3: Generate review checklists**

`MethodologyRAGAgent.run(workspace_root: Path, supervisor_skills_dir: Path | None)` must write:

- `rag/methodology_hits.json`
- `rag/retrieval_notes.md`
- `rag/review_checklists/modeling_checklist.md`
- `rag/review_checklists/figure_checklist.md`
- `rag/review_checklists/pre_submission_checklist.md`

- [ ] **Step 4: Write test for checklist generation**

Test must assert:

- `methodology_hits.json` contains at least one hit for "figure design".
- `pre_submission_checklist.md` contains "macro logic".
- `figure_checklist.md` contains "data source".

- [ ] **Step 5: Run RAG tests**

Run:

```bash
pytest tests/test_rag.py -v
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit methodology RAG**

Run:

```bash
git add MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/rag.py MathModelAgentDesign/reference_implementation/tests/test_rag.py MathModelAgentDesign/reference_implementation/tests/fixtures/supervisor_skill_excerpt.md
git commit -m "feat: add methodology rag"
```

### Task 11: Implement Data/EDA, Solver Execution, and Evidence Registry

**Files:**

- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/eda.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/solver.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/utils/subprocesses.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/tests/test_solver_evidence.py`

- [ ] **Step 1: Implement EDA agent**

`DataEDAAgent.run(workspace_root: Path)` must:

- Read CSV/XLSX files from `input/attachments/` and `data/external/`.
- Save cleaned CSV files to `data/processed/`.
- Write `reports/data_profile.md`.
- Write `results/eda_summary.json`.
- Register evidence items for row counts, column counts, missing values, and summary statistics.

- [ ] **Step 2: Implement subprocess runner**

Create:

```python
class CommandResult(BaseModel):
    command: list[str]
    return_code: int
    stdout: str
    stderr: str
    duration_seconds: float


def run_command(command: list[str], cwd: Path, timeout_seconds: int) -> CommandResult:
    """Run a subprocess with timeout and captured output."""
```

If timeout occurs, kill the process and return `return_code=-1` with stderr containing `"timeout"`.

- [ ] **Step 3: Implement SolverCoderAgent**

For MVP, generate a deterministic baseline solver when no generated code is available:

- For prediction tasks: linear regression baseline.
- For evaluation tasks: normalized weighted score baseline.
- For optimization tasks: scipy minimize baseline.

The agent must write:

- `code/problem1.py`
- `results/problem1_results.csv`
- `results/model_metrics.json`
- `results/run_log.md`

Every metric in `model_metrics.json` must be added to `results/evidence_registry.json`.

- [ ] **Step 4: Run solver tests**

Run:

```bash
pytest tests/test_solver_evidence.py -v
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit solver and evidence**

Run:

```bash
git add MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/eda.py MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/solver.py MathModelAgentDesign/reference_implementation/src/mcm_agent/utils/subprocesses.py MathModelAgentDesign/reference_implementation/tests/test_solver_evidence.py
git commit -m "feat: add eda solver and evidence registry"
```

### Task 12: Implement Validation Agent

**Files:**

- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/validation.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/tests/test_validation.py`

- [ ] **Step 1: Implement evidence verifier**

Validation must load `results/evidence_registry.json` and verify:

- Each `source_path` exists.
- Each code output evidence has `verified=True` only after the source file has been read.
- Each evidence item used in a paper section points to a section path under `paper/sections/`.

- [ ] **Step 2: Implement metric consistency check**

For metrics in `results/model_metrics.json`, ensure matching evidence exists:

```text
metric key -> evidence item with source_path == results/model_metrics.json
```

- [ ] **Step 3: Implement sensitivity output**

Write:

- `results/sensitivity_analysis.csv`
- `results/robustness_checks.json`
- `reports/validation_report.md`

The report must include:

```markdown
# Validation Report

## Constraint Checks
## Metric Consistency
## Evidence Coverage
## Sensitivity Analysis
## Robustness Checks
## Blocking Issues
```

- [ ] **Step 4: Emit validation event**

If blocking issues exist, emit `validation.failed`.

If no blocking issues exist, emit `validation.passed`.

- [ ] **Step 5: Run validation tests**

Run:

```bash
pytest tests/test_validation.py -v
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit validation**

Run:

```bash
git add MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/validation.py MathModelAgentDesign/reference_implementation/tests/test_validation.py
git commit -m "feat: add validation agent"
```

### Task 13: Implement Figure Planning and Vector-First Visualization

**Files:**

- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/visualization.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/tests/test_visualization.py`

- [ ] **Step 1: Implement figure planner**

`FigurePlanningAgent.run(workspace_root: Path)` reads:

- `reports/model_decision.md`
- `reports/experiment_plan.md`
- `reports/validation_report.md`
- `results/evidence_registry.json`

It writes `figures/figure_plan.json` with at least:

- one `data_plot`
- one `concept_diagram`

Each `data_plot` must include `"pdf"` or `"svg"` in `output_formats`.

- [ ] **Step 2: Implement data plot renderer**

Use matplotlib with:

```python
plt.rcParams.update({
    "figure.dpi": 160,
    "savefig.dpi": 300,
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
})
```

Write outputs:

```text
figures/<figure_id>.pdf
figures/<figure_id>.svg
figures/<figure_id>.png
```

Save source plotting script to:

```text
figures/source/<figure_id>_plot.py
```

- [ ] **Step 3: Implement concept diagram renderer**

For MVP, write Mermaid source:

```text
figures/source/fig_framework.mmd
```

If `mmdc` is installed, render SVG and PDF.

If `mmdc` is not installed, save the Mermaid source and mark the figure status `review_required`, not `approved`.

- [ ] **Step 4: Implement figure registry**

Write `figures/figure_registry.json`.

Reject `ai_visual_draft` as final paper figure by setting status `review_required` and adding a registry metadata warning:

```text
AI visual drafts must be redrawn as vector figures before final submission.
```

- [ ] **Step 5: Run visualization tests**

Run:

```bash
pytest tests/test_visualization.py -v
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit visualization**

Run:

```bash
git add MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/visualization.py MathModelAgentDesign/reference_implementation/tests/test_visualization.py
git commit -m "feat: add vector first visualization"
```

### Task 14: Implement Paper Writer and LaTeX Typesetter

**Files:**

- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/writer.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/providers/latex.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/templates/paper/main.tex.j2`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/templates/paper/references.bib.j2`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/templates/paper/sections/*.tex.j2`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/tests/test_latex.py`

- [ ] **Step 1: Implement section generation**

`PaperWriterAgent.run(workspace_root: Path)` must write:

```text
paper/sections/abstract.tex
paper/sections/introduction.tex
paper/sections/assumptions.tex
paper/sections/model.tex
paper/sections/results.tex
paper/sections/sensitivity.tex
paper/sections/conclusion.tex
paper/references.bib
paper/main.tex
```

Each generated section must include only:

- problem understanding facts
- approved model decision content
- validated evidence
- registered figures
- registered sources

- [ ] **Step 2: Add unresolved placeholder guard**

If the writer lacks required evidence, insert:

```text
[[UNRESOLVED:
reason = "<specific reason>"
needed_input = "<specific needed input>"
affected_section = "<section file>"
]]
```

Append the same entry to `unresolved_issues.md`.

- [ ] **Step 3: Implement LaTeX compiler provider**

Create `LatexCompileResult`:

```python
class LatexCompileResult(BaseModel):
    success: bool
    pdf_path: str | None = None
    log_path: str
    reason: str = ""
```

`LatexProvider.compile(paper_dir: Path) -> LatexCompileResult` runs:

```bash
latexmk -pdf -interaction=nonstopmode main.tex
```

Write full output to:

```text
paper/compile_log.txt
```

If `latexmk` is missing, return:

```python
LatexCompileResult(success=False, reason="latexmk not installed")
```

and do not mark `paper/main.pdf` as approved.

- [ ] **Step 4: Run LaTeX tests**

Run:

```bash
pytest tests/test_latex.py -v
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit writer and typesetter**

Run:

```bash
git add MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/writer.py MathModelAgentDesign/reference_implementation/src/mcm_agent/providers/latex.py MathModelAgentDesign/reference_implementation/src/mcm_agent/templates/paper MathModelAgentDesign/reference_implementation/tests/test_latex.py
git commit -m "feat: add paper writer and latex compiler"
```

### Task 15: Implement UShallPass Humanization and Fact Regression

**Files:**

- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/providers/humanizer.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/compliance.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/utils/text_locks.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/tests/test_humanizer.py`

- [ ] **Step 1: Implement fact lock extractor**

`extract_fact_locks(text: str) -> FactLocks` must extract:

- numbers, including decimals and percentages
- LaTeX equations between `$<equation>$`, `\(<equation>\)`, `\[<equation>\]`
- citation commands such as `\cite{smith2024}` and `\citep{smith2024}`
- figure references such as `Figure~\ref{fig:model}`
- table references such as `Table~\ref{tab:data}`

- [ ] **Step 2: Implement UShallPass provider**

English submit:

```text
POST /api_v2/rewrite/english/jobs
```

Chinese submit:

```text
POST /api_v2/rewrite/chinese/jobs
```

Poll:

```text
GET <same-submit-path>/{task_id}
```

Headers:

```text
X-API-Key: $HUMANIZER_API_KEY
Accept: application/json
Content-Type: application/json
```

Failure rules:

- `AUTH_ERROR`: raise `RuntimeError("UShallPass authentication failed")`.
- `RATE_LIMITED`: retry with tenacity exponential backoff up to three attempts.
- `INVALID_PARAMETER`: raise `ValueError("UShallPass invalid parameter: <message>")`.
- `SERVICE_UNAVAILABLE`: mark the paragraph skipped and preserve original text.
- timeout: mark skipped and preserve original text.

- [ ] **Step 3: Implement ComplianceOriginalityAgent**

The agent must:

- Read `paper/sections/*.tex`.
- Split paragraphs.
- Skip paragraphs containing formulas, citations, figure refs, table refs, or more than five numeric locks.
- Submit eligible paragraphs.
- Compare locks before and after.
- Write `review/humanization_diff.md`.
- Write `review/fact_regression_report.md`.
- Write `review/originality_report.md`.

- [ ] **Step 4: Implement fact regression rules**

If any number, formula, citation, figure reference, or table reference changes:

- Reject the humanized paragraph.
- Preserve original paragraph.
- Add a `critical` finding to `review/fact_regression_report.md`.

- [ ] **Step 5: Run humanizer tests**

Run:

```bash
pytest tests/test_humanizer.py -v
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit compliance layer**

Run:

```bash
git add MathModelAgentDesign/reference_implementation/src/mcm_agent/providers/humanizer.py MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/compliance.py MathModelAgentDesign/reference_implementation/src/mcm_agent/utils/text_locks.py MathModelAgentDesign/reference_implementation/tests/test_humanizer.py
git commit -m "feat: add humanization with fact regression"
```

### Task 16: Implement Reviewer and Revision Loop

**Files:**

- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/reviewer.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/revision.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/templates/prompts/reviewer.md`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/tests/test_reviewer_revision.py`

- [ ] **Step 1: Implement reviewer checks**

Reviewer must inspect:

- `reports/problem_understanding.md`
- `reports/model_decision.md`
- `reports/validation_report.md`
- `figures/figure_registry.json`
- `results/evidence_registry.json`
- `paper/main.tex`
- `paper/compile_log.txt`
- `review/fact_regression_report.md`
- `rag/review_checklists/pre_submission_checklist.md`

- [ ] **Step 2: Write reviewer report**

Write `review/reviewer_report.md`:

```markdown
# 自动评审报告

## 总体评分
## 主要优点
## 高风险问题
## 需要修改的问题
## 可能影响奖项的问题
## 修改建议
```

- [ ] **Step 3: Write methodology checklist report**

Write `review/methodology_checklist_report.md` with five sections:

```markdown
# Methodology Checklist Report

## Macro Logic
## Writing Details
## English Expression
## LaTeX Formatting
## Figure Quality
```

- [ ] **Step 4: Implement submission blocker**

If any finding has `blocks_submission=True`, emit `paper.review.failed`.

Otherwise emit `paper.review.passed`.

- [ ] **Step 5: Implement revision request parser**

`RevisionAgent.apply_revision_request(workspace_root: Path, user_request: str)` writes:

- `review/revision_requests.md`
- `review/revision_summary.md`

If the request touches results, data, model, or figure generation, mark impacted artifacts as `stale`.

If the request only touches wording, modify paper sections and rerun compliance/reviewer.

- [ ] **Step 6: Run reviewer tests**

Run:

```bash
pytest tests/test_reviewer_revision.py -v
```

Expected:

```text
passed
```

- [ ] **Step 7: Commit reviewer and revision loop**

Run:

```bash
git add MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/reviewer.py MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/revision.py MathModelAgentDesign/reference_implementation/src/mcm_agent/templates/prompts/reviewer.md MathModelAgentDesign/reference_implementation/tests/test_reviewer_revision.py
git commit -m "feat: add reviewer and revision loop"
```

### Task 17: Implement MVP Workflow Orchestrator

**Files:**

- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/workflows/mvp.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/workflows/demo_fixtures.py`
- Modify: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/cli.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/tests/test_mvp_workflow.py`

- [ ] **Step 1: Implement workflow runner**

`run_mvp_workflow(workspace_root: Path, inputs: TaskInput, providers: ProviderBundle, auto_approve: bool = False)` runs agents in this order:

```text
create_workspace
IntakeAgent
DocumentExtractionAgent
ProblemUnderstandingAgent
UserDiscussionAgent
ModelingCouncil
ModelJudge
SearchDataAgent
MethodologyRAGAgent
DataEDAAgent
SolverCoderAgent
ValidationAgent
FigurePlanningAgent
VisualizationAgent
PaperWriterAgent
LatexTypesetterAgent
ComplianceOriginalityAgent
ReviewerAgent
```

Stop at checkpoints unless `auto_approve=True`.

- [ ] **Step 2: Add CLI command**

Add:

```bash
mcm-agent run-demo /absolute/path/to/workspace --auto-approve
```

This command uses:

- fake MinerU
- fake LLM
- fake search
- fake Firecrawl
- fake UShallPass
- sample CSV fixture

- [ ] **Step 3: Define expected demo outputs**

The demo must create:

```text
reports/problem_understanding.md
reports/model_candidates.md
reports/model_decision.md
reports/experiment_plan.md
data/source_registry.json
data/retrieval_log.jsonl
rag/methodology_hits.json
reports/data_profile.md
results/model_metrics.json
results/evidence_registry.json
reports/validation_report.md
figures/figure_plan.json
figures/figure_registry.json
paper/main.tex
review/originality_report.md
review/humanization_diff.md
review/fact_regression_report.md
review/reviewer_report.md
review/methodology_checklist_report.md
final_submission/AI_use_report.md
```

- [ ] **Step 4: Run end-to-end demo test**

Run:

```bash
pytest tests/test_mvp_workflow.py -v
```

Expected:

```text
passed
```

- [ ] **Step 5: Run demo manually**

Run:

```bash
mcm-agent run-demo /tmp/mcm_agent_demo --auto-approve
mcm-agent status /tmp/mcm_agent_demo
```

Expected status:

```text
Phase: paper_review_passed
Unresolved issues: 0
Pending checkpoints: 0
```

- [ ] **Step 6: Commit MVP orchestrator**

Run:

```bash
git add MathModelAgentDesign/reference_implementation/src/mcm_agent/workflows MathModelAgentDesign/reference_implementation/src/mcm_agent/cli.py MathModelAgentDesign/reference_implementation/tests/test_mvp_workflow.py
git commit -m "feat: add mvp workflow runner"
```

### Task 18: Add Submission Packaging

**Files:**

- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/submission.py`
- Modify: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/src/mcm_agent/cli.py`
- Create: `/Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation/tests/test_submission.py`

- [ ] **Step 1: Implement final blocker check**

Block packaging if:

- `unresolved_issues.md` contains `[[UNRESOLVED:`.
- `review/fact_regression_report.md` contains a critical finding.
- `review/reviewer_report.md` contains a blocking issue.
- `paper/main.pdf` does not exist when `latexmk` is available.
- `figures/figure_registry.json` contains final figures with status not equal to `approved`.

- [ ] **Step 2: Generate AI use report**

Write `final_submission/AI_use_report.md`:

```markdown
# AI Use Report

## Tools Used
## Human Decisions
## AI-Assisted Steps
## Verification Steps
## External Services
```

Mention UShallPass only as academic style humanization with fact regression checking.

- [ ] **Step 3: Create source code zip**

Zip:

```text
code/
results/
figures/source/
data/source_registry.json
data/retrieval_log.jsonl
```

to:

```text
final_submission/source_code.zip
```

- [ ] **Step 4: Create submission package**

Zip:

```text
paper/main.pdf
final_submission/AI_use_report.md
final_submission/source_code.zip
```

to:

```text
final_submission/submission_package.zip
```

If `paper/main.pdf` is unavailable because `latexmk` is not installed, create `final_submission/submission_blocked.md` explaining the missing compiler and do not create `submission_package.zip`.

- [ ] **Step 5: Run packaging tests**

Run:

```bash
pytest tests/test_submission.py -v
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit submission packaging**

Run:

```bash
git add MathModelAgentDesign/reference_implementation/src/mcm_agent/agents/submission.py MathModelAgentDesign/reference_implementation/src/mcm_agent/cli.py MathModelAgentDesign/reference_implementation/tests/test_submission.py
git commit -m "feat: add submission packaging"
```

---

## 6. MVP Acceptance Criteria

The MVP is accepted only when all criteria below pass on a clean checkout.

### 6.1 Static and Unit Checks

Run:

```bash
cd /Users/mac/Programming/MathModelAgent/MathModelAgentDesign/reference_implementation
ruff check src tests
pytest -v
```

Required result:

```text
ruff exits 0
pytest exits 0
```

### 6.2 Workspace Contract Check

Run:

```bash
mcm-agent init-workspace /tmp/mcm_workspace_contract
find /tmp/mcm_workspace_contract -maxdepth 3 -type f | sort
```

Required files:

```text
/tmp/mcm_workspace_contract/artifact_registry.json
/tmp/mcm_workspace_contract/data/retrieval_log.jsonl
/tmp/mcm_workspace_contract/data/source_registry.json
/tmp/mcm_workspace_contract/event_log.jsonl
/tmp/mcm_workspace_contract/figures/figure_plan.json
/tmp/mcm_workspace_contract/figures/figure_registry.json
/tmp/mcm_workspace_contract/results/evidence_registry.json
/tmp/mcm_workspace_contract/review/fact_regression_report.md
/tmp/mcm_workspace_contract/review/humanization_diff.md
/tmp/mcm_workspace_contract/review/methodology_checklist_report.md
/tmp/mcm_workspace_contract/task_state.json
/tmp/mcm_workspace_contract/unresolved_issues.md
```

### 6.3 End-to-End Dry Run

Run:

```bash
mcm-agent run-demo /tmp/mcm_agent_demo --auto-approve
mcm-agent status /tmp/mcm_agent_demo
```

Required status:

```text
Phase: paper_review_passed
Unresolved issues: 0
Pending checkpoints: 0
```

Required artifacts:

```text
/tmp/mcm_agent_demo/reports/problem_understanding.md
/tmp/mcm_agent_demo/reports/model_decision.md
/tmp/mcm_agent_demo/data/source_registry.json
/tmp/mcm_agent_demo/data/retrieval_log.jsonl
/tmp/mcm_agent_demo/results/evidence_registry.json
/tmp/mcm_agent_demo/figures/figure_plan.json
/tmp/mcm_agent_demo/figures/figure_registry.json
/tmp/mcm_agent_demo/paper/main.tex
/tmp/mcm_agent_demo/review/humanization_diff.md
/tmp/mcm_agent_demo/review/fact_regression_report.md
/tmp/mcm_agent_demo/review/reviewer_report.md
```

### 6.4 Humanization Safety Check

Run the humanizer test fixture where UShallPass changes `2.31` to `2.13`.

Required result:

- The modified paragraph is rejected.
- Original paragraph is preserved.
- `review/fact_regression_report.md` contains a critical finding.
- `review/humanization_diff.md` records the rejected provider output.

### 6.5 Retrieval Governance Check

Run a fake search with one official source and one SEO-style blog source.

Required result:

- Official source enters `source_registry.json` with `source_rank="official"`.
- Blog source enters with `source_rank="background_only"` or is rejected.
- Both search and extraction actions are recorded in `retrieval_log.jsonl`.
- No background-only source is used as model input.

### 6.6 Figure Contract Check

Run figure generation on the demo workspace.

Required result:

- Data figure produces PDF or SVG.
- `figure_plan.json` includes purpose, source data, target section, and caption intent.
- `figure_registry.json` includes source file and outputs.
- AI visual draft is never marked as approved final data figure.

---

## 7. Agent Collaboration Rules to Enforce in Code

These are not documentation preferences. They must be implemented as runtime checks.

1. Writer cannot use unverified evidence.
2. Writer cannot cite a source that is missing from `source_registry.json`.
3. Data plots cannot be created without `source_data`.
4. Data plots cannot be raster-only.
5. Humanizer cannot modify numbers, formulas, citations, figure references, or table references.
6. Reviewer blocks final submission if unresolved placeholders remain.
7. Search results are not model inputs until Data/EDA Agent processes them.
8. External data must be registered before evidence can reference it.
9. User checkpoint rejection marks downstream artifacts stale.
10. MCP providers can be adapters, but core runtime works without MCP.

---

## 8. Recommended Build Order

Use this exact order because every later layer depends on artifacts from earlier layers:

1. Task 1: scaffold package.
2. Task 2: core models.
3. Task 3: workspace and registries.
4. Task 4: coordinator.
5. Task 5: provider interfaces.
6. Task 6: intake and MinerU extraction.
7. Task 7: problem understanding and user direction.
8. Task 8: modeling council and judge.
9. Task 9: search and data governance.
10. Task 10: methodology RAG.
11. Task 11: EDA, solver, evidence.
12. Task 12: validation.
13. Task 13: figure planning and visualization.
14. Task 14: writer and LaTeX.
15. Task 15: UShallPass and fact regression.
16. Task 16: reviewer and revision.
17. Task 17: MVP workflow.
18. Task 18: submission packaging.

At the end of each task:

```bash
pytest <task-specific-test-file> -v
git status --short
```

Commit only the files listed in that task.

---

## 9. Risk Register

| Risk | Concrete Failure | Mitigation in Plan |
|---|---|---|
| PDF parsing low quality | Missing formula or task statement | Task 6 extraction quality report and fake/local/REST MinerU modes |
| Source hallucination | Writer cites unregistered webpage | Task 9 source registry and Task 14 writer source guard |
| Data hallucination | Paper includes numbers not from code | Task 11 evidence registry and Task 12 validation |
| Figure misuse | Beautiful raster image used as result figure | Task 13 vector output requirement |
| Humanizer changes facts | UShallPass changes result values | Task 15 fact lock and regression |
| Over-complex modeling | Model cannot be implemented in contest time | Task 8 judge scoring includes implementation risk |
| LaTeX failure | PDF not generated | Task 14 compile result and Task 18 blocked package |
| User revision breaks dependencies | Old figures remain after model change | Task 16 stale artifact marking |

---

## 10. Implementation Handoff Notes

Start with fake providers. They are not throwaway code; they are the test harness that makes the real API adapters safe to add.

When real providers are added:

- Keep fake providers as default in tests.
- Add one integration smoke script per provider under `examples/`, not unit tests that require paid API keys.
- Never store API responses only in memory. Persist source, retrieval, evidence, and humanization logs in the workspace.
- Prefer deterministic baseline modeling first, then add stronger LLM-generated modeling code after the pipeline is stable.

The first impressive demo should not be "the model is brilliant." It should be:

```text
Here is a complete, traceable, reviewable contest-paper pipeline that cannot silently invent data or break facts during rewriting.
```
