# Claude Code Handoff: MCM-ICM Agent

Status date: 2026-06-16

This handoff is for continuing development in:

```text
/Users/mac/Programming/MCM-ICM-Agent
https://github.com/jsyzlbw/MCM-ICM-Agent
```

Important: do not confuse this repository with:

```text
/Users/mac/Programming/MathModelAgent
https://github.com/jsyzlbw/MathModelAgent
https://github.com/jihe520/MathModelAgent
```

Earlier README work was accidentally done in `MathModelAgent`; that has since been corrected. The active project is `MCM-ICM-Agent`.

## Update 2026-06-17 (read this first)

Since the original 2026-06-16 handoff, the following shipped to `main` (all fake/demo-provider tested; `pytest -q` = 322 passed; `ruff` clean). Design specs + task plans are under `docs/superpowers/specs/` and `docs/superpowers/plans/`.

- **Workflow Control API** — threaded run registry + a cooperative pause/stop hook in the stage executor; endpoints `POST .../run|resume|stop`, `GET .../run` (run-status, incl. a `stopping` state), `POST .../checkpoints/{id}/approve`, `GET .../events` (SSE), `GET .../logs`. Real runs without an LLM key are rejected (use `demo:true`).
- **Zero-build GUI** — `mcm-agent gui` serves a static Alpine.js + SSE app at `/`; six screens: Settings, Knowledge Base, Task Upload, Discussion/Planning, Run Monitor (live timeline + log + checkpoint approval + error display), Artifacts. Markdown is rendered in artifact/planning views. Config saves merge-safely (never clobbers stored secrets). The "extra requirements" box is persisted as the workflow's user idea.
- **Knowledge Base API** — list/upload/delete `knowledge_base/` files + offline index preview.
- **RAG v2** — hybrid FTS + vector retrieval with reranking; Voyage embedding/rerank providers (+ deterministic fakes for offline), content-hash embedding cache, per-workspace chroma index. New `embedding` config section. `chromadb` is now a dependency. Embedding is in `provider-smoke`/`provider-status`.
- **Provider smoke history** — `provider-smoke` appends results to `<workspace>/provider_smoke_history.jsonl`.

**Highest-value next work — needs YOU (not done autonomously on purpose):**
1. **Real-provider end-to-end** — needs your real keys (LLM + Voyage + data). Run a small task through the GUI; fix real-mode issues (cooperative stop only acts between stages).
2. **In-browser GUI verification** — I cannot open a browser; click through the six screens (esp. SSE live updates + checkpoint approval + markdown rendering).
3. **Stronger problem-specific modeling/code generation** — the deepest gap; needs a design pass with you (kept out of autonomous scope deliberately).
4. Optional decision: structured "case" knowledge-base schema vs. the current flat-file model (see `docs/superpowers/plans/2026-06-16-phase3-knowledge.md`).

## Current Git State

Latest commit on `main` at the time of this update:

```text
1bc42e7 feat: record provider-smoke run history (roadmap: live provider history)
```

Remote:

```text
origin https://github.com/jsyzlbw/MCM-ICM-Agent.git
```

Before continuing, run:

```bash
cd /Users/mac/Programming/MCM-ICM-Agent
git status --short --branch
git remote -v
git log --oneline --decorate --max-count=5
```

Expected branch is `main`, tracking `origin/main`.

## Product Goal

Build a user-facing MCM/ICM mathematical modeling agent. The final product should be easy to use through a GUI:

1. Configure all API providers in one local JSON file.
2. Import excellent modeling papers, rules, and method notes into a local RAG knowledge base.
3. Upload the current contest problem package, including PDFs, data, templates, images, and additional requirements.
4. Discuss the implementation plan with the agent before execution.
5. Let the multi-agent workflow research, model, solve, write, typeset, review, repair, and package the submission.
6. Show users what the agent is doing while it runs.
7. Let users inspect artifacts and request revisions.

The current repository is CLI-first with a local FastAPI GUI backend foundation. It does not yet have a production GUI frontend.

## Implemented Capabilities

### Core Workflow

The workflow is no longer a simple linear MVP. It is a graph-aware, checkpointable pipeline:

```text
intake
mineru_extraction
extraction_quality_gate
problem_understanding
data_feasibility_scout
research_reframing when needed
user_discussion
methodology_rag
modeling_council
model_judge
modeling_quality_gate
search_data
source_verifier
data_eda
solver_coder
validation_gate
figure_planning
visualization
figure_quality_gate
claim_planning
paper_writer
paper_evidence_binding
typesetting
pre_submission_review
final_gatekeeper
submission_packager
```

The executor writes `task_state.json`, `stage_runs.jsonl`, gate files, repair metadata, and workspace artifacts. `mcm-agent inspect` and `mcm-agent resume` are important operational commands.

### Agent System

Key agents are implemented under `src/mcm_agent/agents/`:

- `IntakeAgent`
- `DocumentExtractionAgent`
- `ProblemUnderstandingAgent`
- `DataFeasibilityScoutAgent`
- `ResearchReframingAgent`
- `UserDiscussionAgent`
- `MethodologyRAGAgent`
- `ModelingCouncil`
- `ModelJudge`
- `ModelingPlanQualityAgent`
- `SearchDataAgent`
- `DataEDAAgent`
- `SolverCoderAgent`
- `ValidationAgent`
- `FigurePlanningAgent`
- `VisualizationAgent`
- `FigureQualityAgent`
- `ClaimPlanningAgent`
- `PaperWriterAgent`
- `PaperEvidenceBindingAgent`
- `ComplianceOriginalityAgent`
- `ReferenceManager`
- `TypesettingQAAgent`
- `TypesettingRepairAgent`
- `ReviewerAgent`
- `SubmissionPackager`

Agents communicate through workspace files, not hidden chat state. The README now documents the stage/agent/input/output/purpose table.

### Workspace Evidence Contract

Important artifacts:

```text
input/
parsed/problem.md
reports/problem_understanding.md
reports/data_feasibility_report.md
discussion/confirmed_direction.md
rag/methodology_hits.json
reports/experiment_spec.json
data/source_registry.json
data/retrieval_log.jsonl
data/data_lineage.json
data/citation_candidates.json
results/model_route_summary.json
results/evidence_registry.json
figures/figure_registry.json
paper/claim_plan.json
paper/main.tex
paper/references.bib
review/*.json
final_submission/
```

The design intent is evidence-first paper generation: planned claims should be traceable to evidence, figures, sources, or explicit unresolved reasons.

### Unified JSON Configuration

Committed template:

```text
mcm_agent_config.example.json
```

Local ignored config:

```text
mcm_agent_config.local.json
```

The `.gitignore` intentionally ignores:

```text
.env
.env.*
mcm_agent_config.local.json
knowledge_base/*
!knowledge_base/.gitkeep
```

Top-level config sections:

- `llm`
- `search`
- `official_data`
- `mineru`
- `humanizer`
- `rag`
- `runtime`

`.env` is still supported for backward compatibility, but JSON config values override `.env` when both are supplied.

### Provider Support

Provider or smoke-test coverage exists for:

- OpenAI-compatible LLM
- Tavily
- Firecrawl
- Brave Search
- Exa
- UShallPass-compatible humanizer
- MinerU fake/local/rest
- World Bank
- OECD
- UNData
- FRED
- US Census
- NOAA
- NASA POWER
- Open-Meteo
- OSM/Overpass

Manual provider smoke:

```bash
mcm-agent provider-smoke \
  --config-file mcm_agent_config.local.json \
  --workspace .smoke
```

Subset example:

```bash
mcm-agent provider-smoke \
  --config-file mcm_agent_config.local.json \
  --providers llm,tavily,firecrawl,fred
```

MinerU parse smoke:

```bash
mcm-agent provider-smoke \
  --config-file mcm_agent_config.local.json \
  --mineru-file /path/to/sample.pdf
```

### RAG Knowledge Base

The committed folder:

```text
knowledge_base/.gitkeep
```

User-provided files under `knowledge_base/` are ignored by git. Supported ingest extensions are configured in JSON and currently default to:

```json
[".md", ".txt", ".pdf"]
```

`.md` and `.txt` are chunked directly. `.pdf` uses MinerU when available. Current RAG is mostly local methodology retrieval; embedding/rerank is not yet implemented.

### Modeling

Implemented route planning and deterministic solver modules for common MCM/ICM archetypes:

- multi-criteria evaluation
- constrained optimization
- forecasting
- Monte Carlo simulation
- classification
- clustering/segmentation
- queueing service analysis
- network flow/graph structure
- multi-objective decision support

Key files:

```text
src/mcm_agent/core/model_recipes.py
src/mcm_agent/core/modeling_intelligence.py
src/mcm_agent/solver_modules/
tests/test_solver_modules.py
tests/test_modeling_intelligence.py
```

This is still a deterministic baseline, not strong arbitrary model-code generation.

### Paper Generation

Implemented:

- `paper/claim_plan.json`
- claim-aware section generation
- source-to-BibTeX mapping
- paper evidence binding
- reference audit
- typesetting QA
- conservative one-pass LaTeX repair
- reviewer/final gate
- submission packager

Important files:

```text
src/mcm_agent/agents/claim_planning.py
src/mcm_agent/agents/writer.py
src/mcm_agent/agents/paper_evidence.py
src/mcm_agent/agents/reference_manager.py
src/mcm_agent/agents/typesetting_qa.py
src/mcm_agent/agents/typesetting_repair.py
src/mcm_agent/agents/reviewer.py
src/mcm_agent/agents/submission.py
src/mcm_agent/templates/paper/
```

### Local GUI API Foundation

CLI command:

```bash
mcm-agent gui --host 127.0.0.1 --port 8787
```

Implemented server modules:

```text
src/mcm_agent/server/app.py
src/mcm_agent/server/routes_config.py
src/mcm_agent/server/routes_workspace.py
src/mcm_agent/server/routes_artifacts.py
src/mcm_agent/server/config_store.py
src/mcm_agent/server/schemas.py
```

Current endpoints include:

- `GET /api/health`
- `GET /api/config`
- `POST /api/config`
- `POST /api/config/test-provider`
- `POST /api/workspaces`
- `GET /api/workspaces`
- `GET /api/workspaces/{workspace_id}`
- `POST /api/workspaces/{workspace_id}/files`
- `GET /api/workspaces/{workspace_id}/status`
- `GET /api/workspaces/{workspace_id}/artifacts`
- `GET /api/workspaces/{workspace_id}/artifacts/content`
- `GET /api/workspaces/{workspace_id}/artifacts/download`

Missing: workflow run/resume/stop endpoints and a real frontend.

## Commands To Know

Install:

```bash
python -m pip install -e ".[dev]"
cp mcm_agent_config.example.json mcm_agent_config.local.json
```

Demo:

```bash
mcm-agent run-demo /tmp/mcm_agent_demo --auto-approve
mcm-agent inspect /tmp/mcm_agent_demo
mcm-agent status /tmp/mcm_agent_demo
```

Helper demo:

```bash
python scripts/run_demo_task.py --workspace .demo_workspace --clean
```

Real run:

```bash
mcm-agent run /tmp/mcm_agent_task \
  --config-file mcm_agent_config.local.json \
  --problem-file /path/to/problem.pdf \
  --attachment /path/to/data.csv \
  --user-idea-file /path/to/user_idea.md \
  --auto-approve
```

Resume:

```bash
mcm-agent resume /tmp/mcm_agent_task \
  --config-file mcm_agent_config.local.json \
  --problem-file /path/to/problem.pdf \
  --attachment /path/to/data.csv \
  --from-stage validation_gate \
  --until-stage final_gatekeeper \
  --auto-approve
```

Package:

```bash
mcm-agent package /tmp/mcm_agent_task
```

Provider status:

```bash
mcm-agent provider-status --config-file mcm_agent_config.local.json
```

GUI API:

```bash
mcm-agent gui --host 127.0.0.1 --port 8787
```

## Verification Commands

Run before claiming completion:

```bash
python -m pytest tests/test_docs.py tests/test_server_config.py tests/test_server_workspace.py -q
python -m pytest -q
```

If ruff is installed:

```bash
ruff check src tests scripts
```

Recent verified result before this handoff:

```text
276 passed, 1 warning
```

Warning is from FastAPI/Starlette TestClient/httpx deprecation and is currently non-blocking.

## Recent Documentation Work

README was rewritten and pushed to GitHub:

- default English `README.md`
- Chinese `README.zh-CN.md`
- architecture SVG `docs/assets/mcm-icm-agent-hero.svg`

Latest README emphasizes:

- agent system
- stage/agent/input/output/purpose table
- collaboration model
- workflow loops
- command reference
- configuration
- workspace artifacts
- local GUI API

Do not replace it with generic marketing copy. The user explicitly wants professional developer docs focused on agents and commands.

## Current Gaps

The project is strong as a workflow prototype, but not yet mature product software. Major gaps:

1. No production GUI frontend.
2. GUI API cannot yet start, stop, resume, or stream workflow runs.
3. No real-time event stream for users to see what the agent is doing.
4. RAG lacks embedding/rerank; current behavior is closer to local methodology retrieval.
5. Solver modules are deterministic baselines; stronger problem-specific modeling/code generation is still needed.
6. Real-provider end-to-end smoke has not been fully run with all API keys.
7. LaTeX repair is conservative and does not handle complex page-limit, float-placement, or template-specific failures.
8. No persistent run database, user accounts, auth, or deployment model.

## Recommended Next Route

Recommended next route: GUI Product MVP plus Workflow Control API.

### Phase 1: Backend Workflow Control API

Goal: allow a GUI to operate the agent, not only inspect files.

Suggested endpoints:

- `POST /api/workspaces/{workspace_id}/run`
- `POST /api/workspaces/{workspace_id}/resume`
- `POST /api/workspaces/{workspace_id}/stop`
- `POST /api/workspaces/{workspace_id}/checkpoints/{checkpoint_id}/approve`
- `GET /api/workspaces/{workspace_id}/events`
- `GET /api/workspaces/{workspace_id}/logs`

Implementation guidance:

- Keep execution local and file-backed first.
- Avoid introducing Celery/Redis unless necessary.
- Use a background task/thread registry for MVP if tests can cover it.
- Expose stage status from `task_state.json` and `stage_runs.jsonl`.
- Tests should live near existing server tests:

```text
tests/test_server_workspace.py
tests/test_server_config.py
tests/test_server_artifacts.py or new tests/test_server_workflow_control.py
```

### Phase 2: GUI Frontend MVP

Goal: give users a real interface.

Minimum screens:

1. Settings: edit JSON-backed config; each provider row has a test button.
2. RAG Knowledge Base: show expected folder structure, import/upload files, display indexed materials.
3. Task Upload: upload problem PDF, attachments, template, extra requirements.
4. Conversation/Planning: user discusses plan, agent proposes direction, user approves.
5. Run Monitor: live stage timeline, current agent, recent logs, failed gate, repair route.
6. Artifact Browser: inspect/download reports, figures, LaTeX, PDF, final zip.

Prefer a simple web app that talks to the local FastAPI server. Keep UI honest about prototype maturity.

### Phase 3: RAG v2

Goal: improve retrieval quality.

The user chose Voyage for embedding/rerank in earlier discussion. Add JSON config fields before hardcoding:

```json
{
  "embedding": {
    "provider": "voyage",
    "api_key": "",
    "embedding_model": "voyage-3-large",
    "rerank_model": "rerank-2"
  }
}
```

Then implement:

- ingestion index with vectors
- chunk metadata and provenance
- rerank during retrieval
- tests with fake embedding/rerank provider
- no real key committed

### Phase 4: Real Provider End-to-End Smoke

Goal: prove the configured stack can run a small real task.

Run:

```bash
mcm-agent provider-smoke --config-file mcm_agent_config.local.json --workspace .smoke
```

Then run a small problem package through:

```bash
mcm-agent run /tmp/mcm_agent_real_smoke \
  --config-file mcm_agent_config.local.json \
  --problem-file /path/to/small_problem.pdf \
  --attachment /path/to/small_data.csv \
  --auto-approve
```

Document provider failures without printing secrets.

## User Preferences And Constraints

- User wants all API keys and provider choices configured in one local JSON file.
- Local secret config must be ignored by git; only example templates are committed.
- RAG knowledge base should be empty in git and user-filled locally.
- User wants GUI interaction eventually.
- User wants users to see what the agent is doing during long runs.
- User wants professional developer documentation, not generic marketing.
- User strongly dislikes confusing `MCM-ICM-Agent` with `MathModelAgent`.
- Do not commit `.env`, `mcm_agent_config.local.json`, `knowledge_base/*`, generated workspaces, caches, or API keys.

## Known API Keys

The user has provided test keys in prior conversation and asked to save/use them locally only. Do not commit or repeat secrets in docs. Check local `.env` or `mcm_agent_config.local.json` if needed, but keep secrets out of git output.

Potential providers mentioned:

- OpenAI-compatible LLM endpoint
- Tavily
- Firecrawl
- Brave Search
- Exa
- UShallPass-compatible humanizer
- MinerU
- OpenAlex
- FRED
- US Census
- NOAA
- Voyage embedding/rerank

Semantic Scholar key was pending at the time of earlier discussion.

## Development Guardrails

1. Always work in `/Users/mac/Programming/MCM-ICM-Agent`.
2. Run `git remote -v` before commits if there is any doubt.
3. Use `rg` for searches.
4. Use `apply_patch` for manual file edits.
5. Do not revert unrelated user changes.
6. Do not commit generated files or secrets.
7. Keep tests focused for small changes, full `pytest -q` before major claims or pushes.
8. Preserve the artifact-driven architecture; do not turn the system into a hidden-state chat chain.

## Useful Files To Read First

```text
README.md
README.zh-CN.md
docs/WORKFLOW.md
docs/AGENT_TOPOLOGY.md
docs/PROJECT_STATUS.md
docs/DESIGN.md
src/mcm_agent/cli.py
src/mcm_agent/workflows/mvp.py
src/mcm_agent/server/app.py
src/mcm_agent/server/routes_config.py
src/mcm_agent/server/routes_workspace.py
src/mcm_agent/server/routes_artifacts.py
src/mcm_agent/config.py
mcm_agent_config.example.json
```

## Suggested First Task For Claude Code

Start with a planning pass for:

```text
GUI Product MVP + Workflow Control API
```

Recommended first implementation slice:

1. Add backend workflow-control API endpoints for run/resume/status/events.
2. Keep them file-backed and locally testable.
3. Add tests for endpoint behavior using fake/demo providers.
4. Only then scaffold the frontend.

This is the best next step because the workflow already exists, but users still cannot comfortably operate it or see progress from a GUI.
