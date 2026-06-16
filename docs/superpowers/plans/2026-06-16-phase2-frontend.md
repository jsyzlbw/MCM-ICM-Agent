# Phase 2: Static Frontend (GUI MVP) — Implementation Record

Status date: 2026-06-16
Branch: `feat/gui-frontend`
Implements spec `docs/superpowers/specs/2026-06-16-frontend-gui-design.md` §4.1, §5, §6.1/§6.3/§6.5/§6.6, §12 step ②.

## What was built

Zero-build frontend (no node, no build step) served by the existing `mcm-agent gui` FastAPI server.

**Backend wiring**
- `src/mcm_agent/server/app.py` — mounts `StaticFiles` at `/static`, serves the shell at `GET /`.
- `src/mcm_agent/server/config_store.py` — new `merge_config(existing, incoming)`: deep-merges, strips mask pseudo-fields (`*_configured`/`*_preview`), and **preserves stored secrets when the incoming value is blank** (the GUI never sees real secrets to send back).
- `src/mcm_agent/server/routes_config.py` — `POST /api/config` now merges instead of overwriting, so saving the masked config from the Settings screen cannot clobber existing keys.

**Frontend** (`src/mcm_agent/server/static/`)
- `index.html` — app shell: fixed sidebar (6 nav items) + screen sections.
- `styles.css` — Friendly Workbench design tokens (violet `#7C5CFF`, rounded 14px, pill badges, `--mono` log box).
- `app.js` — single Alpine `app` component: hash router, `api()` fetch helper, and logic for the four core screens.
- `vendor/alpine.min.js` — Alpine v3.14.1 vendored (zero-build, no CDN dependency at runtime).

**Screens wired this phase (spec §12 step ②):**
- **设置 / Settings** — renders config by section; per-section 「测试连接」 (POST `/api/config/test-provider`); secrets shown as 已配置 ✓ + last-4, editable to overwrite; Save merges.
- **任务上传 / Task Upload** — create/select workspace, upload problem/attachment/template, start run (demo + auto-approve toggles).
- **运行监控 / Run Monitor** — stage timeline, activity feed + live log box driven by **SSE** (`/events`), run-status pill + duration, Stop, and the inline **checkpoint approval** card when paused.
- **产物浏览 / Artifacts** — file list + text preview + download (existing artifact API).

**Placeholders (built in later phases):** 知识库 (Phase 3), 讨论/规划 (Phase 4) render a "coming in Phase N" card; nav is already present.

## Verification

- `pytest -q` → **296 passed**; `ruff check src tests` → clean.
- New tests: `tests/test_server_static.py` (root shell + static assets served), `tests/test_config_merge.py` (secret-preserving merge, pseudo-field stripping).
- **Live HTTP smoke** (real uvicorn, not TestClient): `/` + all `/static/*` → 200; full create→upload→run(demo, until problem_understanding)→`done` loop ran 4 stages and produced 31 artifacts; `/logs` returned the stage list.
- **Static frontend audit** (independent subagent): all API paths/methods/payloads match the backend; all SSE event names match; all 47 HTML-referenced state/methods exist in `app.js`; Alpine directives well-formed; config round-trip coherent. One fix applied: `approve()` now forwards `auto_approve` + `demo` so a resumed run keeps the user's mode.

## NOT autonomously verified (needs the user, morning)

- **In-browser visual/interaction check.** I cannot open a browser. Open `http://127.0.0.1:8787` after `mcm-agent gui` and click through Settings → Upload → run a demo task → watch the Monitor (timeline + SSE log) → Artifacts. The static audit + HTTP smoke cover the contract, but pixel layout and Alpine reactivity need human eyes.

## Follow-ups

- **Packaging:** static files live under the package (`src/mcm_agent/server/static/`) and are git-tracked, so hatchling includes them in the wheel; the user runs an editable install so it already works. Verify on a real wheel build if distributing.
- The Settings test button maps each section to one representative provider (`llm→llm`, `search→tavily`, `official_data→fred`, `mineru→mineru`, `humanizer→humanizer`); per-provider granular testing within `search` is a later refinement.
- `extraRequirements` textarea is captured in the UI but not yet persisted to the workspace (wire to a `user_requirements.md` upload in a later pass).
