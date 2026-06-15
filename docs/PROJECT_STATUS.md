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
# 214 passed

ruff check src tests scripts
# All checks passed
```

Latest implementation commit at the time this status was written:

```text
98a4384 test: assert paper quality artifacts in workflow
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
| Modeling Plan Quality Agent | Implemented |
| Search & Data Agent with source registry, retrieval log, lineage, citation candidates | Implemented |
| Supervisor-Skills methodology RAG import skeleton | Implemented |
| Local `knowledge_base/` RAG ingestion for `.md` and `.txt` with PDF pending notes | Implemented as MVP |
| Multi-query methodology RAG for paper quality | Implemented |
| Data/EDA Agent | Implemented |
| Solver/Coder Agent, experiment runner, evidence registry | Implemented |
| Validation Agent and validation gate | Implemented |
| Figure planning, vector-first visualization, figure quality gate | Implemented |
| Claim Planning Agent and `paper/claim_plan.json` | Implemented with paper-context-aware assumptions, model, result, sensitivity, limitation, and conclusion claims |
| Paper Writer Agent | Implemented as contextual claim-plan-aware writer |
| Reference Manager and reference audit | Implemented |
| Paper Evidence Binding Agent | Implemented with section-level, claim-level, and planned-claim coverage checks |
| Compliance & Originality Agent with fact regression check | Implemented as MVP |
| Reviewer, Revision, Submission Packager | Implemented with claim-plan blockers and paper-quality scoring |
| End-to-end fake-provider workflow tests | Implemented |

## Partially Implemented

| Area | Current capability | Remaining work |
| --- | --- | --- |
| Real automatic modeling | Runs deterministic solver modules and records evidence | Generate stronger problem-specific model code for arbitrary MCM/ICM tasks |
| Claim-level paper evidence | Checks `claim_id`, `evidence_id`, `figure_id`, `source_id`, planned critical/major claim coverage, and reviewer quality scores | Improve claim taxonomy and richer repair routing for ambiguous missing support |
| Paper writing | Produces contextual traceable LaTeX sections from `paper/claim_plan.json` when present | Add richer citation insertion and optional style variants |
| RAG | Imports selected Supervisor-Skills documents plus local `.md` and `.txt` files from `knowledge_base/` into SQLite FTS; retrieves paper-quality query types; reports `.pdf` as pending | Add MinerU-backed PDF ingestion, chunking, provenance metadata, and usage restrictions |
| Official data APIs | Includes provider pattern and World Bank example | Expand to OECD, UNData, FRED, US Census, NOAA/NASA/Open-Meteo, OSM/Overpass |
| Visualization | Generates vector-first data figures and QA reports | Add richer concept-diagram generation via Mermaid, Graphviz, TikZ, and Draw.io |
| LaTeX | Generates and compiles through provider abstraction | Add robust compile-error repair, page-limit checks, and layout QA |
| Humanization | Calls UShallPass or fake provider and performs fact-lock regression | Add privacy policy switches, batch job logs, retry reports, and user approval gates |
| User interaction | File/CLI-oriented checkpoints | Add a smoother interactive conversation loop or UI later |
| Provider smoke tests | Manual smoke script reads `--config-file`, checks live LLM/Tavily/Firecrawl/UShallPass/MinerU connectivity, and reports skipped missing keys | Broaden to official-data providers and expose as a first-class CLI command if useful |

## Not Yet Built

- Live, comprehensive official-data API coverage.
- MinerU-backed PDF RAG ingestion for user-uploaded优秀论文 and modeling-method files.
- Advanced LaTeX layout repair for page limits, figure placement, table overflow, and equation overflow.
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
- Runtime configuration is loaded from `mcm_agent_config.local.json` when passed with
  `--config-file`; `.env` remains backward compatible.
- Local methodology notes in `knowledge_base/` are ingested during `methodology_rag`.

## Recommended Next Build Phase

The next phase should focus on `Real Modeling Capability Expansion`.

Build order:

1. Expand model route selection for common MCM/ICM task types.
2. Add stronger solver module orchestration and generated-code contracts.
3. Keep deterministic fallback modules for tests and demos.
4. Strengthen validation so model-specific failures route to the right repair stage.
5. Add tests proving different task archetypes choose different model structures.

This is the right next step because the paper argument chain is now stronger; the next
quality bottleneck is whether the selected model and solver structure fit the problem type.
