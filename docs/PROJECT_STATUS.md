# MCM/ICM Agent Project Status

Status date: 2026-06-15

This document records the implementation state of the repository at
`/Users/mac/Programming/MCM-ICM-Agent`. It is the source of truth for what has
actually been built, while `DESIGN.md` remains the system design and
`IMPLEMENTATION_PLAN.md` tracks the next build phases.

## Verification Snapshot

Latest verified local commands:

```bash
pytest -q
# 266 passed

ruff check src tests scripts
# All checks passed
```

Latest implementation commit at the time this status was written:

```text
f7769ea feat: execute new modeling recipe routes
```

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
| Typesetting QA for compile errors, missing PDF, page-limit hints, table/equation/figure risks | Implemented |
| Paper Evidence Binding Agent | Implemented with section-level, claim-level, and planned-claim coverage checks |
| Compliance & Originality Agent with fact regression check | Implemented as MVP |
| Reviewer, Revision, Submission Packager | Implemented with claim-plan blockers and paper-quality scoring |
| Provider smoke CLI for LLM, search, extraction, MinerU, humanizer, and official-data checks | Implemented |
| End-to-end fake-provider workflow tests | Implemented |

## Partially Implemented

| Area | Current capability | Remaining work |
| --- | --- | --- |
| Real automatic modeling | Selects recipe-driven hybrid route plans, writes route-aware experiment specs, emits solver blueprints, executes deterministic route modules for evaluation, optimization, forecasting, simulation, classification, clustering, queueing, and network tasks, records route execution status, and routes binding-driven weak-model failures to modeling repair | Generate stronger problem-specific model code for arbitrary MCM/ICM tasks |
| Claim-level paper evidence | Checks `claim_id`, `evidence_id`, `figure_id`, `source_id`, citation keys, planned critical/major claim coverage, and reviewer quality scores | Improve claim taxonomy and richer repair routing for ambiguous missing support |
| Paper writing | Produces contextual traceable LaTeX sections from `paper/claim_plan.json` with source-specific citations when present | Add optional style variants |
| RAG | Imports selected Supervisor-Skills documents plus local `.md`, `.txt`, and MinerU-parsed `.pdf` files from `knowledge_base/` into SQLite FTS; retrieves paper-quality query types with source type, relative path, chunk id, page hint, and usage restrictions | Add richer source-specific query planning and citation-style guidance for local method libraries |
| Official data APIs | Provider pattern plus World Bank, OECD, UNData, FRED, US Census, NOAA, NASA POWER, Open-Meteo, and OSM/Overpass repair adapters with mocked tests and smoke checks | Add richer provider-specific query planning |
| Visualization | Generates vector-first data figures, Mermaid source concept diagrams, deterministic SVG concept outputs, and QA reports | Add richer diagram styling/export polish if needed |
| LaTeX | Generates, compiles through provider abstraction, and runs deterministic typesetting QA for compile/layout risks | Add automatic LaTeX source repair beyond routing reports |
| Humanization | Calls UShallPass or fake provider and performs fact-lock regression | Add privacy policy switches, batch job logs, retry reports, and user approval gates |
| User interaction | File/CLI-oriented checkpoints | Add a smoother interactive conversation loop or UI later |
| Provider smoke tests | `mcm-agent provider-smoke` and `scripts/smoke_providers.py` read `--config-file`, check configured live providers, and report skipped missing keys | Add richer paid-provider cost controls and batch smoke history |

## Not Yet Built

- Automatic LaTeX source repair for complex page-limit, figure-placement, table, and equation issues.
- Production UI or hosted service.
- Persistent multi-user authentication, billing, or SaaS deployment.
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
- Runtime configuration is loaded from `mcm_agent_config.local.json` when passed with
  `--config-file`; `.env` remains backward compatible.
- Local methodology notes, rules, paper examples, and MinerU-parsed PDFs in
  `knowledge_base/` are ingested during `methodology_rag` with chunk-level provenance.

## Recommended Next Build Phase

The next phase should focus on deeper contest intelligence.

Build order:

1. Add automatic LaTeX source repair for common formatting failures.
2. Add richer source-specific query planning.
3. Add a smoother interactive user loop or UI for checkpoint decisions.

This is the right next step because the main planning, modeling, RAG, official-data,
paper, typesetting QA, and provider-readiness foundations now exist.
