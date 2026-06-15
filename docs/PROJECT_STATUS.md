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
# 183 passed

ruff check src tests scripts
# All checks passed
```

Latest implementation commit at the time this status was written:

```text
9d32de7 feat: add claim-level paper evidence bindings
```

## Implemented

| Area | Status |
| --- | --- |
| Python package, CLI, configuration, tests, ruff | Implemented |
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
| Data/EDA Agent | Implemented |
| Solver/Coder Agent, experiment runner, evidence registry | Implemented |
| Validation Agent and validation gate | Implemented |
| Figure planning, vector-first visualization, figure quality gate | Implemented |
| Claim Planning Agent and `paper/claim_plan.json` | Implemented |
| Paper Writer Agent | Implemented as claim-plan-aware MVP writer |
| Reference Manager and reference audit | Implemented |
| Paper Evidence Binding Agent | Implemented with section-level, claim-level, and planned-claim coverage checks |
| Compliance & Originality Agent with fact regression check | Implemented as MVP |
| Reviewer, Revision, Submission Packager | Implemented as MVP with claim-plan final-gate blockers |
| End-to-end fake-provider workflow tests | Implemented |

## Partially Implemented

| Area | Current capability | Remaining work |
| --- | --- | --- |
| Real automatic modeling | Runs deterministic solver modules and records evidence | Generate stronger problem-specific model code for arbitrary MCM/ICM tasks |
| Claim-level paper evidence | Checks `claim_id`, `evidence_id`, `figure_id`, `source_id`, and planned critical/major claim coverage | Improve claim taxonomy and richer repair routing for ambiguous missing support |
| Paper writing | Produces traceable LaTeX sections from `paper/claim_plan.json` when present | Improve full-paper quality, narrative structure, abstract, assumptions, and citations |
| RAG | Imports selected Supervisor-Skills documents into SQLite FTS | Add ingestion for user-uploaded excellent papers, method notes, and competition rules |
| Official data APIs | Includes provider pattern and World Bank example | Expand to OECD, UNData, FRED, US Census, NOAA/NASA/Open-Meteo, OSM/Overpass |
| Visualization | Generates vector-first data figures and QA reports | Add richer concept-diagram generation via Mermaid, Graphviz, TikZ, and Draw.io |
| LaTeX | Generates and compiles through provider abstraction | Add robust compile-error repair, page-limit checks, and layout QA |
| Humanization | Calls UShallPass or fake provider and performs fact-lock regression | Add privacy policy switches, batch job logs, retry reports, and user approval gates |
| User interaction | File/CLI-oriented checkpoints | Add a smoother interactive conversation loop or UI later |
| Provider smoke tests | Basic provider smoke infrastructure exists | Add one command that checks all configured live APIs and reports missing keys clearly |

## Not Yet Built

- Full high-quality MCM/ICM paper generation from a claim plan.
- Live, comprehensive official-data API coverage.
- Full paper-method RAG ingestion from user-uploaded优秀论文 and modeling-method files.
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

## Recommended Next Build Phase

The next phase should focus on `High Quality Claim-Aware Paper Generation`.

Build order:

1. Improve claim-plan generation quality from problem requirements, model route, validation, figures, and data limitations.
2. Upgrade `PaperWriterAgent` templates so each planned claim becomes a coherent paragraph with citations and figure references.
3. Add stronger abstract, introduction, assumptions, model formulation, limitations, and conclusion writing rules.
4. Add richer reviewer scoring for claim importance, narrative completeness, and contest-paper readability.
5. Add tests proving a complete demo paper uses all planned critical claims in the expected sections.

This is the right next step because the repository already has provenance, evidence, figures,
references, claim planning, and review gates. The remaining gap is not whether claims are
traceable, but whether they form a persuasive contest-quality argument.
