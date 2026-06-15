# Unified JSON Config And RAG Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the A-route foundation: runtime JSON configuration plus an empty user-fillable RAG knowledge base.

**Architecture:** Add a nested JSON config loader that maps into the existing flat `Settings` model to avoid rewriting providers. Wire `--config-file` through CLI and smoke scripts. Extend `MethodologyRAGAgent` to ingest a configured knowledge-base directory while keeping `--supervisor-skills-dir` compatible.

**Tech Stack:** Python 3, Pydantic settings, Typer CLI, pytest, SQLite FTS5, existing provider bundle.

---

## Task 1: JSON Config Contract

**Files:**
- Modify: `.gitignore`
- Create: `mcm_agent_config.example.json`
- Create: `knowledge_base/.gitkeep`
- Modify: `src/mcm_agent/config.py`
- Test: `tests/test_config_json.py`

Steps:

- [ ] Write failing tests for example JSON sections, gitignore protection, missing config defaults, and JSON-over-env precedence.
- [ ] Implement `load_settings(env_file=None, config_file=None)` that reads existing env values and overlays nested JSON values.
- [ ] Add tracked `mcm_agent_config.example.json`.
- [ ] Add tracked `knowledge_base/.gitkeep` while ignoring local knowledge-base contents.
- [ ] Run `pytest tests/test_config_json.py -q`.
- [ ] Commit with `feat: add json runtime config contract`.

## Task 2: CLI And Smoke Config File Wiring

**Files:**
- Modify: `src/mcm_agent/cli.py`
- Modify: `scripts/smoke_providers.py`
- Test: `tests/test_cli_config.py`
- Test: `tests/test_provider_smoke.py`

Steps:

- [ ] Add failing CLI test for `provider-status --config-file`.
- [ ] Add failing smoke script test or function-level config test for JSON config loading.
- [ ] Add `--config-file` to `run`, `resume`, and `provider-status`.
- [ ] Add `--config-file` to `scripts/smoke_providers.py`.
- [ ] Keep `--env-file` backward compatible.
- [ ] Run `pytest tests/test_cli_config.py tests/test_provider_smoke.py -q`.
- [ ] Commit with `feat: wire json config into cli and smoke`.

## Task 3: Knowledge Base RAG Ingestion

**Files:**
- Modify: `src/mcm_agent/agents/rag.py`
- Modify: `src/mcm_agent/workflows/mvp.py`
- Modify: `src/mcm_agent/cli.py`
- Test: `tests/test_rag.py`
- Test: `tests/test_mvp_workflow.py`

Steps:

- [ ] Add failing tests for empty knowledge base, `.md`/`.txt` ingestion, `.pdf` pending notes, and unsupported suffix notes.
- [ ] Extend `MethodologyRAGAgent.run` to accept `knowledge_base_dir` and `ingest_extensions`.
- [ ] Read RAG settings from `Settings` in workflow handlers.
- [ ] Keep supervisor skills import as an optional additional source.
- [ ] Run `pytest tests/test_rag.py tests/test_mvp_workflow.py -q`.
- [ ] Commit with `feat: ingest configured rag knowledge base`.

## Task 4: Docs And Final Verification

**Files:**
- Modify: `docs/WORKFLOW.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Modify: `docs/PROJECT_STATUS.md`
- Modify: `README.md` if needed

Steps:

- [ ] Document `mcm_agent_config.example.json`, local config copying, and `knowledge_base/`.
- [ ] Update command examples to prefer `--config-file`.
- [ ] Run `pytest -q`.
- [ ] Run `ruff check src tests scripts`.
- [ ] Commit docs with `docs: document json config and rag base`.
- [ ] Push `main`.
