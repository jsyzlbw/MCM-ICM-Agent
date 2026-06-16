# Phase 3: Knowledge Base (file manager + screen) — Implementation Record

Status date: 2026-06-16
Branch: `feat/gui-knowledge`
Implements spec `docs/superpowers/specs/2026-06-16-frontend-gui-design.md` §6.2 + §12 step ③.

## Design decision (important — for your review)

The 2026-06-16 spec §6.2 references an aspirational **structured "case" schema** (carried from the older `2026-06-15-gui-productization-design.md`: `cases/<id>/{metadata.json, problem/, data/, paper/, notes/}` with completeness validation). But the **live RAG implementation** (`src/mcm_agent/agents/rag.py`) ingests **flat files** from `knowledge_base/` (recursively) into a per-workspace SQLite FTS index during the `methodology_rag` stage — there is no global index and no case concept in the code today.

To avoid building an elaborate schema the running system doesn't use, Phase 3 implements a **knowledge-base file manager that matches current reality** and is genuinely useful + testable. The case-schema remains a **deferred decision for you**: if you want structured cases (with metadata + completeness checks + per-case ingest), that's a larger change to both the RAG ingestion and this UI — say the word and we'll spec it.

## What was built

**Backend** — `src/mcm_agent/server/routes_knowledge.py`:
- `GET /api/knowledge/files` → `{knowledge_base_dir, extensions, files:[{path,size,ext,ingestible}], ingestible_count}` (recursive; hidden dirs skipped; `ingestible` = extension in config `rag.ingest_extensions`).
- `POST /api/knowledge/files` (multipart `subdir` + `files`) → save into `knowledge_base/[subdir]/` (path-traversal guarded).
- `DELETE /api/knowledge/files?path=` → delete one file (path-traversal guarded).
- `GET /api/knowledge/index-preview` → offline dry-run: ingest `.md/.txt` into a throwaway FTS store and report `{total_chunks, notes}`. PDFs are reported as "pending MinerU" (real PDF ingestion needs MinerU and happens per-run). Reuses `mcm_agent.agents.rag.ingest_knowledge_base` so the preview matches real ingestion behavior.
- `src/mcm_agent/server/app.py` — `create_app` gains an injectable `knowledge_base_dir` (resolved from config `rag.knowledge_base_dir`, default `knowledge_base/`, cwd-relative); mounts the knowledge router.

**Frontend** — `static/index.html` + `static/app.js`: the 知识库 screen now lists files (with 可索引/跳过 badges + sizes), uploads (optional subfolder), deletes, and runs an index preview (chunk count + per-file notes).

## Verification

- `pytest -q` → **299 passed**; `ruff check src tests` → clean; `node --check app.js` → OK.
- New tests: `tests/test_server_knowledge.py` — list/upload/preview/delete round-trip (md ingested → ≥1 chunk), unsupported-extension marked not ingestible, path-traversal → 400.
- **Live HTTP smoke**: empty list → upload `methods/note.md` (ingestible) → index-preview = 1 chunk → delete → empty; `../` traversal → 400.

## NOT autonomously verified

- In-browser visual/interaction check of the 知识库 screen (mirrors the verified Phase 2 patterns: same `api()` helper, Alpine bindings, file-list styling). Open `mcm-agent gui` → 知识库 to confirm visually.

## Follow-ups

- Structured case schema + per-case ingest/validation (if you want it — see "Design decision" above).
- "Ingest now into a chosen workspace" action (currently ingestion is per-run; preview is global/offline).
- Show which workspace(s) have already indexed the base.
