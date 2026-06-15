# MCM-ICM Agent

CLI-first reference implementation for an MCM/ICM math modeling agent.

The project is built around a traceable workflow: every document parse, data source,
modeling result, figure, paper section, humanization step, and review finding is written
to a task workspace.

## Quick Start

```bash
python -m pip install -e ".[dev]"
cp mcm_agent_config.example.json mcm_agent_config.local.json
mcm-agent version
mcm-agent run-demo /tmp/mcm_agent_demo --auto-approve
mcm-agent status /tmp/mcm_agent_demo
```

Run a real task input with the configured providers:

```bash
mcm-agent run /tmp/mcm_agent_task \
  --config-file mcm_agent_config.local.json \
  --problem-file /path/to/problem.pdf \
  --attachment /path/to/data.csv \
  --auto-approve
```

Use repeated `--attachment` flags for multiple files. Omit `--auto-approve` when you
want the generated checkpoints to stay pending for human review.

Inspect or resume an existing workspace:

```bash
mcm-agent inspect /tmp/mcm_agent_task

mcm-agent resume /tmp/mcm_agent_task \
  --config-file mcm_agent_config.local.json \
  --problem-file /path/to/problem.pdf \
  --attachment /path/to/data.csv \
  --from-stage validation_gate \
  --until-stage final_gatekeeper \
  --auto-approve
```

`inspect` reports the current phase, recent stage runs, failed gate, repair stage, and
unresolved issue status. `resume` uses the same graph-aware executor as `run`; if
`--from-stage` is omitted, it starts from the blocked repair stage or current phase in
`task_state.json`.

Run the bundled MCM-style example task:

```bash
python scripts/run_demo_task.py --workspace .demo_workspace --clean
```

The example lives in `examples/demo_mcm_task/` and includes a problem statement, a small
district-level flood response dataset, a user idea file, methodology excerpts, and an
expected outputs checklist. The script writes `.demo_workspace/demo_run_report.md` after
the run.

## Runtime Shape

The implementation uses a workspace per contest task. Each workspace stores inputs, parsed
documents, reports, data, evidence, figures, paper files, review outputs, and final submission
artifacts. Agents communicate through typed artifact records, event logs, and handoff packets.

For the full operational guide, including workspace folders, agent stages, gate repair
flow, and common failure modes, see [Workflow guide](docs/WORKFLOW.md).

## Runtime Configuration

The preferred runtime contract is one local JSON file:

```bash
cp mcm_agent_config.example.json mcm_agent_config.local.json
```

Fill `mcm_agent_config.local.json` with the LLM model, provider API keys, MinerU mode,
humanizer settings, runtime limits, and RAG settings you want to use. This local file is
ignored by git; the repository commits only `mcm_agent_config.example.json`.

The recommended MVP stack is:

- LLM provider through an OpenAI-compatible API.
- Tavily API as the primary search provider, with Brave and Exa as fallback search providers.
- Firecrawl API for web extraction.
- MinerU local mode or official REST precision API for PDF parsing.
- UShallPass for academic humanization, guarded by fact regression checks.

Then check the active provider selection:

```bash
mcm-agent provider-status --config-file mcm_agent_config.local.json
```

Expected once the first three providers are configured:

```text
LLM: openai-compatible (<your model>)
Search: Tavily API
Extract: Firecrawl API
MinerU: fake
Humanizer: fake
```

When multiple search keys are configured, the runtime tries Tavily first, then Brave,
then Exa. Official data repair can use World Bank, OECD, UNData, NASA POWER,
Open-Meteo, and OSM/Overpass without keys. FRED requires `official_data.fred_api_key`.
US Census works without a key for low-volume use but supports
`official_data.us_census_api_key`. NOAA uses `official_data.noaa_api_key` when configured.
All provider keys and base URLs live under `official_data` in the local JSON config.

`.env` loading remains supported for compatibility through `--env-file`, but JSON values
win when both `--env-file` and `--config-file` are passed.

## RAG Knowledge Base

The repository includes an empty `knowledge_base/` folder. Only `knowledge_base/.gitkeep`
is tracked; user-added papers, notes, and rules are ignored by git.

You can add local files such as:

```text
knowledge_base/methods/network_flow.md
knowledge_base/methods/topsis_notes.txt
knowledge_base/rules/contest_rules.pdf
```

During the `methodology_rag` stage, `.md` and `.txt` files are chunked into the SQLite
FTS methodology store. `.pdf` files are parsed through the configured MinerU provider
when available; if MinerU is not configured or parsing fails, the PDF is reported in
`rag/retrieval_notes.md` without blocking the workflow. Unsupported suffixes are
reported as skipped.

Each retrieved row in `rag/methodology_hits.json` includes `source_type`,
`relative_path`, `chunk_id`, `page_hint`, and `usage`. These local knowledge-base
documents guide modeling and writing patterns; they are not treated as external factual
data sources.

## Claim-Aware Paper Quality

The paper pipeline now builds a compact paper context from problem understanding, confirmed
direction, model decisions, validation, RAG hits, evidence, figures, and sources. That
context enriches `paper/claim_plan.json` with assumption, model-choice, result,
sensitivity, limitation, and conclusion claims.

When a claim plan exists, `PaperWriterAgent` renders contextual abstract, introduction,
assumptions, model, results, sensitivity, and conclusion sections. `ReviewerAgent` writes
`review/paper_quality_scores.json` with section completeness and claim trace density, and
routes incomplete papers back to `paper_writer`.

## Source Citations

The writing pipeline maps `source_id` values to BibTeX keys through
`data/citation_candidates.json`. Source-backed planned claims include source-specific
`\cite{...}` commands in the generated LaTeX while preserving trace comments such as
`source_id=web_001`.

`ReferenceManager` writes `paper/references.bib`, inserts citations for existing
`source_id=` markers, and reports a source-to-bibliography mapping in
`review/reference_audit_report.md`. `PaperEvidenceBindingAgent` records citation keys in
`review/paper_evidence_bindings.json` so reviewers can trace prose citations back to
registered sources.

## Concept Diagrams And Figures

Figure planning now creates both data plots and artifact-derived concept diagrams. The
method overview and claim-evidence map are built from route summaries, evidence, sources,
and `paper/claim_plan.json`, so they explain the actual workflow rather than decorating
the paper.

Concept diagrams write reproducible Mermaid source to `figures/source/*.mmd` and
deterministic SVG outputs to `figures/*.svg`. `FigureQualityAgent` checks concept
diagrams for a Mermaid source file, vector output, caption intent, and target section
before the workflow proceeds to claim planning.

## Automatic LaTeX Repair

The typesetting stage now runs deterministic, pattern-limited LaTeX repair after QA
finds safe formatting issues. It can wrap wide `tabular` environments, add width limits
to unscaled `\includegraphics` calls, and wrap long plain `equation` bodies in `split`
when they are not already using a multi-line math environment.

The workflow performs one repair pass, recompiles, and reruns typesetting QA. Repair
evidence is written to `review/typesetting_repair.json` and
`review/typesetting_repair_report.md`, and the QA markdown includes the repair summary.
Complex compile errors, missing source figures, page-limit problems, and unsafe layout
failures still route through the final gate for targeted stage repair or human review.

## Real Modeling Capability

Model selection now uses a recipe library for common MCM/ICM archetypes. Each recipe
defines the route ID, solver module, method, expected outputs, metrics, column-binding
contract, and paper-writing guidance. Current routes include multi-criteria evaluation,
constrained optimization, forecasting, Monte Carlo simulation, classification,
clustering/segmentation, queueing service analysis, network flow/graph structure, and
multi-objective decision support.

`reports/experiment_spec.json` records `route_plan` metadata, execution order, route
roles, solver modules, input requirements, expected outputs, metrics, and column-binding
contracts. `SolverCoderAgent` executes compatible deterministic solver modules and writes
`results/model_route_summary.json`, including `route_execution_status` values such as
`executed`, `blocked_missing_binding`, and `attempted_no_metric`.

`reports/model_candidates.md` includes a solver blueprint for each diagnosed route.
Executable route outputs now include `results/classification_results.csv`,
`results/cluster_segments.csv`, and `results/queue_summary.csv` when those recipes are
selected. These modules are contest-safe deterministic baselines, not unrestricted
arbitrary code generation.

Validation treats binding-driven weak-model failures as modeling-spec problems and routes
them back to `modeling_council`, while solver execution failures still route to the solver
stage. The workflow test suite includes forecast + simulation + network and
classification + clustering + queueing archetypes.

Setting `mineru.mode` to `rest` uses MinerU's precision API flow: create an upload batch,
upload the local PDF to the returned URL, poll the batch result, download the result zip,
and persist `problem.md`, `problem.json`, `problem_layout.json`, and `formulas.json` into
the task workspace.

### Provider Smoke Tests

Smoke tests are manual checks for real API connectivity. They are intentionally not part
of the normal pytest suite.

```bash
python scripts/smoke_providers.py \
  --config-file mcm_agent_config.local.json \
  --workspace .smoke
```

The same checks are available through the installed CLI:

```bash
mcm-agent provider-smoke \
  --config-file mcm_agent_config.local.json \
  --workspace .smoke
```

To include a real MinerU parse check, provide a small local PDF:

```bash
mcm-agent provider-smoke \
  --config-file mcm_agent_config.local.json \
  --workspace .smoke \
  --mineru-file /path/to/sample.pdf
```

Smoke output reports `PASSED`, `SKIPPED`, or `FAILED` for configured LLM, Tavily,
Brave, Exa, Firecrawl, UShallPass, MinerU, and official-data checks. Missing optional
keys are reported as `SKIPPED`; actual API or response failures return a non-zero exit
code.

## Verification

```bash
ruff check src tests
pytest -v
```

## Design Docs

- [System design](docs/DESIGN.md)
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [Agent topology](docs/AGENT_TOPOLOGY.md)
- [Workflow guide](docs/WORKFLOW.md)
- [Implementation roadmap](docs/superpowers/plans/2026-06-13-mcm-agent-implementation-roadmap.md)
