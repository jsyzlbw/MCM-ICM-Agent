# Final QA And Provider Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden final paper production with LaTeX/layout QA and expose one first-class provider smoke command for configured live services.

**Architecture:** Add a focused `TypesettingQAAgent` that reads LaTeX source, compile logs, and optional provider metadata, then writes machine-readable and Markdown reports. Keep the existing LaTeX provider abstraction and make `ReviewerAgent` consume the QA report for final-gate routing. Extend the current smoke tester instead of creating a parallel tool, then surface it through the Typer CLI while preserving the existing script.

**Tech Stack:** Python 3.12+, Pydantic v2, Typer, SQLite-free local file QA, httpx/respx for mocked provider checks, pytest, ruff.

---

## File Structure

- Create `src/mcm_agent/agents/typesetting_qa.py`: deterministic LaTeX/layout QA rules and report writing.
- Modify `src/mcm_agent/workflows/mvp.py`: call `TypesettingQAAgent` from the `typesetting` stage after compile.
- Modify `src/mcm_agent/agents/reviewer.py`: read `review/typesetting_quality.json` and route blocking format issues to `typesetting`.
- Modify `src/mcm_agent/providers/smoke.py`: add Brave, Exa, official-data, and aggregate default provider support.
- Modify `scripts/smoke_providers.py`: use the expanded default provider list.
- Modify `src/mcm_agent/cli.py`: add a first-class `provider-smoke` command.
- Modify `tests/test_typesetting_qa.py`, `tests/test_reviewer_revision.py`, `tests/test_mvp_workflow.py`, `tests/test_provider_smoke.py`, and `tests/test_cli_config.py`.
- Modify `README.md`, `docs/WORKFLOW.md`, `docs/PROJECT_STATUS.md`, and `docs/IMPLEMENTATION_PLAN.md`.

## Task 1: Typesetting QA Agent

**Files:**
- Create: `tests/test_typesetting_qa.py`
- Create: `src/mcm_agent/agents/typesetting_qa.py`

- [ ] **Step 1: Add failing QA tests**

Create `tests/test_typesetting_qa.py`:

```python
from pathlib import Path

from mcm_agent.agents.typesetting_qa import TypesettingQAAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json


def test_typesetting_qa_flags_compile_error_and_overflow(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    paper = workspace.root / "paper"
    paper.mkdir(exist_ok=True)
    (paper / "main.tex").write_text(
        "\\begin{document}\n"
        "\\begin{tabular}{llllllllllll}\n"
        "a & b & c & d & e & f & g & h & i & j & k & l\\\\\n"
        "\\end{tabular}\n"
        "\\begin{equation}\n"
        "x = aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "\\end{equation}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    (paper / "compile_log.txt").write_text("! Undefined control sequence.\nOverfull \\hbox\n", encoding="utf-8")

    TypesettingQAAgent().run(workspace.root)

    report = read_json(workspace.root / "review" / "typesetting_quality.json", {})
    assert report["status"] == "fail"
    assert "compile_error" in report["issue_types"]
    assert "table_overflow_risk" in report["issue_types"]
    assert "equation_overflow_risk" in report["issue_types"]
    markdown = (workspace.root / "review" / "typesetting_quality_report.md").read_text(encoding="utf-8")
    assert "Undefined control sequence" in markdown


def test_typesetting_qa_passes_clean_short_paper(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    paper = workspace.root / "paper"
    paper.mkdir(exist_ok=True)
    (paper / "main.tex").write_text("\\begin{document}\nShort paper.\n\\end{document}\n", encoding="utf-8")
    (paper / "main.pdf").write_bytes(b"%PDF")
    (paper / "compile_log.txt").write_text("Latexmk: All targets are up-to-date\n", encoding="utf-8")

    TypesettingQAAgent().run(workspace.root)

    report = read_json(workspace.root / "review" / "typesetting_quality.json", {})
    assert report["status"] == "pass"
    assert report["blocking_findings"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_typesetting_qa.py -q`

Expected: FAIL with missing module `mcm_agent.agents.typesetting_qa`.

- [ ] **Step 3: Implement the agent**

Create `src/mcm_agent/agents/typesetting_qa.py` with:

- `TypesettingIssue(BaseModel)` fields: `issue_type`, `severity`, `message`, `repair_stage`, `evidence`.
- `TypesettingQAReport(BaseModel)` fields: `status`, `issue_types`, `blocking_findings`, `repair_stage`, `issues`, `page_count`.
- `TypesettingQAAgent.run(workspace_root: Path, *, max_pages: int = 25) -> TypesettingQAReport`.

Detection rules:

- Compile error: log contains lines starting with `! `, `LaTeX Error`, or `Emergency stop`.
- Missing PDF: `paper/main.pdf` is missing and the compile log exists or `review/typesetting_report.md` says success false.
- Table overflow risk: `tabular` column specs with at least 9 column markers or log contains `Overfull \\hbox`.
- Equation overflow risk: equation/display-math lines longer than 100 characters or log contains `Overfull \\hbox` near math markers.
- Figure placement risk: LaTeX contains `[H]` more than 8 times, missing included figure paths, or log contains `Float too large`.
- Page limit risk: read `page_count` from `review/typesetting_report.json` if present; otherwise count `%%PAGE` markers in a text fixture; fail when `page_count > max_pages`.

Write:

- `review/typesetting_quality.json`
- `review/typesetting_quality_report.md`

- [ ] **Step 4: Run QA tests**

Run: `pytest tests/test_typesetting_qa.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_typesetting_qa.py src/mcm_agent/agents/typesetting_qa.py
git commit -m "feat: add typesetting quality agent"
```

## Task 2: Workflow And Final Gate Wiring

**Files:**
- Modify: `tests/test_reviewer_revision.py`
- Modify: `tests/test_mvp_workflow.py`
- Modify: `src/mcm_agent/workflows/mvp.py`
- Modify: `src/mcm_agent/agents/reviewer.py`

- [ ] **Step 1: Add failing reviewer gate test**

Add to `tests/test_reviewer_revision.py`:

```python
def test_reviewer_routes_typesetting_quality_failure_to_typesetting(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    _write_complete_paper_sections(workspace.root)
    write_json(workspace.root / "results" / "evidence_registry.json", [{"evidence_id": "ev_001"}])
    write_json(workspace.root / "review" / "paper_evidence_bindings.json", [])
    write_json(
        workspace.root / "review" / "typesetting_quality.json",
        {
            "status": "fail",
            "blocking_findings": ["LaTeX compile error: Undefined control sequence."],
            "repair_stage": "typesetting",
            "issue_types": ["compile_error"],
            "issues": [],
            "page_count": None,
        },
    )

    ReviewerAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "final_gate.json", {})
    assert gate["status"] == "fail"
    assert gate["failure_reason"] == "format_issue"
    assert gate["repair_stage"] == "typesetting"
```

- [ ] **Step 2: Add failing MVP artifact test**

Update `tests/test_mvp_workflow.py::test_run_demo_workflow_creates_required_artifacts` required artifacts to include:

```python
"review/typesetting_quality.json",
"review/typesetting_quality_report.md",
```

- [ ] **Step 3: Run failing tests**

Run:

```bash
pytest tests/test_reviewer_revision.py::test_reviewer_routes_typesetting_quality_failure_to_typesetting \
  tests/test_mvp_workflow.py::test_run_demo_workflow_creates_required_artifacts -q
```

Expected: FAIL because workflow and reviewer do not consume the QA report.

- [ ] **Step 4: Wire workflow**

In `src/mcm_agent/workflows/mvp.py`:

- Import `TypesettingQAAgent`.
- In `typesetting`, call `TypesettingQAAgent().run(workspace_root)` after `_compile_latex(...)`.
- Return `review/typesetting_quality.json` and `review/typesetting_quality_report.md`.

- [ ] **Step 5: Wire reviewer**

In `ReviewerAgent.run`, read `review/typesetting_quality.json`. If status is `fail`, append its `blocking_findings`. Set `failure_reason="format_issue"` and `repair_stage` from the report before generic bad-writing routing.

- [ ] **Step 6: Run focused tests**

Run:

```bash
pytest tests/test_typesetting_qa.py \
  tests/test_reviewer_revision.py::test_reviewer_routes_typesetting_quality_failure_to_typesetting \
  tests/test_mvp_workflow.py::test_run_demo_workflow_creates_required_artifacts -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/test_reviewer_revision.py tests/test_mvp_workflow.py src/mcm_agent/workflows/mvp.py src/mcm_agent/agents/reviewer.py
git commit -m "feat: route typesetting qa through final gate"
```

## Task 3: Expanded Provider Smoke Coverage

**Files:**
- Modify: `tests/test_provider_smoke.py`
- Modify: `src/mcm_agent/providers/smoke.py`
- Modify: `scripts/smoke_providers.py`

- [ ] **Step 1: Add failing smoke tests**

Add tests:

```python
@respx.mock
def test_smoke_tester_checks_brave_search(tmp_path: Path) -> None:
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=Response(200, json={"web": {"results": [{"title": "Official", "url": "https://data.gov", "description": "Data"}]}})
    )
    tester = ProviderSmokeTester(Settings(brave_search_api_key="test-key"), workspace_root=tmp_path)

    result = tester.check("brave")

    assert result.status == SmokeStatus.PASSED


@respx.mock
def test_smoke_tester_checks_exa_search(tmp_path: Path) -> None:
    respx.post("https://api.exa.ai/search").mock(
        return_value=Response(200, json={"results": [{"title": "Official", "url": "https://data.gov", "text": "Data"}]})
    )
    tester = ProviderSmokeTester(Settings(exa_api_key="test-key"), workspace_root=tmp_path)

    result = tester.check("exa")

    assert result.status == SmokeStatus.PASSED


@respx.mock
def test_smoke_tester_checks_no_key_official_data_provider(tmp_path: Path) -> None:
    respx.get("https://archive-api.open-meteo.com/v1/archive").mock(
        return_value=Response(200, json={"daily": {"temperature_2m_max": [1]}})
    )
    tester = ProviderSmokeTester(Settings(), workspace_root=tmp_path)

    result = tester.check("open_meteo")

    assert result.status == SmokeStatus.PASSED
```

Update `test_smoke_tester_skips_missing_provider_keys` so it includes `brave`, `exa`, `fred`, `noaa`, and `mineru`, expecting key-required providers to be skipped.

- [ ] **Step 2: Run smoke tests to verify failure**

Run: `pytest tests/test_provider_smoke.py -q`

Expected: FAIL because `brave`, `exa`, and `open_meteo` checks are unknown.

- [ ] **Step 3: Implement expanded checks**

In `src/mcm_agent/providers/smoke.py`:

- Import `BraveSearchProvider`, `ExaSearchProvider`, and official data providers.
- Add checks for `brave`, `exa`, `world_bank`, `oecd`, `undata`, `fred`, `us_census`, `noaa`, `nasa_power`, `open_meteo`, and `overpass`.
- Skip key-required checks when keys are absent: `fred`, `noaa`; `us_census` can run without a key.
- Use low-cost tiny queries:
  - World Bank: `US/SP.POP.TOTL`
  - Open-Meteo: one-day archive for latitude/longitude
  - NASA POWER: one-day point with `T2M`
  - Overpass: minimal query with timeout and output count
  - OECD/UNData: request a small dataset string and accept HTTP success.
- Continue returning `FAILED` for unknown provider names.

In `scripts/smoke_providers.py`, set:

```python
DEFAULT_PROVIDERS = [
    "llm", "tavily", "brave", "exa", "firecrawl", "humanizer", "mineru",
    "world_bank", "oecd", "undata", "fred", "us_census", "noaa",
    "nasa_power", "open_meteo", "overpass",
]
```

- [ ] **Step 4: Run smoke tests**

Run: `pytest tests/test_provider_smoke.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_provider_smoke.py src/mcm_agent/providers/smoke.py scripts/smoke_providers.py
git commit -m "feat: expand provider smoke coverage"
```

## Task 4: First-Class CLI Provider Smoke Command

**Files:**
- Modify: `tests/test_cli_config.py`
- Modify: `src/mcm_agent/cli.py`

- [ ] **Step 1: Add failing CLI smoke test**

Add to `tests/test_cli_config.py`:

```python
def test_provider_smoke_command_reports_skipped_providers(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "provider-smoke",
            "--workspace",
            str(tmp_path / "smoke"),
            "--providers",
            "llm,mineru",
        ],
    )

    assert result.exit_code == 0
    assert "SKIPPED llm" in result.output
    assert "SKIPPED mineru" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_config.py::test_provider_smoke_command_reports_skipped_providers -q`

Expected: FAIL because command does not exist.

- [ ] **Step 3: Implement CLI command**

In `src/mcm_agent/cli.py`:

- Import `ProviderSmokeTester` and `SmokeStatus`.
- Add `provider-smoke` command with `--env-file`, `--config-file`, `--workspace`, `--providers`, and `--mineru-file`.
- Print one line per result: `STATUS provider detail`.
- Exit with code 1 if any result status is `FAILED`.

- [ ] **Step 4: Run CLI tests**

Run:

```bash
pytest tests/test_cli_config.py::test_provider_smoke_command_reports_skipped_providers \
  tests/test_provider_smoke.py::test_smoke_script_accepts_json_config_file_argument -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_cli_config.py src/mcm_agent/cli.py
git commit -m "feat: expose provider smoke cli command"
```

## Task 5: Documentation And Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/WORKFLOW.md`
- Modify: `docs/PROJECT_STATUS.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update docs**

Document:

- Typesetting QA writes `review/typesetting_quality.json` and `review/typesetting_quality_report.md`.
- Final gate routes `format_issue` to `typesetting`.
- Provider smoke can be run as `mcm-agent provider-smoke --config-file mcm_agent_config.local.json`.
- Missing optional keys produce `SKIPPED`, not failure.
- No secrets or local config are committed.

- [ ] **Step 2: Run focused verification**

Run:

```bash
pytest tests/test_typesetting_qa.py tests/test_reviewer_revision.py tests/test_mvp_workflow.py tests/test_provider_smoke.py tests/test_cli_config.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full verification**

Run:

```bash
pytest -q
ruff check src tests scripts
```

Expected: PASS.

- [ ] **Step 4: Commit docs**

```bash
git add README.md docs/WORKFLOW.md docs/PROJECT_STATUS.md docs/IMPLEMENTATION_PLAN.md
git commit -m "docs: describe final qa and provider readiness"
```

## Self-Review

- Spec coverage: The plan covers LaTeX compile/layout QA, final-gate routing, first-class provider smoke, smoke expansion, docs, and verification.
- Placeholder scan: No unresolved TODO/TBD placeholders remain.
- Type consistency: `typesetting_quality.json`, `TypesettingQAAgent`, `ProviderSmokeTester`, `provider-smoke`, `format_issue`, and `typesetting` are used consistently across tasks.
