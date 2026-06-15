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
then Exa. World Bank and Open-Meteo are available as no-key official data repair sources
when search coverage fails. FRED requires registration; leave `official_data.fred_api_key`
empty to disable FRED repair.

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

During the `methodology_rag` stage, `.md` and `.txt` files are inserted into the SQLite FTS
methodology store. `.pdf` files are discovered and reported in `rag/retrieval_notes.md` as
pending MinerU-backed ingestion. Unsupported suffixes are reported as skipped.

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

To include a real MinerU parse check, provide a small local PDF:

```bash
python scripts/smoke_providers.py \
  --config-file mcm_agent_config.local.json \
  --workspace .smoke \
  --mineru-file /path/to/sample.pdf
```

The script reports `PASSED`, `SKIPPED`, or `FAILED` for LLM, Tavily, Firecrawl,
UShallPass, and MinerU. Missing optional keys are reported as `SKIPPED`; actual API
or response failures return a non-zero exit code.

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
