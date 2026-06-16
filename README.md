<p align="center">
  <a href="README.md"><img alt="English" src="https://img.shields.io/badge/English-default-111827?style=for-the-badge"></a>
  <a href="README.zh-CN.md"><img alt="Simplified Chinese" src="https://img.shields.io/badge/简体中文-切换语言-10b981?style=for-the-badge"></a>
</p>

<p align="center">
  <img src="docs/assets/mcm-icm-agent-hero.svg" alt="MCM-ICM Agent architecture diagram" width="100%">
</p>

<div align="center">

# MCM-ICM Agent

**A traceable multi-agent workflow for MCM / ICM mathematical modeling papers.**

MCM-ICM Agent turns a contest problem package into an auditable workspace: parsed problem files, data feasibility reports, model-route decisions, solver outputs, evidence registries, claim-aware LaTeX sections, review gates, repair logs, and final submission packages.

[Agent System](#agent-system) · [Workflow](#workflow) · [Command Reference](#command-reference) · [Configuration](#configuration) · [Artifacts](#workspace-artifacts) · [GUI API](#local-gui-api)

![Python](https://img.shields.io/badge/python-3.12%2B-3776ab)
![CLI](https://img.shields.io/badge/interface-CLI%20%2B%20local%20GUI%20API-0f766e)
![FastAPI](https://img.shields.io/badge/gui%20api-FastAPI-009688)
![Tests](https://img.shields.io/badge/tests-pytest-0ea5e9)
![Status](https://img.shields.io/badge/status-active%20research%20prototype-f59e0b)

</div>

---

## What Matters

This repository is not a generic chat agent. It is a staged contest-paper system where each agent reads registered workspace artifacts, writes new artifacts, and passes explicit quality gates before downstream agents can depend on its output.

The central design idea is simple:

```text
Problem package -> Agent workflow -> Evidence-backed paper -> Review/repair loop -> Submission package
```

The implementation is CLI-first and now also ships a **zero-build local web GUI** (served by `mcm-agent gui`) backed by a Workflow Control API, so you can configure providers, upload a task, run/resume/stop the workflow, watch live progress, approve checkpoints, and browse artifacts from a browser. The production-grade part today is the workflow and artifact contract; the GUI is a working local single-user app, not a hosted multi-user service.

---

## Agent System

The project is organized as a graph of specialized agents. They do not collaborate through hidden memory. They collaborate through files in the workspace: reports, JSON registries, source logs, evidence records, figure registries, LaTeX files, and gate decisions.

### Agent Roles

| Stage | Agent | Reads | Writes | Purpose |
|---|---|---|---|---|
| `intake` | Intake Agent | Problem file, attachments, user idea, template dir | `input_manifest.json`, copied inputs | Creates the workspace input contract. |
| `mineru_extraction` | Document Extraction Agent | Input manifest, MinerU provider | `parsed/problem.md`, `parsed/problem.json`, extraction report | Converts problem PDFs and templates into machine-readable text and layout artifacts. |
| `extraction_quality_gate` | Extraction QA Gate | Parsed problem artifacts | `review/extraction_gate.json` | Blocks downstream reasoning when extraction is incomplete. |
| `problem_understanding` | Problem Understanding Agent | Parsed problem | `reports/problem_understanding.md` | Extracts tasks, constraints, metrics, ambiguities, and assumptions. |
| `data_feasibility_scout` | Data Feasibility Scout Agent | Problem understanding, search provider | `reports/data_feasibility_report.md`, decision JSON | Checks whether required data is public, proxy-needed, private, or unknown before locking a plan. |
| `research_reframing` | Research Reframing Agent | Data feasibility decision | `discussion/reframing_options.md`, JSON | Reframes plans when direct data is unavailable. |
| `user_discussion` | User Discussion Agent | Problem report, data feasibility, user idea | `discussion/confirmed_direction.md`, `direction_lock.json` | Locks the research direction or sends new data needs back to scouting. |
| `methodology_rag` | Methodology RAG Agent | Local `knowledge_base/`, supervisor skills, MinerU | `rag/methodology_hits.json`, methodology report | Retrieves excellent-paper patterns, method notes, and checklist guidance. |
| `modeling_council` | Modeling Council | Understanding, direction lock, LLM | `reports/model_candidates.md` | Proposes candidate model routes and hybrid strategies. |
| `model_judge` | Model Judge Agent | Model candidates, LLM | `reports/model_decision.md`, `reports/experiment_spec.json` | Selects the model route and experiment contract. |
| `modeling_quality_gate` | Modeling Plan Quality Agent | Experiment spec, model decision | `review/modeling_gate.json` | Rejects weak, unsupported, or under-specified modeling plans. |
| `search_data` | Search & Data Agent | Search, extraction, official-data providers | `data/source_registry.json`, `data/retrieval_log.jsonl`, lineage and repair files | Collects and registers sources, web extracts, and official datasets. |
| `source_verifier` | Source Verifier Gate | Source registry | `review/source_gate.json` | Ensures sources are reliable enough for paper claims. |
| `data_eda` | Data / EDA Agent | Registered data and attachments | `reports/data_profile.md`, `data/processed/` | Profiles fields, cleans tables, and records limitations. |
| `solver_coder` | Solver / Coding Agent | Experiment spec, processed data | `code/`, `results/model_route_summary.json`, `results/evidence_registry.json` | Runs deterministic solver modules and registers numerical evidence. |
| `validation_gate` | Validation Agent | Solver outputs and evidence | `reports/validation_report.md`, `review/validation_gate.json` | Checks metrics, robustness, sensitivity, and evidence coverage. |
| `figure_planning` | Figure Planning Agent | Results, evidence, source registry | `figures/figure_plan.json` | Plans figures by purpose, source, and target paper section. |
| `visualization` | Visualization Agent | Figure plan and data | `figures/figure_registry.json`, SVG/PNG/PDF outputs | Generates vector-first plots and artifact-derived concept diagrams. |
| `figure_quality_gate` | Figure Quality Agent | Figure registry and generated graphics | `review/figure_gate.json`, quality report | Checks figure readability, vector outputs, captions, and section placement. |
| `claim_planning` | Claim Planning Agent | Understanding, model decision, validation, RAG, evidence, figures, sources | `paper/claim_plan.json`, claim-plan report | Plans the paper's argument chain before drafting. |
| `paper_writer` | Paper Writer Agent | Claim plan, evidence, figures, sources, LLM | `paper/main.tex`, `paper/sections/` | Writes claim-aware LaTeX sections with trace comments and citations. |
| `paper_evidence_binding` | Paper Evidence Binding Agent | Paper sections, claim plan, registries | `review/paper_evidence_bindings.json`, report | Verifies section and claim support. |
| `typesetting` | Compliance, Reference, LaTeX, and Repair Agents | Paper files, citations, humanizer, LaTeX provider | `paper/references.bib`, `review/typesetting_quality.json`, repair reports, optional `paper/main.pdf` | Handles references, originality/humanization checks, compilation, QA, and conservative source repair. |
| `pre_submission_review` | Reviewer Agent | All major workspace artifacts | `review/reviewer_report.md`, `review/final_gate.json` | Performs final paper-quality, evidence, and compliance review. |
| `final_gatekeeper` | Final Gatekeeper | Final gate decision | `review/final_gate.json` | Routes blocking findings to the responsible repair stage. |
| `submission_packager` | Submission Packager | Reviewed paper and artifacts | `final_submission/submission_package.zip`, manifest, checklist, or blocked report | Produces the final package when prerequisites are satisfied. |

### Collaboration Model

The agents coordinate through a graph-aware executor:

1. Each stage declares the artifacts it writes.
2. Gate stages emit machine-readable pass/fail decisions.
3. Failed gates route to responsible repair stages, such as `search_data`, `modeling_council`, `solver_coder`, `figure_planning`, `paper_writer`, or `typesetting`.
4. `mcm-agent inspect` explains the current phase, latest failed gate, repair stage, and recent stage history.
5. `mcm-agent resume` restarts from a selected stage or from the blocked repair point in `task_state.json`.

See [docs/AGENT_TOPOLOGY.md](docs/AGENT_TOPOLOGY.md) for the longer topology document and Mermaid workflow graph.

---

## Workflow

Typical pass path:

```text
intake
mineru_extraction
extraction_quality_gate
problem_understanding
data_feasibility_scout
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

Important loops:

| Loop | Why it exists |
|---|---|
| `data_feasibility_scout -> research_reframing -> user_discussion` | Avoids committing to a plan that depends on private, unavailable, or weak data. |
| `user_discussion -> data_feasibility_scout` | Rechecks feasibility when the user introduces a new data-dependent idea. |
| `modeling_quality_gate -> modeling_council` | Repairs weak model choices before solver work. |
| `validation_gate -> solver_coder/search_data/modeling_council` | Sends failures to code, data, or model repair depending on root cause. |
| `figure_quality_gate -> figure_planning` | Repairs figures before the paper claim plan depends on them. |
| `final_gatekeeper -> responsible stage` | Routes final blockers to the smallest meaningful repair point. |

For operational details, workspace structure, gate formats, and common failure modes, read [docs/WORKFLOW.md](docs/WORKFLOW.md).

---

## Command Reference

Install first:

```bash
python -m pip install -e ".[dev]"
cp mcm_agent_config.example.json mcm_agent_config.local.json
```

### `mcm-agent version`

Prints the installed CLI version.

```bash
mcm-agent version
```

Use this to confirm that your shell is running the editable checkout you expect.

### `mcm-agent init-workspace`

Initializes an empty task workspace.

```bash
mcm-agent init-workspace /tmp/mcm_agent_task
```

This creates the base workspace structure and `task_state.json`. It is useful when you want to inspect the workspace format before running a full workflow.

### `mcm-agent run-demo`

Runs a deterministic demo using fake providers and bundled example inputs.

```bash
mcm-agent run-demo /tmp/mcm_agent_demo --auto-approve
```

Use this as the first smoke test after installation. It exercises the workflow without consuming paid APIs.

Equivalent helper:

```bash
python scripts/run_demo_task.py --workspace .demo_workspace --clean
```

### `mcm-agent run`

Runs the workflow on real task inputs.

```bash
mcm-agent run /tmp/mcm_agent_task \
  --config-file mcm_agent_config.local.json \
  --problem-file /path/to/problem.pdf \
  --attachment /path/to/data.csv \
  --attachment /path/to/extra.xlsx \
  --user-idea-file /path/to/user_idea.md \
  --template-dir /path/to/template_dir \
  --supervisor-skills-dir /path/to/skills \
  --auto-approve
```

Options:

| Option | Meaning |
|---|---|
| `WORKSPACE` | Directory where all inputs, reports, artifacts, and final packages are written. |
| `--problem-file`, `-p` | Required problem statement file. |
| `--attachment`, `-a` | Optional repeatable attachment file: CSV, XLSX, images, PDFs, or other contest data. |
| `--user-idea-file` | Optional user notes, initial modeling idea, or constraints. |
| `--template-dir` | Optional contest template or formatting sample directory. |
| `--supervisor-skills-dir` | Optional directory of methodology/review skill notes to ingest during RAG. |
| `--env-file` | Optional legacy `.env` source. |
| `--config-file` | Preferred local JSON config. Values here override `.env`. |
| `--auto-approve` | Automatically approves checkpoints. Omit this for human review checkpoints. |

### `mcm-agent inspect`

Explains the current state of a workspace.

```bash
mcm-agent inspect /tmp/mcm_agent_task
```

It reports current phase, unresolved issues, failed gate, repair stage, model routes, submission manifest status, and recent stages. Use this whenever a run appears stuck or blocked.

### `mcm-agent status`

Prints a compact workspace status summary.

```bash
mcm-agent status /tmp/mcm_agent_task
```

This is lighter than `inspect`: current phase, unresolved issue count, and pending checkpoints.

### `mcm-agent resume`

Resumes an existing workspace from a selected stage or from the repair stage saved in `task_state.json`.

```bash
mcm-agent resume /tmp/mcm_agent_task \
  --config-file mcm_agent_config.local.json \
  --problem-file /path/to/problem.pdf \
  --attachment /path/to/data.csv \
  --from-stage validation_gate \
  --until-stage final_gatekeeper \
  --auto-approve
```

Common resume patterns:

| Goal | Example |
|---|---|
| Resume from blocked repair stage | omit `--from-stage` |
| Rerun data collection onward | `--from-stage search_data` |
| Rerun modeling and solver | `--from-stage modeling_council` |
| Rerun paper writing only | `--from-stage claim_planning --until-stage final_gatekeeper` |
| Stop before packaging | `--until-stage final_gatekeeper` |

### `mcm-agent package`

Creates final zip artifacts for a reviewed workspace.

```bash
mcm-agent package /tmp/mcm_agent_task
```

If `paper/main.pdf` or other package prerequisites are missing, the command writes `final_submission/submission_blocked.md` and exits non-zero instead of pretending the package is complete.

### `mcm-agent provider-status`

Shows which configured providers will be used.

```bash
mcm-agent provider-status --config-file mcm_agent_config.local.json
```

Use it after editing config to confirm LLM, search, extraction, official data, MinerU, and humanizer selection.

### `mcm-agent provider-smoke`

Runs real provider connectivity checks without printing secrets.

```bash
mcm-agent provider-smoke \
  --config-file mcm_agent_config.local.json \
  --workspace .smoke
```

Check a subset:

```bash
mcm-agent provider-smoke \
  --config-file mcm_agent_config.local.json \
  --providers llm,tavily,firecrawl,fred
```

Include MinerU parsing:

```bash
mcm-agent provider-smoke \
  --config-file mcm_agent_config.local.json \
  --mineru-file /path/to/sample.pdf
```

Smoke tests may call paid or rate-limited services, so they are manual and not part of the normal pytest suite.

### `mcm-agent emit` and `mcm-agent approve-checkpoint`

Lower-level workflow controls.

```bash
mcm-agent emit /tmp/mcm_agent_task user_review_requested
mcm-agent approve-checkpoint /tmp/mcm_agent_task checkpoint_001
```

Use these when experimenting with checkpoint behavior or building UI controls around the coordinator.

### `mcm-agent gui`

Starts the local web GUI (static frontend + Workflow Control API) on FastAPI.

```bash
mcm-agent gui --host 127.0.0.1 --port 8787
```

Open `http://127.0.0.1:8787` in a browser. The GUI is zero-build (FastAPI-served HTML + Alpine.js + Server-Sent Events; no Node/build step) and has six screens: Settings, Knowledge Base, Task Upload, Discussion/Planning, Run Monitor (live stage timeline + log stream + checkpoint approval), and Artifacts. It drives the same workflow as the CLI via the Workflow Control API (run/resume/stop/approve/events/logs).

---

## Configuration

The preferred runtime contract is one local JSON file:

```bash
cp mcm_agent_config.example.json mcm_agent_config.local.json
```

`mcm_agent_config.local.json` is ignored by git. Commit only `mcm_agent_config.example.json`.

Top-level sections:

| Section | Purpose |
|---|---|
| `llm` | OpenAI-compatible API key, base URL, model name, and timeout. |
| `search` | Tavily, Firecrawl, Brave Search, and Exa API keys. |
| `official_data` | FRED, US Census, NOAA keys and public data base URLs. |
| `mineru` | Fake, local CLI, or REST document parsing mode. |
| `humanizer` | UShallPass-compatible humanization settings. |
| `rag` | Local knowledge-base directory and ingest extensions. |
| `embedding` | RAG v2 embedding/rerank: provider (`voyage`/`fake`), API key, base URL, embedding + rerank model names. Empty key falls back to deterministic fakes. |
| `runtime` | Default language, retries, HTTP timeout, and code timeout. |

Supported provider smoke IDs:

```text
llm, tavily, brave, exa, firecrawl, humanizer, mineru,
world_bank, oecd, undata, fred, us_census, noaa,
nasa_power, open_meteo, overpass, embedding
```

`.env` remains supported through `--env-file` for older setups. When both `.env` and JSON config are supplied, JSON values win.

---

## RAG Knowledge Base

The repository intentionally commits an empty folder:

```text
knowledge_base/
└── .gitkeep
```

User files under `knowledge_base/` are ignored by git. A practical layout is:

```text
knowledge_base/
├── contest_rules/
│   └── mcm_rules.pdf
├── methods/
│   ├── topsis_notes.md
│   └── network_flow_examples.txt
└── papers/
    └── 2024_problem_c/
        ├── problem.pdf
        ├── data/
        └── excellent_paper.pdf
```

During `methodology_rag`, `.md` and `.txt` files are chunked directly. `.pdf` files are parsed through MinerU when available. Retrieval is **hybrid**: keyword (SQLite FTS) and semantic (vector) candidates are merged and reranked to the top results. When an `embedding` provider key (Voyage) is configured, real embeddings + reranking are used and embeddings are cached by content hash; otherwise deterministic fake providers keep the full path working offline. Retrieved chunks are written to `rag/methodology_hits.json` with provenance fields and rerank scores.

RAG materials guide modeling and writing patterns. They are not automatically treated as verified factual sources; factual claims still need registered sources and evidence.

---

## Workspace Artifacts

Key files created during a run:

| Path | Purpose |
|---|---|
| `input/` | Copied problem, attachments, templates, and user notes. |
| `parsed/problem.md` | Parsed problem text used by downstream agents. |
| `reports/problem_understanding.md` | Task decomposition and assumptions. |
| `reports/data_feasibility_report.md` | Data availability and proxy analysis. |
| `discussion/confirmed_direction.md` | Human/agent direction lock. |
| `rag/methodology_hits.json` | Retrieved local method and paper-writing guidance. |
| `reports/experiment_spec.json` | Model route, solver modules, inputs, outputs, and metrics. |
| `data/source_registry.json` | Stable source records for citations and evidence. |
| `data/retrieval_log.jsonl` | Search and extraction trace. |
| `results/model_route_summary.json` | Route execution and binding status. |
| `results/evidence_registry.json` | Numerical evidence available to the paper. |
| `figures/figure_registry.json` | Figure metadata, source scripts, and paper targets. |
| `paper/claim_plan.json` | Claim-level argument plan. |
| `paper/main.tex` | Generated LaTeX paper. |
| `paper/references.bib` | Source-backed bibliography. |
| `review/*.json` | Machine-readable QA gates and repair decisions. |
| `final_submission/` | Submission package, source zip, checklist, AI use report, or blocked report. |

---

## Local GUI API

Start the server:

```bash
mcm-agent gui --host 127.0.0.1 --port 8787
```

The browser app is served at `/` (static assets under `/static`). It talks to these endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /` | Serve the GUI shell (`/static/*` for assets). |
| `GET /api/health` | Health check. |
| `GET /api/config` | Read masked runtime config. |
| `POST /api/config` | Save local runtime config (merge-based; never clobbers stored secrets). |
| `POST /api/config/test-provider` | Test one provider through the smoke layer. |
| `POST /api/workspaces` | Create a workspace under `.mcm_agent_workspaces`. |
| `GET /api/workspaces` | List local workspaces. |
| `POST /api/workspaces/{id}/files` | Upload problem, attachment, template, or chat files. |
| `GET /api/workspaces/{id}/status` | Read task state, failed gate, and recent stages. |
| `POST /api/workspaces/{id}/run` | Start a run (background thread; `demo`/`auto_approve`/`from_stage`/`until_stage`). |
| `POST /api/workspaces/{id}/resume` | Resume a run from a stage or saved state. |
| `POST /api/workspaces/{id}/stop` | Request a cooperative stop. |
| `GET /api/workspaces/{id}/run` | Run status: state, duration, pending checkpoint, error. |
| `POST /api/workspaces/{id}/checkpoints/{checkpoint_id}/approve` | Approve a paused checkpoint and resume. |
| `GET /api/workspaces/{id}/events` | Server-Sent Events stream of stage/log/gate/checkpoint events. |
| `GET /api/workspaces/{id}/logs` | Recent stage records (SSE backfill / polling). |
| `GET /api/workspaces/{id}/artifacts` | List generated artifacts. |
| `GET /api/workspaces/{id}/artifacts/content` | Read a text artifact. |
| `GET /api/workspaces/{id}/artifacts/download` | Download an artifact. |
| `GET /api/knowledge/files` | List knowledge-base files with ingest-eligibility. |
| `POST /api/knowledge/files` | Upload files into `knowledge_base/`. |
| `DELETE /api/knowledge/files` | Delete a knowledge-base file. |
| `GET /api/knowledge/index-preview` | Offline dry-run of RAG ingestion (chunk counts). |

---

## Project Layout

```text
MCM-ICM-Agent/
├── mcm_agent_config.example.json
├── knowledge_base/
├── examples/demo_mcm_task/
├── scripts/
│   ├── run_demo_task.py
│   └── smoke_providers.py
├── src/mcm_agent/
│   ├── agents/
│   ├── core/
│   ├── providers/
│   ├── server/
│   ├── solver_modules/
│   ├── templates/
│   └── workflows/
├── tests/
└── docs/
```

Important docs:

| Document | Use it for |
|---|---|
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | Operational guide, stage order, workspace structure, gates, and failure recovery. |
| [docs/AGENT_TOPOLOGY.md](docs/AGENT_TOPOLOGY.md) | Agent graph, responsibilities, and repair routing. |
| [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) | Current implementation state and remaining gaps. |
| [docs/DESIGN.md](docs/DESIGN.md) | Long-form architecture and product design. |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Historical and future implementation plan. |

---

## Verification

Focused README and server checks:

```bash
python -m pytest tests/test_docs.py tests/test_server_config.py tests/test_server_workspace.py -q
```

Full test suite:

```bash
python -m pytest -q
```

Lint:

```bash
ruff check src tests scripts
```

---

## Maturity

MCM-ICM Agent is an active research prototype. It has a real workflow, a real artifact contract, and extensive tests, but it is not an automatic contest-winning system.

Human review is still required for problem interpretation, model validity, data assumptions, numerical correctness, citation quality, paper style, final compliance, and official submission decisions.
