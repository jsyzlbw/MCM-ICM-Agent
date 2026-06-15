# Automatic LaTeX Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic automatic LaTeX source repair for common compile/layout failures so typesetting QA can fix safe issues before the final gate routes back to the user.

**Architecture:** Keep `TypesettingQAAgent` as the detector and add a separate `TypesettingRepairAgent` that reads `review/typesetting_quality.json`, patches only bounded patterns in `paper/main.tex`, writes a repair report, and lets QA rerun. The workflow will compile, QA, repair when possible, recompile once, and rerun QA. Repairs are conservative source rewrites, not LLM-generated LaTeX.

**Tech Stack:** Python 3.12+, Pydantic v2, regex-based LaTeX source transforms, pytest, ruff.

---

## File Structure

- Create `src/mcm_agent/agents/typesetting_repair.py`: deterministic repair agent and report models.
- Modify `src/mcm_agent/workflows/mvp.py`: call repair and rerun compile/QA once during the `typesetting` stage.
- Modify `tests/test_typesetting_qa.py`: direct repair agent behavior.
- Modify `tests/test_mvp_workflow.py`: workflow records repair artifacts.
- Modify docs: `README.md`, `docs/WORKFLOW.md`, `docs/PROJECT_STATUS.md`, `docs/IMPLEMENTATION_PLAN.md`.

## Task 1: Repair Agent Fixes Safe LaTeX Patterns

**Files:**
- Create: `src/mcm_agent/agents/typesetting_repair.py`
- Modify: `tests/test_typesetting_qa.py`

- [ ] **Step 1: Add failing repair-agent test**

Add to `tests/test_typesetting_qa.py`:

```python
def test_typesetting_repair_agent_wraps_wide_tables_and_scales_graphics(tmp_path: Path) -> None:
    from mcm_agent.agents.typesetting_repair import TypesettingRepairAgent

    workspace = create_workspace(tmp_path / "run_001")
    paper = workspace.root / "paper"
    paper.mkdir(exist_ok=True)
    (paper / "main.tex").write_text(
        "\\begin{document}\n"
        "\\includegraphics{figures/missing.png}\n"
        "\\begin{tabular}{llllllllllll}\n"
        "a & b & c & d & e & f & g & h & i & j & k & l\\\\\n"
        "\\end{tabular}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "review" / "typesetting_quality.json",
        {
            "status": "fail",
            "issue_types": ["table_overflow_risk", "figure_file_missing"],
            "blocking_findings": [
                "Wide table has 12 declared columns.",
                "Included figure file is missing: figures/missing.png",
            ],
            "repair_stage": "typesetting",
            "issues": [],
        },
    )

    report = TypesettingRepairAgent().run(workspace.root)

    tex = (paper / "main.tex").read_text(encoding="utf-8")
    assert report.status == "repaired"
    assert "\\resizebox{\\textwidth}{!}{%" in tex
    assert "\\includegraphics[width=0.9\\linewidth]{figures/missing.png}" in tex
    assert (workspace.root / "review" / "typesetting_repair_report.md").exists()
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_typesetting_qa.py::test_typesetting_repair_agent_wraps_wide_tables_and_scales_graphics -q
```

Expected: FAIL with missing module `mcm_agent.agents.typesetting_repair`.

- [ ] **Step 3: Implement repair agent**

Create:

```python
class TypesettingRepairAction(BaseModel):
    action_type: str
    message: str
    changed: bool

class TypesettingRepairReport(BaseModel):
    status: Literal["repaired", "no_action", "skipped"]
    actions: list[TypesettingRepairAction] = Field(default_factory=list)
```

Implement `TypesettingRepairAgent.run(workspace_root: Path) -> TypesettingRepairReport`:

- Read `paper/main.tex`.
- Read `review/typesetting_quality.json`.
- If status is not `fail`, write skipped report.
- For `table_overflow_risk`, wrap each unwrapped `tabular` environment with `\resizebox{\textwidth}{!}{% ... }`.
- For `figure_placement_risk` and `figure_file_missing`, add `width=0.9\linewidth` to `\includegraphics{...}` calls that lack options.
- For `equation_overflow_risk`, wrap long `equation` bodies in a `split` environment only when not already split/aligned.
- Write modified `paper/main.tex` only if changed.
- Write `review/typesetting_repair.json` and `review/typesetting_repair_report.md`.

- [ ] **Step 4: Run repair-agent test**

Run:

```bash
pytest tests/test_typesetting_qa.py::test_typesetting_repair_agent_wraps_wide_tables_and_scales_graphics -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_typesetting_qa.py src/mcm_agent/agents/typesetting_repair.py
git commit -m "feat: add deterministic latex repair agent"
```

## Task 2: Repair Agent Handles Long Equations And Records No-Action

**Files:**
- Modify: `tests/test_typesetting_qa.py`
- Modify: `src/mcm_agent/agents/typesetting_repair.py`

- [ ] **Step 1: Add failing equation/no-action tests**

Add to `tests/test_typesetting_qa.py`:

```python
def test_typesetting_repair_agent_wraps_long_equations(tmp_path: Path) -> None:
    from mcm_agent.agents.typesetting_repair import TypesettingRepairAgent

    workspace = create_workspace(tmp_path / "run_001")
    paper = workspace.root / "paper"
    paper.mkdir(exist_ok=True)
    long_rhs = " + ".join(f"x_{{{index}}}" for index in range(30))
    (paper / "main.tex").write_text(
        "\\begin{document}\n"
        "\\begin{equation}\n"
        f"y = {long_rhs}\n"
        "\\end{equation}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "review" / "typesetting_quality.json",
        {
            "status": "fail",
            "issue_types": ["equation_overflow_risk"],
            "blocking_findings": ["Long display equation may overflow the page width."],
            "repair_stage": "paper_writer",
            "issues": [],
        },
    )

    TypesettingRepairAgent().run(workspace.root)

    tex = (paper / "main.tex").read_text(encoding="utf-8")
    assert "\\begin{split}" in tex
    assert "\\end{split}" in tex
```

Add:

```python
def test_typesetting_repair_agent_reports_no_action_for_clean_quality(tmp_path: Path) -> None:
    from mcm_agent.agents.typesetting_repair import TypesettingRepairAgent

    workspace = create_workspace(tmp_path / "run_001")
    paper = workspace.root / "paper"
    paper.mkdir(exist_ok=True)
    (paper / "main.tex").write_text("\\begin{document}Short.\\end{document}\n", encoding="utf-8")
    write_json(
        workspace.root / "review" / "typesetting_quality.json",
        {"status": "pass", "issue_types": [], "blocking_findings": [], "repair_stage": None},
    )

    report = TypesettingRepairAgent().run(workspace.root)

    assert report.status == "skipped"
    repair_json = read_json(workspace.root / "review" / "typesetting_repair.json", {})
    assert repair_json["status"] == "skipped"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_typesetting_qa.py::test_typesetting_repair_agent_wraps_long_equations \
  tests/test_typesetting_qa.py::test_typesetting_repair_agent_reports_no_action_for_clean_quality -q
```

Expected: FAIL until equation and skipped handling exist.

- [ ] **Step 3: Implement equation and skipped handling**

Add helpers:

- `_wrap_long_equations(tex: str) -> tuple[str, bool]`
- `_write_repair_report(workspace_root, report)`
- safe detection for already wrapped `split`, `aligned`, or `multline`.

Status rules:

- `skipped`: QA status was not fail.
- `repaired`: at least one action changed source.
- `no_action`: QA failed but no safe action applied.

- [ ] **Step 4: Run typesetting repair tests**

Run:

```bash
pytest tests/test_typesetting_qa.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_typesetting_qa.py src/mcm_agent/agents/typesetting_repair.py
git commit -m "feat: repair long equations and report skipped latex repairs"
```

## Task 3: Workflow Reruns QA After Repair

**Files:**
- Modify: `tests/test_mvp_workflow.py`
- Modify: `src/mcm_agent/workflows/mvp.py`

- [ ] **Step 1: Add failing workflow test**

Add to `tests/test_mvp_workflow.py`:

```python
def test_typesetting_stage_records_repair_artifacts(tmp_path: Path) -> None:
    workspace = tmp_path / "task"
    problem = tmp_path / "problem.md"
    attachment = tmp_path / "data.csv"
    problem.write_text("# Problem\n\nUse references and produce a paper.", encoding="utf-8")
    attachment.write_text("x,y\n1,2\n2,3\n", encoding="utf-8")

    class RepairLatexProvider(InjectedLatexProvider):
        def compile(self, paper_dir: Path) -> LatexCompileResult:
            result = super().compile(paper_dir)
            text = (paper_dir / "main.tex").read_text(encoding="utf-8")
            if "\\resizebox{\\textwidth}{!}{%" not in text:
                (paper_dir / "compile_log.txt").write_text("Overfull \\hbox\n", encoding="utf-8")
            return result

    providers = ProviderBundle(
        llm=FakeLLMProvider({"default": ""}),
        mineru=InjectedMinerUProvider(),
        search=InjectedSearchProvider(),
        extractor=InjectedExtractProvider(),
        official_data=None,
        humanizer=FakeHumanizerProvider({}),
        latex=RepairLatexProvider(),
    )

    run_mvp_workflow(
        workspace,
        TaskInput(problem_file=problem, attachments=[attachment]),
        providers=providers,
        auto_approve=True,
    )

    assert (workspace / "review" / "typesetting_repair.json").exists()
    assert (workspace / "review" / "typesetting_repair_report.md").exists()
```

If this test is too broad, use the stage handler directly through `build_stage_handlers` with a prepared workspace.

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_mvp_workflow.py::test_typesetting_stage_records_repair_artifacts -q
```

Expected: FAIL because workflow never calls `TypesettingRepairAgent`.

- [ ] **Step 3: Integrate repair into workflow**

In `src/mcm_agent/workflows/mvp.py`:

- Import `TypesettingRepairAgent`.
- In `typesetting`, after first `_compile_latex` and `TypesettingQAAgent().run`, call repair.
- If repair status is `repaired`, call `_compile_latex` once more and rerun `TypesettingQAAgent`.
- Include `review/typesetting_repair.json` and `review/typesetting_repair_report.md` in returned artifacts.

Avoid infinite loops; only one repair pass.

- [ ] **Step 4: Run workflow test**

Run:

```bash
pytest tests/test_mvp_workflow.py::test_typesetting_stage_records_repair_artifacts -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_mvp_workflow.py src/mcm_agent/workflows/mvp.py
git commit -m "feat: rerun typesetting qa after latex repair"
```

## Task 4: QA Report Includes Repair Status

**Files:**
- Modify: `tests/test_typesetting_qa.py`
- Modify: `src/mcm_agent/agents/typesetting_qa.py`

- [ ] **Step 1: Add failing QA report test**

Add to `tests/test_typesetting_qa.py`:

```python
def test_typesetting_qa_report_mentions_repair_status(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    paper = workspace.root / "paper"
    paper.mkdir(exist_ok=True)
    (paper / "main.tex").write_text("\\begin{document}\nShort.\\end{document}\n", encoding="utf-8")
    (paper / "main.pdf").write_bytes(b"%PDF")
    (paper / "compile_log.txt").write_text("Latexmk: All targets are up-to-date\n", encoding="utf-8")
    write_json(
        workspace.root / "review" / "typesetting_repair.json",
        {"status": "repaired", "actions": [{"action_type": "scale_graphics", "message": "Scaled graphics.", "changed": True}]},
    )

    TypesettingQAAgent().run(workspace.root)

    markdown = (workspace.root / "review" / "typesetting_quality_report.md").read_text(encoding="utf-8")
    assert "Repair status: repaired" in markdown
    assert "Scaled graphics." in markdown
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_typesetting_qa.py::test_typesetting_qa_report_mentions_repair_status -q
```

Expected: FAIL because QA report does not mention repair artifacts.

- [ ] **Step 3: Include repair summary in QA markdown**

In `TypesettingQAAgent._write_reports`, read `review/typesetting_repair.json` and append:

- `## Repair Summary`
- `- Repair status: ...`
- one line per action.

Do not change pass/fail semantics.

- [ ] **Step 4: Run typesetting tests**

Run:

```bash
pytest tests/test_typesetting_qa.py tests/test_mvp_workflow.py::test_typesetting_stage_records_repair_artifacts -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_typesetting_qa.py src/mcm_agent/agents/typesetting_qa.py
git commit -m "feat: summarize latex repairs in typesetting qa"
```

## Task 5: Documentation And Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/WORKFLOW.md`
- Modify: `docs/PROJECT_STATUS.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update docs**

Document:

- Automatic LaTeX repair is deterministic and pattern-limited.
- Repair artifacts: `review/typesetting_repair.json` and `review/typesetting_repair_report.md`.
- The workflow runs one repair pass and reruns compile/QA.
- Remaining complex layout failures still route to the final gate.

- [ ] **Step 2: Run focused verification**

Run:

```bash
pytest tests/test_typesetting_qa.py tests/test_mvp_workflow.py::test_run_demo_workflow_creates_required_artifacts -q
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
git commit -m "docs: describe automatic latex repair"
```

## Self-Review

- Spec coverage: The plan covers deterministic repair actions, workflow rerun, QA reporting, docs, and verification.
- Placeholder scan: No unresolved TODO/TBD placeholders remain.
- Type consistency: `TypesettingRepairAgent`, `TypesettingRepairReport`, `typesetting_repair.json`, and `typesetting_repair_report.md` are used consistently.
