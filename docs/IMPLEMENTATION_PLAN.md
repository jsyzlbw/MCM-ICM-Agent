# MCM/ICM Agent Implementation Plan

Status date: 2026-06-15

This plan reflects the current repository at `/Users/mac/Programming/MCM-ICM-Agent`.
The earlier `MathModelAgentDesign/reference_implementation/` layout has been superseded:
the implementation now lives at the repository root.

For current implementation status, see `docs/PROJECT_STATUS.md`.

## 0. Current Baseline

The repository already contains a tested MVP with:

- CLI-first Python package under `src/mcm_agent/`.
- Workspace, artifact registry, event log, handoff packets, workflow topology, and stage executor.
- Provider adapters for LLM, MinerU, Tavily, Firecrawl, Brave, Exa, UShallPass, LaTeX, academic APIs, and official data APIs.
- Core agents for intake, extraction, problem understanding, data feasibility, discussion, reframing, modeling, search, RAG, EDA, solver, validation, visualization, claim planning, writing, compliance, review, revision, reference management, and submission packaging.
- Source governance through `source_registry.json`, `retrieval_log.jsonl`, `data_lineage.json`, and `citation_candidates.json`.
- Modeling evidence through `experiment_runs.jsonl`, `model_metrics.json`, `model_route_summary.json`, and `evidence_registry.json`.
- Vector-first figure planning and figure QA.
- Claim planning through `paper/claim_plan.json`.
- Paper evidence binding at section level, claim level, and planned-claim coverage level.
- Fake-provider end-to-end workflow tests.

Latest verified baseline:

```bash
pytest -q
# 225 passed

ruff check src tests scripts
# All checks passed
```

## 1. Current Repository Layout

```text
MCM-ICM-Agent/
├── README.md
├── pyproject.toml
├── .env.example
├── mcm_agent_config.example.json
├── knowledge_base/
│   └── .gitkeep
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

`mcm_agent_config.example.json` is the preferred public runtime configuration contract.
Copy it to `mcm_agent_config.local.json`, fill only the providers you want to use, and pass
it with `--config-file`. The local JSON file is ignored by git and may contain plaintext
API keys for local use.

```bash
cp mcm_agent_config.example.json mcm_agent_config.local.json
mcm-agent provider-status --config-file mcm_agent_config.local.json
```

The config sections are `llm`, `search`, `official_data`, `mineru`, `humanizer`, `rag`,
and `runtime`. `.env.example` and `--env-file` remain backward compatible, but JSON values
override env-file values when both are supplied.

Rules:

- Do not commit `.env`, `mcm_agent_config.local.json`, or real secrets.
- Do not commit user-filled `knowledge_base/*`; only `knowledge_base/.gitkeep` is tracked.
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
| P9 Claim planning and claim-plan enforcement | Complete as MVP |
| A1 Unified JSON runtime config | Complete |
| A2 User-fillable RAG knowledge base base | Complete as MVP |
| B1 High-quality claim-aware paper generation | Complete as MVP |
| C1 Real modeling capability expansion | Complete as MVP |
| D1 Official data API expansion | Complete as MVP |
| E1 RAG ingestion expansion | Complete |

## 4. Active Next Phase

The active next phase is **LaTeX Layout QA and Provider Smoke Expansion**.

Purpose:

The system now stores sources, data lineage, evidence, figures, references, claim plans,
contextual paper sections, claim-level paper bindings, paper-quality scores, hybrid route
plans, route-aware experiment specs, route execution status, official-data repair
records, and provenance-aware local RAG entries across the main provider families. The
remaining work is to harden final paper production and make live provider readiness easy
to check.

Current core artifact:

```text
review/typesetting_report.md
review/final_gate.json
provider smoke output
```

Current implemented flow:

```text
paper/main.tex + figures + references
        ↓
LaTeX compile provider
        ↓
typesetting and layout QA
        ↓
repair routing notes for writer / visualization / typesetting
        ↓
final gate and submission package
```

## 5. Next Phase Tasks

### Task 1: Add LaTeX Layout QA

Inputs:

- `paper/main.tex`
- `paper/main.pdf` when available
- `paper/compile_log.txt` or provider compile logs
- contest page-limit and formatting assumptions

Target behavior:

- Detect compile errors, missing PDF output, page-limit issues, table overflow, equation
  overflow, and figure placement risks.
- Write a machine-readable layout QA report that the final gate can inspect.
- Preserve the current provider abstraction so fake tests do not require a real LaTeX
  installation.

### Task 2: Add Repair Routing For Typesetting Issues

Target behavior:

- Route compile and equation issues back to typesetting or writer repair.
- Route figure placement and figure file issues back to visualization or figure quality.
- Keep user-facing reports concise enough to act on during a contest.

### Task 3: Expand Provider Smoke

Target behavior:

- Provide one CLI command for configured provider smoke checks.
- Report configured, skipped, passed, and failed providers without exposing secrets.
- Include LLM, Tavily, Firecrawl, Brave, Exa, MinerU, UShallPass, and official-data
  providers where a low-cost smoke check is available.

## 6. Later Build Phases

After the official data API phase, continue with these quality phases:

1. **Concept Diagram System**
   - Add Mermaid, Graphviz, and TikZ concept figure generation.
   - Keep final concept diagrams vector-first.

2. **LaTeX Layout QA**
   - Detect compile errors, table overflow, equation overflow, figure placement issues, and page-limit violations.
   - Route layout failures back to writer, visualization, or typesetting.

3. **Provider Smoke Expansion**
   - The manual smoke script now reads `--config-file` and checks configured live providers.
   - Later work can broaden it into a first-class CLI command and include additional official-data providers.

## 7. Operating Rules

- Use TDD for behavior changes.
- Keep commits small and independently useful.
- Do not call paid or live APIs in unit tests.
- Never commit `.env`, `mcm_agent_config.local.json`, or secrets.
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
