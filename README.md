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

## Runtime Shape

The implementation uses a workspace per contest task. Each workspace stores inputs, parsed
documents, reports, data, evidence, figures, paper files, review outputs, and final submission
artifacts. Agents communicate through typed artifact records, event logs, and handoff packets.

## API Configuration

Copy `.env.example` to `.env` and fill in only the providers you want to use.

The recommended MVP stack is:

- LLM provider through an OpenAI-compatible API.
- Tavily API for search.
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
```

`MINERU_MODE=rest` uses MinerU's precision API flow: create an upload batch,
upload the local PDF to the returned URL, poll the batch result, download the
result zip, and persist `problem.md`, `problem.json`, `problem_layout.json`, and
`formulas.json` into the task workspace.

## Verification

```bash
ruff check src tests
pytest -v
```

## Design Docs

- [System design](docs/DESIGN.md)
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
