# Workflow Guide

This guide explains how to run, inspect, resume, and audit the MCM/ICM Agent workflow.
It is written for development and early user testing, not as a promise that the system is
contest-ready without human review.

## Command Reference

Install the project in editable mode:

```bash
python -m pip install -e ".[dev]"
```

Run the bundled demo task:

```bash
python scripts/run_demo_task.py --workspace .demo_workspace --clean
```

Run your own task:

```bash
mcm-agent run /tmp/mcm_agent_task \
  --env-file .env \
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
  --env-file .env \
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
python scripts/smoke_providers.py --env-file .env --workspace .smoke
```

## Workspace Structure

Each run writes to a workspace directory. Important files and folders:

| Path | Purpose |
|---|---|
| `input/` | Copied problem file, attachments, user idea, and optional template. |
| `parsed/` | MinerU or fake parser outputs: `problem.md`, `problem.json`, layout files. |
| `reports/` | Human-readable reports: problem understanding, feasibility, validation. |
| `discussion/` | User direction lock, user brief, data questions, reframing options. |
| `data/` | Source registry, retrieval log, external extracts, processed data, lineage. |
| `results/` | Model metrics, evidence registry, experiment runs, sensitivity files. |
| `figures/` | Figure plan, figure registry, generated PDF/SVG/PNG, source scripts. |
| `paper/` | LaTeX sections, `main.tex`, `references.bib`, optional PDF. |
| `review/` | Gate JSON, reviewer report, source audit, figure audit, fact regression report. |
| `final_submission/` | AI use report, submission checklist, machine-readable manifest, packages when packaging is run. |
| `workflow_topology.json` | Snapshot of graph nodes, edges, and failure routes. |
| `stage_runs.jsonl` | Append-only stage execution log. |
| `task_state.json` | Current phase, checkpoints, and blocked repair metadata. |

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
search_data
source_verifier
data_eda
solver_coder
validation_gate
figure_planning
visualization
figure_quality_gate
paper_writer
typesetting
pre_submission_review
final_gatekeeper
submission_packager
```

Some edges are conditional:

- `data_feasibility_scout -> research_reframing` when critical data appears unavailable.
- `user_discussion -> data_feasibility_scout` when the user introduces a new data need.
- Gate stages route to repair stages when they fail.

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

- `data/source_registry.json`
- `data/retrieval_log.jsonl`
- `data/data_lineage.json`
- `data/citation_candidates.json`

Every reported metric should be traceable through:

- `results/experiment_runs.jsonl`
- `results/model_metrics.json`
- `results/model_route_summary.json`
- `results/evidence_registry.json`

`model_route_summary.json` binds the selected model route to route-specific metrics,
figure planning, and the paper model section.

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
