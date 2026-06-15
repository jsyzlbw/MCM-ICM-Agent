# Next Roadmap And Claim-Aware Paper Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the current traceable paper pipeline into a higher-quality MCM/ICM paper generator whose sections form a coherent claim-aware argument.

**Architecture:** Keep the existing workflow graph and provider abstractions. Add a small paper-context layer that reads existing artifacts, enrich `ClaimPlanningAgent` from that context, render stronger section drafts from planned claims, and make `ReviewerAgent` score paper quality in addition to evidence binding. Leave real official-data expansion, PDF RAG ingestion, and LaTeX layout repair as separate follow-up routes.

**Tech Stack:** Python 3, Pydantic models, Typer CLI, pytest, SQLite FTS5, existing fake-provider test harness.

---

## Roadmap After A Route

The A route is complete: JSON config is wired through CLI/smoke, `knowledge_base/` is local-only and empty by default, and RAG ingests `.md` / `.txt` while reporting `.pdf` as pending.

Next phases should proceed in this order:

1. **B Route: High Quality Claim-Aware Paper Generation**
   - Enrich `claim_plan.json` from problem context, model decision, validation, RAG hits, evidence, figures, and sources.
   - Improve abstract, introduction, assumptions, model, results, sensitivity, limitations, and conclusion sections.
   - Add quality scoring in final review.

2. **C Route: Real Modeling Capability Expansion**
   - Improve model route selection and solver module orchestration for more MCM/ICM problem types.
   - Add stronger generated code contracts while preserving deterministic fallback modules.

3. **D Route: Official Data API Expansion**
   - Add OECD, UNData, US Census, NOAA/NASA/Open-Meteo, and OSM/Overpass adapters.
   - Extend provider smoke coverage and source-lineage records.

4. **E Route: RAG Completeness**
   - Add MinerU-backed PDF ingestion, chunking, provenance metadata, and retrieval usage notes.
   - Let writing and modeling retrieve from user method notes, rules, and excellent-paper examples.

5. **F Route: LaTeX And Layout QA**
   - Detect compile errors, table overflow, equation overflow, figure placement issues, and page-limit risk.
   - Route layout failures back to writer, visualization, or typesetting.

This plan implements only the B route.

---

## File Structure

Create:

- `src/mcm_agent/agents/paper_context.py`
  - Reads existing workspace artifacts and exposes a compact `PaperContext` model for claim planning and writing.

- `src/mcm_agent/agents/paper_sections.py`
  - Renders section-level LaTeX from planned claims and paper context. Keeps `writer.py` from becoming the only place where paper prose logic lives.

- `tests/test_paper_context.py`
  - Unit tests for context extraction.

Modify:

- `src/mcm_agent/agents/claim_planning.py`
  - Use `PaperContext` to create stronger assumption, model-formulation, result, sensitivity, limitation, and conclusion claims.

- `src/mcm_agent/agents/writer.py`
  - Delegate claim-plan section rendering to `paper_sections.py`.

- `src/mcm_agent/agents/reviewer.py`
  - Add paper-quality scoring and route poor paper quality to `paper_writer`.

- `src/mcm_agent/agents/rag.py`
  - Retrieve multiple methodology query types instead of only `figure design`.

- Existing tests:
  - `tests/test_claim_planning.py`
  - `tests/test_llm_agents.py`
  - `tests/test_paper_evidence_binding.py`
  - `tests/test_reviewer_revision.py`
  - `tests/test_rag.py`
  - `tests/test_mvp_workflow.py`

Update docs:

- `README.md`
- `docs/WORKFLOW.md`
- `docs/PROJECT_STATUS.md`
- `docs/IMPLEMENTATION_PLAN.md`

---

## Task 1: Paper Context Builder

**Files:**
- Create: `src/mcm_agent/agents/paper_context.py`
- Test: `tests/test_paper_context.py`

- [ ] **Step 1: Write failing context extraction tests**

Add `tests/test_paper_context.py`:

```python
from pathlib import Path

from mcm_agent.agents.paper_context import build_paper_context
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import write_json


def test_build_paper_context_reads_core_paper_inputs(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "problem_understanding.md").write_text(
        "# Problem Understanding\n\nNeed a resilient evacuation allocation model.",
        encoding="utf-8",
    )
    (workspace.root / "discussion" / "confirmed_direction.md").write_text(
        "# Confirmed Direction\n\nUse interpretable optimization.",
        encoding="utf-8",
    )
    (workspace.root / "reports" / "model_decision.md").write_text(
        "# Model Decision\n\nSelected constrained optimization with TOPSIS ranking.",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {
            "selected_routes": ["multi_criteria_evaluation", "constrained_optimization"],
            "route_metrics": {"priority_score_mean": {"value": 0.6}},
        },
    )
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [{"evidence_id": "ev_priority", "claim": "Priority score mean equals 0.6."}],
    )
    write_json(
        workspace.root / "figures" / "figure_registry.json",
        [{"figure_id": "fig_priority", "claim_supported": "Priority ranking supports allocation."}],
    )
    write_json(workspace.root / "data" / "source_registry.json", [{"source_id": "web_001"}])

    context = build_paper_context(workspace.root)

    assert "evacuation allocation" in context.problem_summary
    assert "interpretable optimization" in context.direction_summary
    assert context.selected_routes == ["multi_criteria_evaluation", "constrained_optimization"]
    assert context.primary_evidence_ids == ["ev_priority"]
    assert context.primary_figure_ids == ["fig_priority"]
    assert context.primary_source_ids == ["web_001"]


def test_build_paper_context_reads_rag_notes_and_limitations(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "validation_report.md").write_text(
        "# Validation Report\n\nLimitation: private mobility data is unavailable.",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "rag" / "methodology_hits.json",
        [{"title": "Assumption Guide", "content": "State assumptions before model equations."}],
    )

    context = build_paper_context(workspace.root)

    assert "private mobility data" in context.validation_summary
    assert context.methodology_notes == ["Assumption Guide: State assumptions before model equations."]
```

- [ ] **Step 2: Run tests and verify red**

Run:

```bash
pytest tests/test_paper_context.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'mcm_agent.agents.paper_context'`.

- [ ] **Step 3: Implement `paper_context.py`**

Create `src/mcm_agent/agents/paper_context.py`:

```python
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from mcm_agent.utils.json_io import read_json


class PaperContext(BaseModel):
    problem_summary: str = ""
    direction_summary: str = ""
    model_decision_summary: str = ""
    validation_summary: str = ""
    selected_routes: list[str] = Field(default_factory=list)
    route_metric_names: list[str] = Field(default_factory=list)
    primary_evidence_ids: list[str] = Field(default_factory=list)
    primary_figure_ids: list[str] = Field(default_factory=list)
    primary_source_ids: list[str] = Field(default_factory=list)
    methodology_notes: list[str] = Field(default_factory=list)


def build_paper_context(workspace_root: Path) -> PaperContext:
    route_summary = read_json(workspace_root / "results" / "model_route_summary.json", {})
    evidence_rows = _rows(read_json(workspace_root / "results" / "evidence_registry.json", []))
    figure_rows = _rows(read_json(workspace_root / "figures" / "figure_registry.json", []))
    source_rows = _rows(read_json(workspace_root / "data" / "source_registry.json", []))
    rag_rows = _rows(read_json(workspace_root / "rag" / "methodology_hits.json", []))
    routes = route_summary.get("selected_routes", []) if isinstance(route_summary, dict) else []
    metrics = route_summary.get("route_metrics", {}) if isinstance(route_summary, dict) else {}
    return PaperContext(
        problem_summary=_summarize_markdown(workspace_root / "reports" / "problem_understanding.md"),
        direction_summary=_summarize_markdown(workspace_root / "discussion" / "confirmed_direction.md"),
        model_decision_summary=_summarize_markdown(workspace_root / "reports" / "model_decision.md"),
        validation_summary=_summarize_markdown(workspace_root / "reports" / "validation_report.md"),
        selected_routes=[str(item) for item in routes] if isinstance(routes, list) else [],
        route_metric_names=[str(key) for key in metrics.keys()] if isinstance(metrics, dict) else [],
        primary_evidence_ids=_ids(evidence_rows, "evidence_id", limit=3),
        primary_figure_ids=_ids(figure_rows, "figure_id", limit=3),
        primary_source_ids=_ids(source_rows, "source_id", limit=3),
        methodology_notes=_methodology_notes(rag_rows, limit=5),
    )


def _summarize_markdown(path: Path, *, max_chars: int = 500) -> str:
    if not path.exists():
        return ""
    text = " ".join(line.strip("# ").strip() for line in path.read_text(encoding="utf-8").splitlines())
    return " ".join(text.split())[:max_chars]


def _rows(value: object) -> list[dict[str, object]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _ids(rows: list[dict[str, object]], key: str, *, limit: int) -> list[str]:
    return [str(row[key]) for row in rows if row.get(key)][:limit]


def _methodology_notes(rows: list[dict[str, object]], *, limit: int) -> list[str]:
    notes: list[str] = []
    for row in rows[:limit]:
        title = str(row.get("title", "Methodology note"))
        content = str(row.get("content", "")).strip()
        if content:
            notes.append(f"{title}: {content[:240]}")
    return notes
```

- [ ] **Step 4: Run tests and verify green**

Run:

```bash
pytest tests/test_paper_context.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/agents/paper_context.py tests/test_paper_context.py
git commit -m "feat: build paper context for claim-aware writing"
```

---

## Task 2: Enrich Claim Planning

**Files:**
- Modify: `src/mcm_agent/agents/claim_planning.py`
- Test: `tests/test_claim_planning.py`

- [ ] **Step 1: Write failing claim planning tests**

Append to `tests/test_claim_planning.py`:

```python
def test_claim_planning_uses_context_for_assumptions_model_and_limitations(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "problem_understanding.md").write_text(
        "# Problem Understanding\n\nThe problem requires evacuation capacity assumptions.",
        encoding="utf-8",
    )
    (workspace.root / "reports" / "model_decision.md").write_text(
        "# Model Decision\n\nThe model combines TOPSIS ranking with constrained allocation.",
        encoding="utf-8",
    )
    (workspace.root / "reports" / "validation_report.md").write_text(
        "# Validation Report\n\nLimitation: mobility data is incomplete.",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {"selected_routes": ["multi_criteria_evaluation"], "route_metrics": {}},
    )
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [{"evidence_id": "ev_capacity", "claim": "Capacity constraints are feasible."}],
    )
    write_json(
        workspace.root / "figures" / "figure_registry.json",
        [{"figure_id": "fig_capacity", "status": "approved", "source_ids": ["web_001"]}],
    )
    write_json(workspace.root / "data" / "source_registry.json", [{"source_id": "web_001"}])

    ClaimPlanningAgent().run(workspace.root)

    plan = read_json(workspace.root / "paper" / "claim_plan.json", [])
    claim_types = {item["claim_type"] for item in plan}
    claim_text = "\n".join(item["claim_text"] for item in plan)
    assert "assumption" in claim_types
    assert "model_choice" in claim_types
    assert "limitation" in claim_types
    assert "evacuation capacity" in claim_text
    assert "TOPSIS ranking" in claim_text
    assert "mobility data is incomplete" in claim_text
```

- [ ] **Step 2: Run test and verify red**

Run:

```bash
pytest tests/test_claim_planning.py::test_claim_planning_uses_context_for_assumptions_model_and_limitations -q
```

Expected: fail because contextual assumption/model/limitation claim text is not generated.

- [ ] **Step 3: Import and use `build_paper_context`**

Modify `src/mcm_agent/agents/claim_planning.py`:

```python
from mcm_agent.agents.paper_context import PaperContext, build_paper_context
```

In `ClaimPlanningAgent.run`, add:

```python
context = build_paper_context(workspace_root)
```

Then build the claim list as:

```python
claims.extend(self._assumption_claims(context, evidence, sources))
claims.extend(self._model_claims(route_summary, evidence, figures, sources, context))
claims.extend(self._metric_claims(evidence, figures, sources))
claims.extend(self._figure_claims(figures))
claims.extend(self._sensitivity_claims(evidence, figures, sources, context))
claims.extend(self._limitation_claims(validation_text, evidence, sources, context))
claims.append(self._conclusion_claim(evidence, figures, sources, context))
```

- [ ] **Step 4: Add contextual claim helpers**

Add methods to `ClaimPlanningAgent`:

```python
def _assumption_claims(
    self,
    context: PaperContext,
    evidence: list[dict[str, object]],
    sources: list[dict[str, object]],
) -> list[PaperClaimPlanItem]:
    support = self._ids(evidence[:1], "evidence_id") or self._ids(sources[:1], "source_id")
    if not support:
        return []
    text = context.problem_summary or "The model uses explicit assumptions to connect problem conditions to computable variables."
    return [
        PaperClaimPlanItem(
            claim_id="claim_assumption_problem_context",
            section="paper/sections/assumptions.tex",
            claim_text="The modeling assumptions are grounded in the problem context: " + text,
            claim_type="assumption",
            evidence_ids=self._ids(evidence[:1], "evidence_id"),
            source_ids=self._ids(sources[:1], "source_id"),
            priority="major",
        )
    ]
```

Update `_model_claims`, `_sensitivity_claims`, `_limitation_claims`, and `_conclusion_claim` signatures to accept `context: PaperContext`. Keep old behavior when context fields are empty. For limitation text, prefer:

```python
limitation_text = context.validation_summary or validation_text
```

- [ ] **Step 5: Run tests and verify green**

Run:

```bash
pytest tests/test_claim_planning.py -q
```

Expected: all claim planning tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/mcm_agent/agents/claim_planning.py tests/test_claim_planning.py
git commit -m "feat: enrich claim planning from paper context"
```

---

## Task 3: Section Renderer For Claim-Aware Paper Drafts

**Files:**
- Create: `src/mcm_agent/agents/paper_sections.py`
- Modify: `src/mcm_agent/agents/writer.py`
- Test: `tests/test_llm_agents.py`
- Test: `tests/test_paper_evidence_binding.py`

- [ ] **Step 1: Write failing writer tests**

Append to `tests/test_llm_agents.py`:

```python
def test_paper_writer_renders_contextual_abstract_intro_and_assumptions(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "problem_understanding.md").write_text(
        "# Problem Understanding\n\nNeed an evacuation allocation model.",
        encoding="utf-8",
    )
    (workspace.root / "discussion" / "confirmed_direction.md").write_text(
        "# Confirmed Direction\n\nUse interpretable optimization.",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "paper" / "claim_plan.json",
        [
            {
                "claim_id": "claim_assumption_problem_context",
                "section": "paper/sections/assumptions.tex",
                "claim_text": "Capacity assumptions define feasible allocation.",
                "claim_type": "assumption",
                "evidence_ids": ["ev_capacity"],
                "priority": "major",
            },
            {
                "claim_id": "claim_model_route",
                "section": "paper/sections/model.tex",
                "claim_text": "The selected model combines ranking and allocation.",
                "claim_type": "model_choice",
                "evidence_ids": ["ev_capacity"],
                "priority": "critical",
            },
        ],
    )
    write_json(workspace.root / "results" / "evidence_registry.json", [{"evidence_id": "ev_capacity"}])

    PaperWriterAgent().run(workspace.root)

    abstract = (workspace.root / "paper" / "sections" / "abstract.tex").read_text(encoding="utf-8")
    introduction = (workspace.root / "paper" / "sections" / "introduction.tex").read_text(encoding="utf-8")
    assumptions = (workspace.root / "paper" / "sections" / "assumptions.tex").read_text(encoding="utf-8")
    assert "evacuation allocation" in abstract
    assert "interpretable optimization" in introduction
    assert "Capacity assumptions define feasible allocation" in assumptions
    assert "% claim_id=claim_assumption_problem_context evidence_id=ev_capacity" in assumptions
```

- [ ] **Step 2: Run test and verify red**

Run:

```bash
pytest tests/test_llm_agents.py::test_paper_writer_renders_contextual_abstract_intro_and_assumptions -q
```

Expected: fail because current claim-plan writer uses static abstract/introduction and simple claim paragraphs.

- [ ] **Step 3: Implement `paper_sections.py`**

Create `src/mcm_agent/agents/paper_sections.py`:

```python
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from mcm_agent.agents.paper_context import PaperContext
from mcm_agent.core.models import PaperClaimPlanItem


SECTION_TITLES = {
    "abstract.tex": "\\section*{Abstract}",
    "introduction.tex": "\\section{Introduction}",
    "assumptions.tex": "\\section{Assumptions}",
    "model.tex": "\\section{Model}",
    "results.tex": "\\section{Results}",
    "sensitivity.tex": "\\section{Sensitivity Analysis}",
    "conclusion.tex": "\\section{Conclusion}",
}


def render_claim_plan_sections(
    claim_plan: list[PaperClaimPlanItem],
    context: PaperContext,
) -> dict[str, str]:
    grouped: dict[str, list[PaperClaimPlanItem]] = defaultdict(list)
    for claim in claim_plan:
        grouped[Path(claim.section).name].append(claim)
    sections: dict[str, str] = {
        "abstract.tex": _render_abstract(context, claim_plan),
        "introduction.tex": _render_introduction(context, claim_plan),
    }
    for filename in ["assumptions.tex", "model.tex", "results.tex", "sensitivity.tex", "conclusion.tex"]:
        sections[filename] = _render_claim_section(filename, grouped.get(filename, []), context)
    return sections


def render_claim_paragraph(claim: PaperClaimPlanItem) -> str:
    evidence_id = claim.evidence_ids[0] if claim.evidence_ids else "missing"
    figure_id = claim.figure_ids[0] if claim.figure_ids else "missing"
    source_id = claim.source_ids[0] if claim.source_ids else "missing"
    trace = (
        f"% claim_id={claim.claim_id} "
        f"evidence_id={evidence_id} "
        f"figure_id={figure_id} "
        f"source_id={source_id}"
    )
    if claim.status == "unresolved":
        body = f"The planned claim \\texttt{{{_latex_escape(claim.claim_id)}}} remains unresolved: {_latex_escape(claim.unresolved_reason)}."
    else:
        body = _latex_escape(claim.claim_text)
    return body + "\n" + trace


def _render_abstract(context: PaperContext, claim_plan: list[PaperClaimPlanItem]) -> str:
    critical = [claim.claim_text for claim in claim_plan if claim.priority == "critical" and claim.status != "unresolved"]
    return "\n".join(
        [
            SECTION_TITLES["abstract.tex"],
            (
                "This paper studies "
                + _latex_escape(context.problem_summary or "the contest problem")
                + " using "
                + _latex_escape(", ".join(context.selected_routes) or "a traceable modeling workflow")
                + "."
            ),
            _latex_escape(" ".join(critical[:2])),
            "",
        ]
    )


def _render_introduction(context: PaperContext, claim_plan: list[PaperClaimPlanItem]) -> str:
    return "\n".join(
        [
            SECTION_TITLES["introduction.tex"],
            _latex_escape(context.problem_summary or "The problem is decomposed into data, model, and validation tasks."),
            _latex_escape(context.direction_summary or "The confirmed direction emphasizes interpretable and reproducible modeling."),
            "The remainder of the paper follows the planned claim chain from assumptions to validated results.",
            "",
        ]
    )


def _render_claim_section(filename: str, claims: list[PaperClaimPlanItem], context: PaperContext) -> str:
    title = SECTION_TITLES.get(filename, "\\section{Planned Claims}")
    paragraphs = [render_claim_paragraph(claim) for claim in claims]
    if filename == "model.tex" and context.model_decision_summary:
        paragraphs.insert(0, _latex_escape(context.model_decision_summary))
    if filename == "sensitivity.tex" and context.validation_summary:
        paragraphs.append(_latex_escape("Validation context: " + context.validation_summary))
    return "\n\n".join([title, *(paragraphs or ["No planned claims were available for this section."]), ""])


def _latex_escape(value: str) -> str:
    return value.replace("_", "\\_")
```

- [ ] **Step 4: Update `PaperWriterAgent` to delegate rendering**

In `src/mcm_agent/agents/writer.py`, import:

```python
from mcm_agent.agents.paper_context import build_paper_context
from mcm_agent.agents.paper_sections import render_claim_paragraph, render_claim_plan_sections
```

In `run`, when `claim_plan` exists:

```python
context = build_paper_context(workspace_root)
self._write_claim_plan_sections(workspace_root, section_dir, claim_plan, context)
```

Change `_write_claim_plan_sections` to:

```python
def _write_claim_plan_sections(
    self,
    workspace_root: Path,
    section_dir: Path,
    claim_plan: list[PaperClaimPlanItem],
    context: PaperContext,
) -> None:
    section_content = render_claim_plan_sections(claim_plan, context)
    for claim in claim_plan:
        if claim.status == "unresolved":
            self._append_unresolved_claim(workspace_root, claim)
    for filename, content in section_content.items():
        (section_dir / filename).write_text(content, encoding="utf-8")
```

Keep `_claim_plan_paragraph` as a compatibility wrapper and replace its body with:

```python
return render_claim_paragraph(claim)
```

- [ ] **Step 5: Run writer and paper evidence tests**

Run:

```bash
pytest tests/test_llm_agents.py tests/test_paper_evidence_binding.py tests/test_latex.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/mcm_agent/agents/paper_sections.py src/mcm_agent/agents/writer.py tests/test_llm_agents.py tests/test_paper_evidence_binding.py
git commit -m "feat: render stronger claim-aware paper sections"
```

---

## Task 4: Multi-Query Methodology RAG For Writing

**Files:**
- Modify: `src/mcm_agent/agents/rag.py`
- Test: `tests/test_rag.py`

- [ ] **Step 1: Write failing RAG test**

Append to `tests/test_rag.py`:

```python
def test_methodology_rag_agent_retrieves_multiple_paper_quality_queries(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    knowledge_base = tmp_path / "knowledge_base"
    knowledge_base.mkdir()
    (knowledge_base / "writing_notes.md").write_text(
        "Assumption writing should precede model formulation. "
        "Limitation discussion should connect validation to interpretation. "
        "Figure design should support the main claim.",
        encoding="utf-8",
    )

    MethodologyRAGAgent().run(
        workspace.root,
        supervisor_skills_dir=None,
        knowledge_base_dir=knowledge_base,
    )

    hits = read_json(workspace.root / "rag" / "methodology_hits.json", [])
    queries = {item["query"] for item in hits}
    assert {"assumption writing", "model formulation", "limitation discussion", "figure design"} <= queries
```

- [ ] **Step 2: Run test and verify red**

Run:

```bash
pytest tests/test_rag.py::test_methodology_rag_agent_retrieves_multiple_paper_quality_queries -q
```

Expected: fail because `methodology_hits.json` rows do not include `query` and only use `figure design`.

- [ ] **Step 3: Add query metadata without breaking old readers**

Update `MethodologyHit` in `src/mcm_agent/agents/rag.py`:

```python
class MethodologyHit(BaseModel):
    source: str
    title: str
    content: str
    rank: int
    query: str = ""
```

Add constants:

```python
PAPER_QUALITY_QUERIES = [
    "assumption writing",
    "model formulation",
    "limitation discussion",
    "figure design",
    "pre submission review",
]
```

Add helper:

```python
def search_methodology_queries(store: MethodologyStore, queries: list[str]) -> list[MethodologyHit]:
    hits: list[MethodologyHit] = []
    for query in queries:
        for hit in store.search(query, limit=3):
            hits.append(hit.model_copy(update={"query": query}))
    return hits
```

In `MethodologyRAGAgent.run`, replace:

```python
hits = store.search("figure design", limit=5)
```

with:

```python
hits = search_methodology_queries(store, PAPER_QUALITY_QUERIES)
```

- [ ] **Step 4: Run RAG tests**

Run:

```bash
pytest tests/test_rag.py -q
```

Expected: all RAG tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/agents/rag.py tests/test_rag.py
git commit -m "feat: retrieve methodology hits for paper quality"
```

---

## Task 5: Reviewer Paper Quality Scoring

**Files:**
- Modify: `src/mcm_agent/agents/reviewer.py`
- Test: `tests/test_reviewer_revision.py`

- [ ] **Step 1: Write failing reviewer quality tests**

Add this helper near the top of `tests/test_reviewer_revision.py`:

```python
def _write_complete_paper_sections(workspace_root: Path) -> None:
    section_dir = workspace_root / "paper" / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "abstract.tex",
        "introduction.tex",
        "assumptions.tex",
        "model.tex",
        "results.tex",
        "sensitivity.tex",
        "conclusion.tex",
    ]:
        (section_dir / name).write_text(
            "\\section{X}\nClaim text.\n% claim_id=claim_x evidence_id=ev_001 figure_id=missing source_id=missing\n",
            encoding="utf-8",
        )
```

Call `_write_complete_paper_sections(workspace.root)` inside
`test_reviewer_writes_reports_and_passes_clean_workspace` before `ReviewerAgent().run`.

Append to `tests/test_reviewer_revision.py`:

```python
def test_reviewer_writes_paper_quality_scores(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    _write_complete_paper_sections(workspace.root)
    write_json(workspace.root / "results" / "evidence_registry.json", [{"evidence_id": "ev_001"}])
    write_json(workspace.root / "review" / "paper_evidence_bindings.json", [])

    ReviewerAgent().run(workspace.root)

    scores = read_json(workspace.root / "review" / "paper_quality_scores.json", {})
    assert scores["section_completeness"] == 1.0
    assert scores["claim_trace_density"] > 0
    assert scores["status"] == "pass"


def test_reviewer_blocks_incomplete_paper_sections(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    section_dir = workspace.root / "paper" / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    (section_dir / "results.tex").write_text("\\section{Results}\nOnly results.\n", encoding="utf-8")

    ReviewerAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "final_gate.json", {})
    scores = read_json(workspace.root / "review" / "paper_quality_scores.json", {})
    assert scores["status"] == "fail"
    assert gate["status"] == "fail"
    assert gate["repair_stage"] == "paper_writer"
    assert "Paper section completeness is too low." in gate["blocking_findings"]
```

- [ ] **Step 2: Run tests and verify red**

Run:

```bash
pytest tests/test_reviewer_revision.py::test_reviewer_writes_paper_quality_scores tests/test_reviewer_revision.py::test_reviewer_blocks_incomplete_paper_sections -q
```

Expected: fail because `paper_quality_scores.json` is not written.

- [ ] **Step 3: Add scoring helper**

In `src/mcm_agent/agents/reviewer.py`, add:

```python
REQUIRED_PAPER_SECTIONS = {
    "abstract.tex",
    "introduction.tex",
    "assumptions.tex",
    "model.tex",
    "results.tex",
    "sensitivity.tex",
    "conclusion.tex",
}
```

Add method:

```python
def _score_paper_quality(self, workspace_root: Path) -> dict[str, object]:
    section_dir = workspace_root / "paper" / "sections"
    present = set()
    trace_lines = 0
    total_lines = 0
    if section_dir.exists():
        for section in section_dir.glob("*.tex"):
            text = section.read_text(encoding="utf-8")
            if text.strip():
                present.add(section.name)
            lines = [line for line in text.splitlines() if line.strip()]
            total_lines += len(lines)
            trace_lines += sum(1 for line in lines if "claim_id=" in line)
    completeness = len(present & REQUIRED_PAPER_SECTIONS) / len(REQUIRED_PAPER_SECTIONS)
    trace_density = trace_lines / total_lines if total_lines else 0.0
    status = "pass" if completeness >= 0.85 and trace_density > 0 else "fail"
    return {
        "section_completeness": round(completeness, 3),
        "claim_trace_density": round(trace_density, 3),
        "status": status,
        "missing_sections": sorted(REQUIRED_PAPER_SECTIONS - present),
    }
```

In `run`, before `record_gate_decision`, write scores:

```python
quality_scores = self._score_paper_quality(workspace_root)
write_json(workspace_root / "review" / "paper_quality_scores.json", quality_scores)
if quality_scores["status"] == "fail":
    blocking.append("Paper section completeness is too low.")
```

Import `write_json`:

```python
from mcm_agent.utils.json_io import read_json, write_json
```

- [ ] **Step 4: Run reviewer tests**

Run:

```bash
pytest tests/test_reviewer_revision.py tests/test_gate_decisions.py tests/test_submission.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/agents/reviewer.py tests/test_reviewer_revision.py tests/test_gate_decisions.py tests/test_submission.py
git commit -m "feat: score claim-aware paper quality"
```

---

## Task 6: End-To-End Workflow Assertion For Better Paper Artifacts

**Files:**
- Modify: `tests/test_mvp_workflow.py`
- Modify: `src/mcm_agent/core/workflow_graph.py`

- [ ] **Step 1: Add end-to-end assertions**

In `tests/test_mvp_workflow.py`, extend `test_run_demo_workflow_creates_required_artifacts` required outputs:

```python
"review/paper_quality_scores.json",
```

After existing stage-order assertions, add:

```python
paper_quality = read_json(workspace / "review" / "paper_quality_scores.json", {})
assert paper_quality["status"] == "pass"
abstract = (workspace / "paper" / "sections" / "abstract.tex").read_text(encoding="utf-8")
introduction = (workspace / "paper" / "sections" / "introduction.tex").read_text(encoding="utf-8")
assumptions = (workspace / "paper" / "sections" / "assumptions.tex").read_text(encoding="utf-8")
assert "traceable" in abstract.lower() or "model" in abstract.lower()
assert "planned claim chain" in introduction
assert "assumption" in assumptions.lower()
```

- [ ] **Step 2: Run workflow test and verify red or green**

Run:

```bash
pytest tests/test_mvp_workflow.py::test_run_demo_workflow_creates_required_artifacts -q
```

Expected before Task 5 implementation: fail because `review/paper_quality_scores.json` is missing. Expected after Task 5: pass or reveal paper-section wording gaps.

- [ ] **Step 3: Register new artifact in workflow graph**

In `src/mcm_agent/core/workflow_graph.py`, update the `pre_submission_review` node
`output_artifacts` list to include the new reviewer artifact:

```python
output_artifacts=[
    "review/reviewer_report.md",
    "review/originality_report.md",
    "review/paper_quality_scores.json",
],
```

- [ ] **Step 4: Run workflow-related tests**

Run:

```bash
pytest tests/test_mvp_workflow.py tests/test_workflow_topology.py tests/test_workspace_registry.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_mvp_workflow.py src/mcm_agent/core/workflow_graph.py
git commit -m "test: assert paper quality artifacts in workflow"
```

---

## Task 7: Documentation And Final Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/WORKFLOW.md`
- Modify: `docs/PROJECT_STATUS.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update docs**

Document:

- `paper/claim_plan.json` now includes assumption, model, result, sensitivity, limitation, and conclusion claims from paper context.
- `PaperWriterAgent` renders contextual abstract, introduction, assumptions, model, results, sensitivity, and conclusion sections from planned claims.
- `review/paper_quality_scores.json` summarizes section completeness and claim trace density.
- B route is complete; C route is the next recommended phase.

- [ ] **Step 2: Run full tests**

Run:

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Run lint**

Run:

```bash
ruff check src tests scripts
```

Expected: `All checks passed!`

- [ ] **Step 4: Commit docs**

```bash
git add README.md docs/WORKFLOW.md docs/PROJECT_STATUS.md docs/IMPLEMENTATION_PLAN.md
git commit -m "docs: describe claim-aware paper quality route"
```

- [ ] **Step 5: Push**

```bash
git status --short --branch
git push origin main
```

Expected: `main` pushes cleanly to GitHub.

---

## Acceptance Criteria

- `ClaimPlanningAgent` generates context-aware assumption, model-choice, metric-result, sensitivity, limitation, and conclusion claims.
- `PaperWriterAgent` renders every planned critical and major claim into the intended section with trace comments near the prose.
- Abstract and introduction are no longer static boilerplate when context artifacts exist.
- Assumptions, model, results, sensitivity, and conclusion sections use paper context and planned claims.
- `MethodologyRAGAgent` retrieves multiple paper-quality query types.
- `ReviewerAgent` writes `review/paper_quality_scores.json`.
- Final review fails incomplete papers and routes them to `paper_writer`.
- Full verification passes:

```bash
pytest -q
ruff check src tests scripts
```

## Self-Review

- Spec coverage: The plan covers B route paper context, claim planning, writing, RAG retrieval, reviewer quality gate, docs, and verification.
- Placeholder scan: clean.
- Type consistency: New plan-level types are `PaperContext`, `render_claim_plan_sections`, and `render_claim_paragraph`; all later tasks use the same names.
