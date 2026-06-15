# Workflow Guide

This guide explains how to run, inspect, resume, and audit the MCM/ICM Agent workflow.
It is written for development and early user testing, not as a promise that the system is
contest-ready without human review.

## Command Reference

Install the project in editable mode:

```bash
python -m pip install -e ".[dev]"
cp mcm_agent_config.example.json mcm_agent_config.local.json
```

Run the bundled demo task:

```bash
python scripts/run_demo_task.py --workspace .demo_workspace --clean
```

Run your own task:

```bash
mcm-agent run /tmp/mcm_agent_task \
  --config-file mcm_agent_config.local.json \
  --problem-file /path/to/problem.pdf \
  --attachment /path/to/data.csv \
  --user-idea-file /path/to/user_idea.md \
  --supervisor-skills-dir /path/to/skills \
  --auto-approve
```

Inspect a workspace:

```bash
mcm-agent inspect /tmp/mcm_agent_task
```

Resume from a specific stage:

```bash
mcm-agent resume /tmp/mcm_agent_task \
  --config-file mcm_agent_config.local.json \
  --problem-file /path/to/problem.pdf \
  --attachment /path/to/data.csv \
  --from-stage validation_gate \
  --until-stage final_gatekeeper \
  --auto-approve
```

Package a reviewed workspace after `paper/main.pdf` exists:

```bash
mcm-agent package /tmp/mcm_agent_task
```

The normal `run` and `resume` workflows continue through `submission_packager`. If
`latexmk` is unavailable or `paper/main.pdf` cannot be produced, the workflow writes
`final_submission/submission_blocked.md` rather than silently claiming a final package.

Check configured provider connectivity manually:

```bash
python scripts/smoke_providers.py \
  --config-file mcm_agent_config.local.json \
  --workspace .smoke
```

`--env-file` is still accepted for older setups. When both are supplied, values from
`--config-file` override `.env` values.

## Workspace Structure

Each run writes to a workspace directory. Important files and folders:

| Path | Purpose |
|---|---|
| `input/` | Copied problem file, attachments, user idea, and optional template. |
| `parsed/` | MinerU or fake parser outputs: `problem.md`, `problem.json`, layout files. |
| `reports/` | Human-readable reports: problem understanding, feasibility, validation. |
| `discussion/` | User direction lock, user brief, data questions, reframing options. |
| `data/` | Feasibility matrix, source registry, retrieval log, external extracts, processed data, lineage. |
| `results/` | Model metrics, evidence registry, experiment runs, sensitivity files. |
| `figures/` | Figure plan, figure registry, generated PDF/SVG/PNG, source scripts. |
| `paper/` | Claim plan, LaTeX sections, `main.tex`, `references.bib`, optional PDF. |
| `review/` | Gate JSON, claim-plan report, reviewer report, source audit, figure audit, fact regression report. |
| `final_submission/` | AI use report, submission checklist, machine-readable manifest, packages when packaging is run. |
| `workflow_topology.json` | Snapshot of graph nodes, edges, and failure routes. |
| `stage_runs.jsonl` | Append-only stage execution log. |
| `task_state.json` | Current phase, checkpoints, and blocked repair metadata. |

## Runtime Config And Knowledge Base

`mcm_agent_config.example.json` is the committed template. Copy it to
`mcm_agent_config.local.json`, fill the providers you want to use, and pass it with
`--config-file`. The local JSON may contain API keys and is ignored by git.

The top-level config sections are:

- `llm`
- `search`
- `official_data`
- `mineru`
- `humanizer`
- `rag`
- `runtime`

`rag.knowledge_base_dir` defaults to `knowledge_base`. The folder is intentionally empty
in git except for `.gitkeep`; local user files are ignored. During `methodology_rag`,
the agent recursively scans that folder. `.md` and `.txt` files are chunked into
`rag/methodology.db`. `.pdf` files are parsed through the configured MinerU provider
when available, then chunked with the original PDF path as provenance. If MinerU is not
available or parsing fails, the PDF is listed in `rag/retrieval_notes.md` and the
workflow continues. Unsupported suffixes are listed as skipped.

`rag/methodology_hits.json` records `source_type`, `relative_path`, `chunk_id`,
`page_hint`, and `usage` for each retrieved chunk. Local RAG materials guide modeling
choices, paper structure, rule compliance, and review checklists; they are not registered
as external factual data unless the data pipeline separately verifies them as sources.

## Agent Stages

The runtime is graph-aware. `run_mvp_workflow` builds stage handlers and executes them
through `StageExecutor`, using `workflow_topology.json` for normal edges and repair routes.

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

Some edges are conditional:

- `data_feasibility_scout -> research_reframing` when critical data appears unavailable.
- `user_discussion -> data_feasibility_scout` when the user introduces a new data need.
- Gate stages route to repair stages when they fail.

`claim_planning` runs after figure QA and before paper writing. It writes
`paper/claim_plan.json`, which lists each planned paper claim, target section, claim type,
priority, support IDs, and unresolved reason when support is missing. Claim planning now
uses a paper context built from problem understanding, confirmed direction, model decision,
validation, RAG hits, evidence, figures, and sources, so the plan can include assumption,
model-choice, result, sensitivity, limitation, and conclusion claims.

`paper_writer` uses `paper/claim_plan.json` as the authoritative list of important claims
when it exists. It renders contextual abstract, introduction, assumptions, model, results,
sensitivity, and conclusion sections while keeping claim trace comments near the prose.

`methodology_rag` imports two optional methodology sources: the configured local
`knowledge_base/` folder and any `--supervisor-skills-dir` passed on the command line.
Both sources are additive, so a user can keep contest rules and method notes locally while
still using supervisor skill excerpts. It retrieves multiple paper-quality query types,
including assumption writing, model formulation, limitation discussion, figure design, and
pre-submission review.

`modeling_council` and `model_judge` diagnose common MCM/ICM archetypes and emit a
bounded hybrid route plan. The current route IDs are `multi_criteria_evaluation`,
`constrained_optimization`, `forecasting_model`, `monte_carlo_simulation`,
`network_flow_graph`, and `multi_objective_decision`. Fallback diagnosis focuses on the
problem-background section and avoids keyword substring matches, so workflow boilerplate
does not trigger spurious models.

`reports/experiment_spec.json` contains `route_plan` metadata plus per-route solver
modules, roles, input requirements, expected outputs, metrics, and column-binding
contracts. `solver_coder` writes `results/model_route_summary.json` with inferred
`column_bindings`, `binding_status`, and `route_execution_status` for each selected
route.

## Gate Repair Flow

Gate outputs are machine-readable JSON files. They have:

```json
{
  "gate_id": "validation_gate",
  "status": "fail",
  "failure_reason": "bad_results",
  "repair_stage": "solver_coder",
  "blocking_findings": ["Missing evidence for metric `row_count`."]
}
```

Important gates:

| Gate | File | Typical repair stage |
|---|---|---|
| Extraction quality | `review/extraction_gate.json` | `mineru_extraction` |
| Source verification | `review/source_gate.json` | `search_data` |
| Validation | `review/validation_gate.json` | `solver_coder`, `search_data`, or `modeling_council` |
| Figure quality | `review/figure_gate.json` | `figure_planning` |
| Final review | `review/final_gate.json` | `paper_writer`, `search_data`, `figure_planning`, etc. |

Use `mcm-agent inspect <workspace>` to view the current failed gate and repair stage.
Use `mcm-agent resume <workspace> --from-stage <stage>` after adding data, fixing files,
or changing configuration.

The executor stops repeated gate loops. If the same gate and failure reason recur too
many times, `task_state.json` receives:

```json
{
  "blocked_reason": "source_verifier/source_unreliable",
  "blocked_repair_stage": "search_data"
}
```

At that point, inspect the blocking findings before resuming.

## Data And Citation Rules

Every external source should be traceable through:

- `data/data_feasibility_matrix.json`
- `data/source_registry.json`
- `data/retrieval_log.jsonl`
- `data/data_lineage.json`
- `data/citation_candidates.json`

`data_feasibility_matrix.json` is written before the user direction is locked. It records
each proposed data need, the early official-data query, top URLs, availability judgment,
proxy variables, and the recommended next action. If the user adds new data needs during
discussion, the workflow can loop back to `data_feasibility_scout` before modeling.

`discussion/user_brief.md` and `discussion/confirmed_direction.md` include a data
feasibility snapshot when the matrix exists, so the human and AI discuss the modeling
plan with data availability visible. `search_data` also imports searchable matrix rows
into `data/search_plan.json`; rows marked `private_or_unavailable` are kept in the plan
but skipped for deeper retrieval unless the user reframes them.

When direct data is private or unavailable, `research_reframing` writes
`discussion/reframing_options.md` and `discussion/reframing_options.json`. The options
include proxy-modeling routes, user-provided-assumption routes, required caveats, and
recommended model changes before `user_discussion` locks the final direction.
`UserDiscussionAgent` records the adopted option in `discussion/direction_lock.json` as
`adopted_reframing_strategy` and `adopted_reframing_option_id`, and copies the adopted
option into `discussion/confirmed_direction.md` for the modeling council.

Each accepted source in `data/source_registry.json` records optional `data_need_id`,
`target_dataset`, and `source_query` fields. This creates a reviewable chain from data
need -> search query -> website URL -> extracted local page -> citation candidate.
The source gate also checks coverage for searchable feasibility-matrix needs: every
available or unknown matrix need must have at least one official, academic, or reputable
source bound to its `data_need_id`; otherwise the workflow routes back to `search_data`.
When coverage fails, `reports/search_repair_report.md` and
`data/search_repair_actions.json` summarize uncovered needs, attempted queries,
untrusted sources, candidate official APIs, and whether the next move is another query,
an official API call, user-provided data, or reframing.
Official API repair can automatically register source and lineage records for World Bank,
OECD, UNData, FRED, US Census, NOAA, NASA POWER, Open-Meteo, and OSM/Overpass payloads.
World Bank, OECD public SDMX, UNData download, NASA POWER, Open-Meteo, and Overpass can
run without keys. FRED needs `official_data.fred_api_key`; US Census can use
`official_data.us_census_api_key`; NOAA uses `official_data.noaa_api_key` when configured.
Unit tests mock these HTTP calls with `respx` rather than touching live APIs.

Every reported metric should be traceable through:

- `reports/experiment_spec.json`
- `results/experiment_runs.jsonl`
- `results/model_metrics.json`
- `results/model_route_summary.json`
- `results/evidence_registry.json`

`experiment_spec.json` is the machine-readable bridge from model decision to solver
execution. It lists each selected route, solver module, method, input requirements,
expected outputs, metrics, and column-binding contracts. Solver execution records the
resolved bindings in `model_route_summary.json`, for example `time_column=year`,
`target_column=demand`, or `source_column=origin`.

`schema_profile.json` is produced by EDA and records field-level dtype, missing rate,
unique count, and semantic tags such as `time`, `target`, `source_node`, `target_node`,
`cost`, `capacity`, and `numeric_indicator`. Solver column binding uses these tags before
falling back to column-name heuristics.

`solver_binding_report.json` records whether required solver columns were successfully
bound. Missing required bindings, such as a network route without source/target/cost
columns, fail validation with `failure_reason=weak_model` and route repair to
`modeling_council`.

`model_route_summary.json` binds the selected model route to route-specific metrics,
figure planning, and the paper model section. Its `route_execution_status` values show
whether each selected route was `executed`, `blocked_missing_binding`, or
`attempted_no_metric`.

`modeling_quality_gate` runs after `model_judge` and before deep search. It writes
`reports/modeling_quality_report.md` and `review/modeling_gate.json`, blocking model
plans whose experiment spec has missing metrics, missing expected outputs, required
route bindings that cannot be justified, or unavailable data needs without an adopted
proxy/reframing strategy. Failures use `failure_reason=weak_model` and route back to
`modeling_council`.

`paper_evidence_binding` runs after `paper_writer` and before typesetting. It writes
`review/paper_evidence_bindings.json` and `review/paper_evidence_report.md`, checking
that claim-bearing sections contain valid `claim_id`, `evidence_id`, `figure_id`, or
`source_id` bindings to registered artifacts. When `paper/claim_plan.json` exists, it
also checks that every planned critical or major claim is written and that written
claim bindings stay within the planned evidence, figure, and source IDs. The final
reviewer blocks omitted planned claims and unresolved critical planned claims.
It also writes `review/paper_quality_scores.json`, scoring section completeness and claim
trace density. Incomplete paper sections fail the final gate with repair stage
`paper_writer`.

The first reusable solver modules are:

- `mcm_agent.solver_modules.evaluation`: entropy weighting and TOPSIS ranking.
- `mcm_agent.solver_modules.optimization`: capacity-constrained priority allocation.
- `mcm_agent.solver_modules.forecasting`: linear trend forecast baseline.
- `mcm_agent.solver_modules.simulation`: reproducible Monte Carlo scenario summaries.
- `mcm_agent.solver_modules.network`: shortest-path table generation.

`ReferenceManager` creates `paper/references.bib` from registered citation candidates
and writes `review/reference_audit_report.md`. Placeholder IDs such as `source_id=missing`
are ignored as placeholders, not treated as real external sources.

## Common Failure Modes

| Symptom | Likely cause | What to do |
|---|---|---|
| `extraction_gate` fails | Parsed problem text is empty. | Check MinerU mode, PDF path, or rerun with a simpler problem file. |
| `source_gate` fails | No reliable external sources were found. | Configure Tavily/Firecrawl, add attachments, or reframe the data need. |
| `validation_gate` fails | Metrics lack evidence or an experiment run failed. | Inspect `results/experiment_runs.jsonl` and rerun from `solver_coder`. |
| `figure_gate` fails | Missing PDF/SVG, caption, target section, or evidence IDs. | Rerun from `figure_planning` after fixing the figure plan. |
| `final_gate` fails | Reviewer found source, writing, figure, or fact regression blockers. | Inspect `review/final_gate.json` and resume from its `repair_stage`. |
| Repeated gate loop | The repair stage cannot fix the same issue automatically. | Add data/API keys or manually edit inputs, then resume. |

## Human Review Points

The system is designed to make human review easier, not to remove it. Before submission,
review at least:

- `reports/problem_understanding.md`
- `reports/model_decision.md`
- `results/evidence_registry.json`
- `figures/figure_registry.json`
- `review/figure_quality_report.md`
- `review/reference_audit_report.md`
- `review/reviewer_report.md`
- `paper/main.tex`

For a real contest run, the user should confirm the research direction before the paper
is considered final.

## Submission Package

When `SubmissionPackager` runs successfully, it creates:

- `final_submission/submission_package.zip`
- `final_submission/source_code.zip`
- `final_submission/submission_manifest.json`
- `final_submission/submission_checklist.md`

The manifest records selected model routes, figure IDs, and audit files such as source
registry, data lineage, route summary, evidence registry, reference audit, and figure QA.
