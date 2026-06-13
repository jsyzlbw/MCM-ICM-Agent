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
- MinerU local or REST mode for PDF parsing.
- UShallPass for academic humanization, guarded by fact regression checks.

MCP adapters can be added later, but the core runtime is designed to work through API
provider adapters so it remains testable, deployable, and auditable.

## Verification

```bash
ruff check src tests
pytest -v
```

## Design Docs

- [System design](docs/DESIGN.md)
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
