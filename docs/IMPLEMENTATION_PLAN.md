# MCM/ICM Agent Implementation Plan

Status date: 2026-06-14

This plan reflects the current repository at `/Users/mac/Programming/MCM-ICM-Agent`.
The earlier `MathModelAgentDesign/reference_implementation/` layout has been superseded:
the implementation now lives at the repository root.

For current implementation status, see `docs/PROJECT_STATUS.md`.

## 0. Current Baseline

The repository already contains a tested MVP with:

- CLI-first Python package under `src/mcm_agent/`.
- Workspace, artifact registry, event log, handoff packets, workflow topology, and stage executor.
- Provider adapters for LLM, MinerU, Tavily, Firecrawl, Brave, Exa, UShallPass, LaTeX, academic APIs, and official data APIs.
- Core agents for intake, extraction, problem understanding, data feasibility, discussion, reframing, modeling, search, RAG, EDA, solver, validation, visualization, writing, compliance, review, revision, reference management, and submission packaging.
- Source governance through `source_registry.json`, `retrieval_log.jsonl`, `data_lineage.json`, and `citation_candidates.json`.
- Modeling evidence through `experiment_runs.jsonl`, `model_metrics.json`, `model_route_summary.json`, and `evidence_registry.json`.
- Vector-first figure planning and figure QA.
- Paper evidence binding at section level and claim level.
- Fake-provider end-to-end workflow tests.

Latest verified baseline:

```bash
pytest -q
# 183 passed

ruff check src tests scripts
# All checks passed
```

## 1. Current Repository Layout

```text
MCM-ICM-Agent/
├── README.md
├── pyproject.toml
├── .env.example
├── docs/
│   ├── DESIGN.md
│   ├── IMPLEMENTATION_PLAN.md
│   ├── PROJECT_STATUS.md
│   ├── WORKFLOW.md
│   └── AGENT_TOPOLOGY.md
├── scripts/
├── src/
│   └── mcm_agent/
│       ├── cli.py
│       ├── config.py
│       ├── agents/
│       ├── core/
│       ├── providers/
│       ├── solver_modules/
│       ├── templates/
│       ├── utils/
│       └── workflows/
└── tests/
```

Runtime workspaces are created outside the source tree and contain task artifacts such as
`data/`, `results/`, `figures/`, `paper/`, `review/`, and `final_submission/`.

## 2. Configuration Contract

`.env.example` remains the public configuration contract. Provider keys are optional at startup
and should fail only when the matching provider is invoked.

```bash
# LLM provider
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=

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
MINERU_API_BASE_URL=https://mineru.net
MINERU_API_KEY=

# Runtime
MCM_AGENT_DEFAULT_LANGUAGE=en
MCM_AGENT_MAX_RETRIES=2
MCM_AGENT_HTTP_TIMEOUT_SECONDS=60
MCM_AGENT_CODE_TIMEOUT_SECONDS=120
```

Rules:

- Do not commit `.env` or real secrets.
- Unit tests must use fake providers or HTTP mocks.
- Live provider checks belong in explicit smoke commands.
- MCP is optional for local development and is not a core runtime dependency.

## 3. Completed Build Phases

| Phase | Status |
| --- | --- |
| M0 Project scaffolding | Complete |
| M1 Core workspace, registry, events | Complete |
| M2 Input and MinerU extraction | Complete |
| M3 Planning agents | Complete as MVP |
| M4 Retrieval and methodology RAG | Complete as MVP |
| M5 Data, code, evidence, validation | Complete as MVP |
| M6 Figures and paper | Complete as MVP |
| M7 Humanization, review, revision | Complete as MVP |
| M8 End-to-end fake-provider demo | Complete |
| P1 Data provenance and reference binding | Complete |
| P2 Data scout and user discussion loop | Complete except richer interactive UX |
| P3 Graph-aware stage executor | Complete |
| P4 Machine-readable gate agents | Complete |
| P5 LLM-driven core reasoning agents | Complete as MVP |
| P6 Solver evidence and reproducible experiments | Complete as MVP |
| P7 Vector-first figure system | Complete as MVP |
| P8 Paper, references, and final review | Complete as MVP |

## 4. Active Next Phase

The next phase is **Claim Planning + High Quality Paper Generation**.

Purpose:

The system now stores sources, data lineage, evidence, figures, references, and claim-level
paper bindings. The missing bridge is a planned argument structure that tells the writer what
claims must appear, where they belong, and which artifacts support them.

Target new artifact:

```text
paper/claim_plan.json
```

Target flow:

```text
model_route_summary.json
evidence_registry.json
figure_registry.json
source_registry.json
        ↓
ClaimPlanningAgent
        ↓
paper/claim_plan.json
        ↓
PaperWriterAgent writes sections from planned claims
        ↓
PaperEvidenceBindingAgent checks planned claim coverage
        ↓
ReviewerAgent blocks omitted or unsupported critical claims
```

## 5. Next Phase Tasks

### Task 1: Add Claim Planning Data Contract

Files:

- Modify: `src/mcm_agent/core/models.py`
- Create or modify tests: `tests/test_claim_planning.py`

Implement `PaperClaimPlanItem` with fields:

- `claim_id`
- `section`
- `claim_text`
- `claim_type`: `model_choice`, `metric_result`, `sensitivity`, `assumption`, `limitation`, `conclusion`
- `evidence_ids`
- `figure_ids`
- `source_ids`
- `priority`: `critical`, `major`, `supporting`
- `status`: `planned`, `written`, `unresolved`
- `unresolved_reason`

Validation rules:

- `claim_id` is required.
- `section` must point to a paper section path.
- Critical claims require at least one of `evidence_ids`, `figure_ids`, or `source_ids`, unless `status="unresolved"`.

Acceptance criteria:

- Focused tests prove unsupported critical claims are rejected.
- Existing tests remain green.

### Task 2: Implement ClaimPlanningAgent

Files:

- Create: `src/mcm_agent/agents/claim_planning.py`
- Modify: `src/mcm_agent/agents/__init__.py` if needed
- Create or modify tests: `tests/test_claim_planning.py`

Inputs:

- `results/model_route_summary.json`
- `results/evidence_registry.json`
- `figures/figure_registry.json`
- `data/source_registry.json`
- `reports/validation_report.md`

Outputs:

- `paper/claim_plan.json`
- `review/claim_plan_report.md`

Rules:

- Generate at least one model-route claim when a selected route exists.
- Generate metric-result claims from verified evidence.
- Generate figure-supported claims from approved figures.
- Generate limitation claims when data feasibility or validation reports include unresolved limitations.
- Mark unsupported required claims as `unresolved`, not fabricated.

Acceptance criteria:

- A workspace with route summary, one evidence item, one figure, and one source produces a claim plan with model, result, and conclusion claims.
- A workspace without evidence produces unresolved claims and writes a review report.

### Task 3: Wire Claim Planning Into Workflow

Files:

- Modify: `src/mcm_agent/core/workflow_graph.py`
- Modify: `src/mcm_agent/workflows/mvp.py`
- Modify tests: `tests/test_workflow_topology.py`, `tests/test_mvp_workflow.py`

Workflow change:

```text
validation
        ↓
figure_planning / visualization
        ↓
claim_planning
        ↓
paper_writer
```

Acceptance criteria:

- `workflow_topology.json` contains `claim_planning`.
- MVP workflow creates `paper/claim_plan.json`.
- Stage executor can route claim-plan failures back to `claim_planning` or upstream artifact producers.

### Task 4: Make PaperWriterAgent Claim-Plan Driven

Files:

- Modify: `src/mcm_agent/agents/writer.py`
- Modify tests: `tests/test_paper_evidence_binding.py`, `tests/test_llm_agents.py`

Rules:

- If `paper/claim_plan.json` exists, Writer must use it as the authoritative list of important claims.
- Writer must emit one machine-readable claim trace per written planned claim.
- Writer must not silently omit critical planned claims.
- Unsupported planned claims must be written as structured unresolved placeholders, not as unsupported prose.
- Existing deterministic fallback remains available for minimal/demo workspaces.

Acceptance criteria:

- A planned claim appears in the expected section with `claim_id`, `evidence_id`, `figure_id`, and `source_id`.
- An unresolved planned claim is recorded in `unresolved_issues.md`.
- Existing LLM fallback tests remain green.

### Task 5: Extend PaperEvidenceBindingAgent To Check Planned Coverage

Files:

- Modify: `src/mcm_agent/agents/paper_evidence.py`
- Modify tests: `tests/test_paper_evidence_binding.py`

Rules:

- Read `paper/claim_plan.json` when present.
- Check that every non-unresolved planned critical or major claim appears in paper sections.
- Check that written claim bindings match or are a valid subset of planned bindings.
- Report omitted claims in `review/paper_evidence_report.md`.

Acceptance criteria:

- Missing planned critical claims fail `paper_evidence_binding`.
- Unknown IDs still fail as they do now.
- Existing section-level trace compatibility remains.

### Task 6: Extend ReviewerAgent For Claim Plan Quality

Files:

- Modify: `src/mcm_agent/agents/reviewer.py`
- Modify tests: `tests/test_reviewer_revision.py` or create `tests/test_claim_planning.py`

Rules:

- Final gate blocks when critical planned claims are omitted.
- Final gate blocks when unresolved critical claims remain.
- Final gate distinguishes writing failures from upstream missing-evidence failures through `repair_stage`.

Acceptance criteria:

- Omitted planned claims route to `paper_writer`.
- Missing evidence for planned claims routes to `validation` or `solver`.
- Missing source bindings route to `search_data`.

### Task 7: Update Docs And Demo

Files:

- Modify: `docs/DESIGN.md`
- Modify: `docs/WORKFLOW.md`
- Modify: `docs/PROJECT_STATUS.md`
- Modify: `scripts/run_demo_task.py` if needed

Acceptance criteria:

- Documentation explains `paper/claim_plan.json`.
- Demo run includes claim plan artifacts.
- `PROJECT_STATUS.md` reflects the new implementation state after the phase lands.

## 6. Later Build Phases

After claim planning, continue with these quality phases:

1. **Real Data API Expansion**
   - Add OECD, UNData, FRED, US Census, NOAA/NASA/Open-Meteo, and OSM/Overpass providers.
   - Add provider-specific source and lineage records.

2. **Paper Quality Upgrade**
   - Improve abstract, introduction, assumptions, model formulation, results narrative, limitations, and conclusion.
   - Add stronger section templates and claim-aware citation insertion.

3. **Concept Diagram System**
   - Add Mermaid, Graphviz, and TikZ concept figure generation.
   - Keep final concept diagrams vector-first.

4. **LaTeX Layout QA**
   - Detect compile errors, table overflow, equation overflow, figure placement issues, and page-limit violations.
   - Route layout failures back to writer, visualization, or typesetting.

5. **Provider Smoke Command**
   - Add a CLI command that checks configured live API providers without running a full workflow.
   - Report missing keys, auth failures, rate limits, and endpoint availability.

6. **RAG Ingestion**
   - Import user-uploaded excellent papers, method notes, and competition rules.
   - Store retrieval hits with source provenance and usage restrictions.

## 7. Operating Rules

- Use TDD for behavior changes.
- Keep commits small and independently useful.
- Do not call paid or live APIs in unit tests.
- Never commit `.env` or secrets.
- Every external datum needs a `source_id`.
- Every modeled result needs an `evidence_id`.
- Every final data figure needs a `figure_id`, source data, and PDF/SVG output.
- Every important paper claim should either bind to evidence, figures, and sources, or be explicitly unresolved.
- Every blocking review finding must map to a repair stage.

## 8. Verification Before Completion

For documentation-only changes:

```bash
pytest tests/test_docs.py -q
```

For code changes:

```bash
pytest -q
ruff check src tests scripts
```

Before pushing a phase, confirm `git status --short` only contains intended files.
