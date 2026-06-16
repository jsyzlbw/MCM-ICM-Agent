# MCM/ICM Agent Project Status

Status date: 2026-06-17

This document records the implementation state of the repository at
`/Users/mac/Programming/MCM-ICM-Agent`. It is the source of truth for what has
actually been built, while `DESIGN.md` remains the system design and
`IMPLEMENTATION_PLAN.md` tracks the next build phases.

## Verification Snapshot

Latest verified local commands:

```bash
pytest -q
# 310 passed

ruff check src tests
# All checks passed
```

Latest implementation commit at the time this status was written:

```text
8f1da81 test: include embedding section in example-config assertion
```

Since the 2026-06-15 snapshot, three major capabilities landed (all on `main`,
fake-provider tested, no real keys required):

- **Workflow Control API** — operate runs over HTTP, not just inspect files.
- **Zero-build GUI** — a 6-screen local web app served by `mcm-agent gui`.
- **RAG v2** — hybrid FTS + vector retrieval with reranking (Voyage + chromadb), fake-provider offline.

## Implemented

| Area | Status |
| --- | --- |
| Python package, CLI, JSON configuration, tests, ruff | Implemented |
| Workspace initialization and runtime registries | Implemented |
| Artifact registry, event log, handoff packets | Implemented |
| Workflow topology and graph-aware stage executor | Implemented |
| Gate decision contract and gate routing | Implemented |
| MinerU provider modes: fake, local, REST | Implemented |
| OpenAI-compatible LLM provider and fake provider | Implemented |
| Search providers: Tavily, Firecrawl, Brave, Exa, fallback stack | Implemented |
| UShallPass provider and fake humanizer | Implemented |
| Intake and document extraction agents | Implemented |
| Problem Understanding Agent | Implemented |
| Data Feasibility Scout Agent | Implemented |
| User Discussion Agent with data feasibility feedback | Implemented |
| Research Reframing Agent for unavailable/private data | Implemented |
| Modeling Council and Model Judge | Implemented |
| Model recipe library and hybrid route planning for evaluation, optimization, forecasting, simulation, classification, clustering, queueing, network, and multi-objective tasks | Implemented |
| Modeling Plan Quality Agent | Implemented |
| Search & Data Agent with source registry, retrieval log, lineage, citation candidates | Implemented |
| Supervisor-Skills methodology RAG import skeleton | Implemented |
| Local `knowledge_base/` RAG ingestion for `.md`, `.txt`, and MinerU-parsed `.pdf` with chunk provenance and usage restrictions | Implemented |
| Multi-query methodology RAG for paper quality | Implemented |
| Data/EDA Agent | Implemented |
| Solver/Coder Agent, deterministic solver modules, experiment runner, evidence registry | Implemented |
| Validation Agent and validation gate | Implemented |
| Figure planning, vector-first data visualization, artifact-derived concept diagrams, figure quality gate | Implemented |
| Claim Planning Agent and `paper/claim_plan.json` | Implemented with paper-context-aware assumptions, model, result, sensitivity, limitation, and conclusion claims |
| Paper Writer Agent | Implemented as contextual claim-plan-aware writer |
| Reference Manager and source-to-BibTeX reference audit | Implemented |
| Typesetting QA plus deterministic one-pass LaTeX repair for safe table, graphic, and equation patterns | Implemented |
| Paper Evidence Binding Agent | Implemented with section-level, claim-level, and planned-claim coverage checks |
| Compliance & Originality Agent with fact regression check | Implemented as MVP |
| Reviewer, Revision, Submission Packager | Implemented with claim-plan blockers and paper-quality scoring |
| Provider smoke CLI for LLM, search, extraction, MinerU, humanizer, and official-data checks | Implemented |
| End-to-end fake-provider workflow tests | Implemented |
| Workflow Control API: threaded run registry + `run`/`resume`/`stop`/`run-status`/checkpoint-`approve`/`events` (SSE)/`logs` endpoints, with a cooperative pause/stop hook in the stage executor | Implemented |
| Zero-build local GUI (FastAPI static + Alpine.js + SSE): Settings, Knowledge Base, Task Upload, Discussion/Planning, Run Monitor, Artifacts | Implemented |
| Secret-safe config round-trip (`merge_config`) so the masked Settings screen never clobbers stored keys | Implemented |
| Knowledge-base file manager API (list/upload/delete + offline index preview) | Implemented |
| RAG v2: hybrid FTS + vector retrieval with reranking; Voyage embedding/rerank providers + deterministic fakes; content-hash embedding cache; chroma vector index | Implemented |

## Partially Implemented

| Area | Current capability | Remaining work |
| --- | --- | --- |
| Real automatic modeling | Selects recipe-driven hybrid route plans, writes route-aware experiment specs, emits solver blueprints, executes deterministic route modules for evaluation, optimization, forecasting, simulation, classification, clustering, queueing, and network tasks, records route execution status, and routes binding-driven weak-model failures to modeling repair | Generate stronger problem-specific model code for arbitrary MCM/ICM tasks |
| Claim-level paper evidence | Checks `claim_id`, `evidence_id`, `figure_id`, `source_id`, citation keys, planned critical/major claim coverage, and reviewer quality scores | Improve claim taxonomy and richer repair routing for ambiguous missing support |
| Paper writing | Produces contextual traceable LaTeX sections from `paper/claim_plan.json` with source-specific citations when present | Add optional style variants |
| RAG | Hybrid retrieval: FTS (keyword) ∪ vector (semantic) candidates reranked to top-K; Voyage embedding/rerank when an `embedding` key is configured, deterministic fakes otherwise; content-hash embedding cache; per-workspace chroma index built during `methodology_rag` | Real-provider (Voyage) end-to-end run; tuning `fts_n`/`vec_n`/`top_k`; optional structured "case" knowledge schema |
| Official data APIs | Provider pattern plus World Bank, OECD, UNData, FRED, US Census, NOAA, NASA POWER, Open-Meteo, and OSM/Overpass repair adapters with mocked tests and smoke checks | Add richer provider-specific query planning |
| Visualization | Generates vector-first data figures, Mermaid source concept diagrams, deterministic SVG concept outputs, and QA reports | Add richer diagram styling/export polish if needed |
| LaTeX | Generates, compiles through provider abstraction, runs deterministic typesetting QA, applies one conservative source-repair pass for safe table, graphic, and equation patterns, recompiles, and records repair artifacts | Add richer repair coverage for complex page-limit and float-placement failures |
| Humanization | Calls UShallPass or fake provider and performs fact-lock regression | Add privacy policy switches, batch job logs, retry reports, and user approval gates |
| User interaction | Local web GUI (6 screens) over the Workflow Control API: configure providers, manage the knowledge base, upload a task, run/resume/stop, watch live SSE progress, approve pause checkpoints, browse artifacts | In-browser visual/UX verification; richer human-in-the-loop (edit/regenerate/ask) and free-form discussion |
| Provider smoke tests | `mcm-agent provider-smoke` and `scripts/smoke_providers.py` read `--config-file`, check configured live providers, and report skipped missing keys | Add an `embedding` (Voyage) smoke check; richer paid-provider cost controls and batch smoke history |

## Not Yet Built

- Automatic LaTeX source repair for complex page-limit, float-placement, template-specific, and semantic compile issues.
- Hosted/multi-user service: authentication, billing, or SaaS deployment (the GUI today is local single-user).
- Verified real-provider end-to-end run (the workflow + GUI + RAG v2 are tested with fake/demo providers; a small real-key run is the next validation).
- Any guarantee of contest award level.

## Current Architecture Reality

The implementation is no longer just the initial linear MVP. It now follows this stronger loop:

```text
Problem Understanding
        ↓
Data Feasibility Scout
        ↓
Research Reframing if critical data is private or unavailable
        ↓
User Discussion and Direction Lock
        ↓
Modeling, Search, RAG, EDA, Solver, Validation
        ↓
Figure Planning and Vector-first Visualization
        ↓
Claim Planning for paper arguments
        ↓
Paper Writing with claim-level evidence traces
        ↓
References, Humanization, Review, Revision, Submission Packaging
```

The most important implemented safety property is evidence governance:

- External sources enter `data/source_registry.json`.
- Search and extraction actions enter `data/retrieval_log.jsonl`.
- External data facts enter `data/data_lineage.json`.
- Citation candidates enter `data/citation_candidates.json`.
- Model outputs enter `results/evidence_registry.json`.
- Figures enter `figures/figure_registry.json`.
- Planned paper claims enter `paper/claim_plan.json`.
- Paper claims are checked through `review/paper_evidence_bindings.json`.
- Paper quality scores enter `review/paper_quality_scores.json`.
- Typesetting QA enters `review/typesetting_quality.json` and can route `format_issue`
  failures to `typesetting`, `paper_writer`, or `visualization`.
- Typesetting repair enters `review/typesetting_repair.json` and
  `review/typesetting_repair_report.md`; when source changes, the workflow recompiles
  once and reruns typesetting QA.
- Runtime configuration is loaded from `mcm_agent_config.local.json` when passed with
  `--config-file`; `.env` remains backward compatible.
- Local methodology notes, rules, paper examples, and MinerU-parsed PDFs in
  `knowledge_base/` are ingested during `methodology_rag` with chunk-level provenance.

## Recommended Next Build Phase

The operable GUI, Workflow Control API, and hybrid RAG now exist and are
fake-provider tested. The next steps shift toward real-world validation and
depth:

1. **Real-provider end-to-end** — run a small real task (real LLM + Voyage +
   data providers) through the GUI; fix real-mode issues surfaced (cooperative
   stop only acts between stages; missing-config currently falls back to demo).
2. **In-browser GUI verification + polish** — click through the 6 screens,
   confirm SSE live updates and checkpoint approval, refine layout.
3. **Stronger problem-specific modeling/code generation** — move beyond
   deterministic recipe baselines (the deepest remaining capability gap).

The planning, modeling, RAG (now hybrid), official-data, paper, automatic
typesetting repair, provider-readiness, and operable-GUI foundations now exist.
Design specs and task-by-task plans for the recent work live under
`docs/superpowers/specs/` and `docs/superpowers/plans/`.
