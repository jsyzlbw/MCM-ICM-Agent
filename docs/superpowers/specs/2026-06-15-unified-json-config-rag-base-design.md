# Unified JSON Config And RAG Base Design

## Goal

Build the A-route foundation: one local JSON file controls runtime configuration, and the RAG knowledge base starts as an empty user-fillable folder.

This phase intentionally does not upgrade paper quality, add new official-data APIs, or implement LaTeX layout repair. Those later phases should depend on this configuration and RAG contract.

## User Requirements

- All runtime configuration, including LLM selection and platform API keys, lives in one JSON file.
- The JSON file may contain plaintext API keys when it is local-only and ignored by git.
- The repository commits only a key-free example template.
- The RAG knowledge base is an empty folder waiting for the user to fill with papers, notes, and rules.
- Do not ask the user for API keys before the broader roadmap is implemented; report required APIs afterward.

## File Contract

Repository-tracked files:

```text
mcm_agent_config.example.json
knowledge_base/.gitkeep
docs/WORKFLOW.md
docs/PROJECT_STATUS.md
docs/IMPLEMENTATION_PLAN.md
```

Local-only files:

```text
mcm_agent_config.local.json
knowledge_base/*
```

`.gitignore` must ignore `mcm_agent_config.local.json` and user-filled `knowledge_base/*`, while allowing `knowledge_base/.gitkeep` to stay tracked.

## JSON Config Shape

The example config will be complete enough to copy and fill:

```json
{
  "llm": {
    "provider": "openai_compatible",
    "api_key": "",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4.1",
    "timeout_seconds": 60
  },
  "search": {
    "tavily_api_key": "",
    "firecrawl_api_key": "",
    "brave_search_api_key": "",
    "exa_api_key": ""
  },
  "official_data": {
    "fred_api_key": "",
    "open_meteo_base_url": "https://archive-api.open-meteo.com/v1/archive"
  },
  "mineru": {
    "mode": "fake",
    "cli": "mineru",
    "api_base_url": "https://mineru.net",
    "api_key": ""
  },
  "humanizer": {
    "provider": "fake",
    "api_key": "",
    "api_base_url": "https://leahloveswriting.xyz"
  },
  "rag": {
    "knowledge_base_dir": "knowledge_base",
    "ingest_extensions": [".md", ".txt", ".pdf"]
  },
  "runtime": {
    "default_language": "en",
    "max_retries": 2,
    "http_timeout_seconds": 60,
    "code_timeout_seconds": 120
  }
}
```

## Configuration Loading

Add a JSON loader in `src/mcm_agent/config.py`.

The new path is:

```text
mcm_agent_config.local.json -> AppConfig -> Settings-compatible provider bundle
```

The CLI should add `--config-file` to `run`, `resume`, `provider-status`, and the provider smoke script.

Recommended default:

```text
--config-file mcm_agent_config.local.json
```

If the file does not exist, the loader should return defaults and fake/disabled providers, so unit tests and demos still run without secrets.

Existing `.env` support may remain during migration, but JSON config is the documented and preferred runtime contract. In commands that accept both `--config-file` and `--env-file`, JSON values win.

## Provider Factory Behavior

`build_provider_bundle` should continue to receive one settings object. The loader should map nested JSON fields into the existing flat settings fields first, then later phases can migrate code to nested config models.

Examples:

```text
config.llm.api_key -> settings.openai_api_key
config.llm.model -> settings.openai_model
config.search.tavily_api_key -> settings.tavily_api_key
config.mineru.mode -> settings.mineru_mode
config.humanizer.api_key -> settings.humanizer_api_key
config.runtime.http_timeout_seconds -> settings.mcm_agent_http_timeout_seconds
```

This keeps the first A-route implementation small and avoids rewriting every provider at once.

## RAG Knowledge Base Behavior

The default folder is:

```text
knowledge_base/
```

The repository tracks only:

```text
knowledge_base/.gitkeep
```

The user can add local files such as:

```text
knowledge_base/mcm_winning_papers/my_note.md
knowledge_base/methods/network_flow.txt
knowledge_base/rules/contest_rules.pdf
```

Initial ingest behavior:

- `.md` and `.txt` files are read directly and inserted into the SQLite FTS store.
- `.pdf` files are discovered and reported in `rag/retrieval_notes.md` as pending MinerU-backed ingestion.
- Empty knowledge bases are valid and should not fail the workflow.
- Existing `--supervisor-skills-dir` remains supported as an optional additional source.

## CLI Behavior

New or updated command examples:

```bash
mcm-agent provider-status --config-file mcm_agent_config.local.json
```

```bash
mcm-agent run /tmp/mcm_agent_task \
  --config-file mcm_agent_config.local.json \
  --problem-file /path/to/problem.pdf \
  --attachment /path/to/data.csv \
  --auto-approve
```

```bash
python scripts/smoke_providers.py \
  --config-file mcm_agent_config.local.json \
  --workspace .smoke
```

`--env-file` can remain for backward compatibility, but docs should present `--config-file` as the standard path.

## Error Handling

- Missing local config file: warn or report defaults in `provider-status`, but do not crash.
- Malformed JSON: fail fast with a clear file path and JSON parse error.
- Unknown keys: ignore with Pydantic-style compatibility so future config expansion does not break older code.
- Knowledge base path missing: create it when initializing or running the workflow.
- Knowledge base empty: write notes saying no user RAG documents were ingested.
- User docs with unsupported suffixes: list them in `rag/retrieval_notes.md` as skipped.

## Tests

Add focused tests for:

- Loading `mcm_agent_config.local.json` into existing flat `Settings`.
- JSON values overriding env-file values when both are passed.
- `mcm_agent_config.example.json` contains all expected top-level sections.
- `.gitignore` ignores `mcm_agent_config.local.json` and user knowledge-base contents.
- `MethodologyRAGAgent` accepts an empty knowledge base folder.
- `MethodologyRAGAgent` ingests `.md` and `.txt` files from the configured folder.
- `.pdf` files are reported as pending ingestion instead of silently ignored.
- CLI `provider-status` reads JSON config.
- `scripts/smoke_providers.py` reads JSON config.

## Non-Goals

- Do not implement OECD, UNData, Census, NOAA/NASA, or OSM providers in this phase.
- Do not improve paper prose generation in this phase.
- Do not implement PDF RAG ingestion in this phase; only detect and report pending PDF files.
- Do not require live API keys in tests.
- Do not commit any local config with real API keys.

## Acceptance Criteria

- A fresh clone contains `mcm_agent_config.example.json` and an empty `knowledge_base/` folder.
- A user can copy the example JSON to `mcm_agent_config.local.json`, fill keys, and run CLI commands with `--config-file`.
- Running without a local config still uses fake providers and keeps existing tests green.
- RAG runs successfully when `knowledge_base/` is empty.
- RAG ingests local `.md` and `.txt` files when the user adds them.
- Full verification passes:

```bash
pytest -q
ruff check src tests scripts
```
