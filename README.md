# MCM-ICM Agent

CLI-first reference implementation for an MCM/ICM math modeling agent.

The project is built around a traceable workflow: every document parse, data source,
modeling result, figure, paper section, humanization step, and review finding is written
to a task workspace.

## Quick Start

```bash
python -m pip install -e ".[dev]"
mcm-agent version
mcm-agent run-demo /tmp/mcm_agent_demo --auto-approve
mcm-agent status /tmp/mcm_agent_demo
```

Run a real task input with the configured providers:

```bash
mcm-agent run /tmp/mcm_agent_task \
  --env-file .env \
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
  --env-file .env \
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

## API Configuration

Copy `.env.example` to `.env` and fill in only the providers you want to use.

The recommended MVP stack is:

- LLM provider through an OpenAI-compatible API.
- Tavily API as the primary search provider, with Brave and Exa as fallback search providers.
- Firecrawl API for web extraction.
- MinerU local mode or official REST precision API for PDF parsing.
- UShallPass for academic humanization, guarded by fact regression checks.

MCP adapters can be added later, but the core runtime is designed to work through API
provider adapters so it remains testable, deployable, and auditable.

### Required For The Next Development Phase

Start with these keys:

```env
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=gpt-4.1

TAVILY_API_KEY=
FIRECRAWL_API_KEY=
```

`OPENAI_BASE_URL` can stay empty when using the default OpenAI endpoint. Set it only when
using an OpenAI-compatible provider.

Then check the active provider selection:

```bash
mcm-agent provider-status --env-file .env
```

Expected once the first three providers are configured:

```text
LLM: openai-compatible (<your model>)
Search: Tavily API
Extract: Firecrawl API
MinerU: fake
Humanizer: fake
```

Later optional keys:

```env
HUMANIZER_API_KEY=
HUMANIZER_API_BASE_URL=https://leahloveswriting.xyz

MINERU_MODE=rest
MINERU_CLI=mineru
MINERU_API_BASE_URL=https://mineru.net
MINERU_API_KEY=

BRAVE_SEARCH_API_KEY=
EXA_API_KEY=

OPEN_METEO_BASE_URL=https://archive-api.open-meteo.com/v1/archive
FRED_API_KEY=
```

When multiple search keys are configured, the runtime tries Tavily first, then Brave,
then Exa. `mcm-agent provider-status --env-file .env` prints the active search stack.

World Bank and Open-Meteo are used as no-key official data repair sources when search
coverage fails. FRED requires registration; leave `FRED_API_KEY` empty to disable FRED
repair.

`MINERU_MODE=rest` uses MinerU's precision API flow: create an upload batch,
upload the local PDF to the returned URL, poll the batch result, download the
result zip, and persist `problem.md`, `problem.json`, `problem_layout.json`, and
`formulas.json` into the task workspace.

### Provider Smoke Tests

Smoke tests are manual checks for real API connectivity. They are intentionally not part
of the normal pytest suite.

```bash
python scripts/smoke_providers.py --env-file .env --workspace .smoke
```

To include a real MinerU parse check, provide a small local PDF:

```bash
python scripts/smoke_providers.py \
  --env-file .env \
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
