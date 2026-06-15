# Claim Planning Paper Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a claim-planning layer that generates `paper/claim_plan.json` before paper writing, then makes writing, evidence binding, and final review enforce planned paper claims.

**Architecture:** The new `ClaimPlanningAgent` reads registered model, evidence, figure, source, and validation artifacts and writes a machine-readable claim plan. `PaperWriterAgent` consumes that plan when present, `PaperEvidenceBindingAgent` verifies planned-claim coverage, and `ReviewerAgent` routes omitted or unsupported critical claims to the correct repair stage.

**Tech Stack:** Python 3, Pydantic models, pytest, ruff, existing JSON workspace artifacts, existing `StageExecutor` workflow graph.

---

## Completed Baseline

The repository at `/Users/mac/Programming/MCM-ICM-Agent` already has a tested MVP.

- CLI, configuration, workspace creation, artifact registry, event log, handoff packets, stage executor, and workflow topology exist.
- Provider adapters exist for fake/OpenAI-compatible LLMs, MinerU, Tavily, Firecrawl, Brave, Exa, UShallPass, LaTeX, academic APIs, and official-data repair.
- Core agents exist for intake, extraction, problem understanding, data feasibility, reframing, discussion, methodology RAG, modeling, source search, EDA, solver, validation, visualization, writing, paper evidence binding, references, compliance, reviewer, revision, and submission packaging.
- Evidence governance already writes:
  - `data/source_registry.json`
  - `data/retrieval_log.jsonl`
  - `data/data_lineage.json`
  - `data/citation_candidates.json`
  - `results/evidence_registry.json`
  - `figures/figure_registry.json`
  - `review/paper_evidence_bindings.json`
- `PaperWriterAgent` emits fallback trace comments such as:

```tex
% claim_id=claim_results_primary evidence_id=metric_priority_score_mean figure_id=fig_priority_ranking source_id=web_001
```

- `PaperEvidenceBindingAgent` verifies section-level and claim-level trace IDs against registries.
- `ReviewerAgent` blocks submission when paper evidence bindings fail.
- Latest local sanity check before this plan:

```bash
pytest tests/test_docs.py -q
# 2 passed
```

## Current Gap

The system can verify trace comments after the draft exists, but it does not yet plan which important claims should be written before drafting. This lets a paper pass local marker validity while still omitting a critical argument that should have appeared.

The missing artifact is:

```text
paper/claim_plan.json
```

The target path is:

```text
results/model_route_summary.json
results/evidence_registry.json
figures/figure_registry.json
data/source_registry.json
reports/validation_report.md
        ↓
ClaimPlanningAgent
        ↓
paper/claim_plan.json
review/claim_plan_report.md
        ↓
PaperWriterAgent
        ↓
PaperEvidenceBindingAgent
        ↓
ReviewerAgent
```

## File Structure

- Modify `src/mcm_agent/core/models.py`
  - Add `PaperClaimPlanItem`, the data contract for one planned paper claim.
- Create `src/mcm_agent/agents/claim_planning.py`
  - Implement `ClaimPlanningAgent`, which reads existing artifacts and writes `paper/claim_plan.json` plus `review/claim_plan_report.md`.
- Modify `src/mcm_agent/workflows/mvp.py`
  - Register a `claim_planning` stage between `figure_quality_gate` and `paper_writer`.
- Modify `src/mcm_agent/core/workflow_graph.py`
  - Add the `claim_planning` node and graph edge.
- Modify `src/mcm_agent/agents/writer.py`
  - Prefer `paper/claim_plan.json` when present.
  - Keep the existing fallback for minimal or demo workspaces.
- Modify `src/mcm_agent/agents/paper_evidence.py`
  - Add planned-claim coverage checks.
- Modify `src/mcm_agent/agents/reviewer.py`
  - Block omitted critical planned claims and unresolved critical planned claims.
- Modify docs:
  - `docs/DESIGN.md`
  - `docs/WORKFLOW.md`
  - `docs/AGENT_TOPOLOGY.md`
  - `docs/PROJECT_STATUS.md`
- Modify tests:
  - Create `tests/test_claim_planning.py`
  - Modify `tests/test_workflow_topology.py`
  - Modify `tests/test_mvp_workflow.py`
  - Modify `tests/test_paper_evidence_binding.py`
  - Modify `tests/test_llm_agents.py`
  - Modify `tests/test_reviewer_revision.py`

---

### Task 1: Add Claim Planning Data Contract

**Files:**
- Modify: `src/mcm_agent/core/models.py`
- Create: `tests/test_claim_planning.py`

- [ ] **Step 1: Write failing model tests**

Add this to `tests/test_claim_planning.py`:

```python
from pathlib import Path

import pytest
from pydantic import ValidationError

from mcm_agent.core.models import PaperClaimPlanItem


def test_paper_claim_plan_item_accepts_supported_critical_claim() -> None:
    item = PaperClaimPlanItem(
        claim_id="claim_model_route",
        section="paper/sections/model.tex",
        claim_text="The selected route is a multi-criteria evaluation model.",
        claim_type="model_choice",
        evidence_ids=["metric_priority_score_mean"],
        figure_ids=[],
        source_ids=[],
        priority="critical",
    )

    assert item.status == "planned"
    assert item.unresolved_reason == ""
    assert Path(item.section).name == "model.tex"


def test_paper_claim_plan_item_rejects_unsupported_critical_claim() -> None:
    with pytest.raises(ValidationError, match="critical claim requires evidence, figure, or source"):
        PaperClaimPlanItem(
            claim_id="claim_results_primary",
            section="paper/sections/results.tex",
            claim_text="The optimized policy improves the primary metric.",
            claim_type="metric_result",
            priority="critical",
        )


def test_paper_claim_plan_item_accepts_unresolved_critical_claim_with_reason() -> None:
    item = PaperClaimPlanItem(
        claim_id="claim_unresolved_private_data",
        section="paper/sections/results.tex",
        claim_text="The private salary benchmark could not be verified.",
        claim_type="limitation",
        priority="critical",
        status="unresolved",
        unresolved_reason="Required salary data is private and no user-provided substitute exists.",
    )

    assert item.status == "unresolved"
    assert "private" in item.unresolved_reason


def test_paper_claim_plan_item_requires_paper_section_path() -> None:
    with pytest.raises(ValidationError, match="section must point to paper/sections"):
        PaperClaimPlanItem(
            claim_id="claim_bad_section",
            section="reports/results.md",
            claim_text="This claim is in the wrong location.",
            claim_type="conclusion",
            evidence_ids=["metric_001"],
            priority="major",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_claim_planning.py -q
```

Expected:

```text
ImportError: cannot import name 'PaperClaimPlanItem'
```

- [ ] **Step 3: Add `PaperClaimPlanItem`**

Add this near the existing paper/figure models in `src/mcm_agent/core/models.py`:

```python
class PaperClaimPlanItem(BaseModel):
    claim_id: str
    section: str
    claim_text: str
    claim_type: Literal[
        "model_choice",
        "metric_result",
        "sensitivity",
        "assumption",
        "limitation",
        "conclusion",
    ]
    evidence_ids: list[str] = Field(default_factory=list)
    figure_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    priority: Literal["critical", "major", "supporting"]
    status: Literal["planned", "written", "unresolved"] = "planned"
    unresolved_reason: str = ""

    @model_validator(mode="after")
    def validate_claim_plan_item(self) -> "PaperClaimPlanItem":
        if not self.claim_id.strip():
            raise ValueError("claim_id is required")
        if not self.section.startswith("paper/sections/") or not self.section.endswith(".tex"):
            raise ValueError("section must point to paper/sections/*.tex")
        has_support = bool(self.evidence_ids or self.figure_ids or self.source_ids)
        if self.priority == "critical" and self.status != "unresolved" and not has_support:
            raise ValueError("critical claim requires evidence, figure, or source")
        if self.status == "unresolved" and not self.unresolved_reason.strip():
            raise ValueError("unresolved claim requires unresolved_reason")
        return self
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest tests/test_claim_planning.py -q
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Commit**

Run:

```bash
git add src/mcm_agent/core/models.py tests/test_claim_planning.py
git commit -m "feat: add paper claim plan model"
```

---

### Task 2: Implement `ClaimPlanningAgent`

**Files:**
- Create: `src/mcm_agent/agents/claim_planning.py`
- Modify: `tests/test_claim_planning.py`

- [ ] **Step 1: Add failing agent tests**

Append this to `tests/test_claim_planning.py`:

```python
from mcm_agent.agents.claim_planning import ClaimPlanningAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json, write_json


def test_claim_planning_agent_writes_model_result_and_conclusion_claims(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {
            "selected_routes": ["multi_criteria_evaluation"],
            "route_metrics": {
                "priority_score_mean": {
                    "route_id": "multi_criteria_evaluation",
                    "value": 0.6,
                },
            },
        },
    )
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [
            {
                "evidence_id": "metric_priority_score_mean",
                "claim": "Route metric priority_score_mean equals 0.6.",
                "verified": True,
            }
        ],
    )
    write_json(
        workspace.root / "figures" / "figure_registry.json",
        [
            {
                "figure_id": "fig_priority_ranking",
                "status": "approved",
                "claim_supported": "Priority ranking supports the main result.",
                "evidence_ids": ["metric_priority_score_mean"],
                "source_ids": ["web_001"],
            }
        ],
    )
    write_json(workspace.root / "data" / "source_registry.json", [{"source_id": "web_001"}])
    (workspace.root / "reports" / "validation_report.md").write_text(
        "# Validation Report\n\nNo unresolved validation limitation remains.\n",
        encoding="utf-8",
    )

    ClaimPlanningAgent().run(workspace.root)

    plan = read_json(workspace.root / "paper" / "claim_plan.json", [])
    claim_ids = {item["claim_id"] for item in plan}
    assert "claim_model_route" in claim_ids
    assert "claim_metric_priority_score_mean" in claim_ids
    assert "claim_conclusion_traceability" in claim_ids
    assert all(item["status"] == "planned" for item in plan)
    assert (workspace.root / "review" / "claim_plan_report.md").exists()


def test_claim_planning_agent_marks_missing_evidence_as_unresolved(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {"selected_routes": ["forecasting_baseline"], "route_metrics": {}},
    )
    write_json(workspace.root / "results" / "evidence_registry.json", [])
    write_json(workspace.root / "figures" / "figure_registry.json", [])
    write_json(workspace.root / "data" / "source_registry.json", [])

    ClaimPlanningAgent().run(workspace.root)

    plan = read_json(workspace.root / "paper" / "claim_plan.json", [])
    unresolved = [item for item in plan if item["status"] == "unresolved"]
    assert unresolved
    assert any(item["priority"] == "critical" for item in unresolved)
    assert "Missing verified evidence" in unresolved[0]["unresolved_reason"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_claim_planning.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'mcm_agent.agents.claim_planning'
```

- [ ] **Step 3: Create `ClaimPlanningAgent`**

Create `src/mcm_agent/agents/claim_planning.py`:

```python
from __future__ import annotations

import re
from pathlib import Path

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.models import PaperClaimPlanItem
from mcm_agent.utils.json_io import read_json, write_json


class ClaimPlanningAgent:
    def run(self, workspace_root: Path) -> None:
        route_summary = read_json(workspace_root / "results" / "model_route_summary.json", {})
        evidence = self._verified_evidence(
            read_json(workspace_root / "results" / "evidence_registry.json", [])
        )
        figures = self._approved_figures(
            read_json(workspace_root / "figures" / "figure_registry.json", [])
        )
        sources = self._rows(read_json(workspace_root / "data" / "source_registry.json", []))
        validation_text = self._read_text(workspace_root / "reports" / "validation_report.md")

        claims: list[PaperClaimPlanItem] = []
        claims.extend(self._model_claims(route_summary, evidence, figures, sources))
        claims.extend(self._metric_claims(evidence, figures, sources))
        claims.extend(self._figure_claims(figures))
        claims.extend(self._limitation_claims(validation_text, evidence, sources))
        claims.append(self._conclusion_claim(evidence, figures, sources))

        deduped = self._dedupe_claims(claims)
        write_json(workspace_root / "paper" / "claim_plan.json", [item.model_dump() for item in deduped])
        self._write_report(workspace_root, deduped)
        Coordinator(workspace_root).emit(
            "paper.claim_plan.ready",
            payload={"artifact_ids": ["paper_claim_plan_v1"]},
            source="ClaimPlanningAgent",
        )

    def _model_claims(
        self,
        route_summary: object,
        evidence: list[dict[str, object]],
        figures: list[dict[str, object]],
        sources: list[dict[str, object]],
    ) -> list[PaperClaimPlanItem]:
        if not isinstance(route_summary, dict):
            return []
        routes = route_summary.get("selected_routes", [])
        if not isinstance(routes, list) or not routes:
            return []
        route_text = " + ".join(str(route) for route in routes)
        evidence_ids = self._ids(evidence[:1], "evidence_id")
        figure_ids = self._ids(figures[:1], "figure_id")
        source_ids = self._ids(sources[:1], "source_id")
        if evidence_ids or figure_ids or source_ids:
            return [
                PaperClaimPlanItem(
                    claim_id="claim_model_route",
                    section="paper/sections/model.tex",
                    claim_text=f"The selected model route is {route_text}.",
                    claim_type="model_choice",
                    evidence_ids=evidence_ids,
                    figure_ids=figure_ids,
                    source_ids=source_ids,
                    priority="critical",
                )
            ]
        return [
            PaperClaimPlanItem(
                claim_id="claim_model_route",
                section="paper/sections/model.tex",
                claim_text=f"The selected model route is {route_text}.",
                claim_type="model_choice",
                priority="critical",
                status="unresolved",
                unresolved_reason="Missing verified evidence, figure, or source for the selected model route.",
            )
        ]

    def _metric_claims(
        self,
        evidence: list[dict[str, object]],
        figures: list[dict[str, object]],
        sources: list[dict[str, object]],
    ) -> list[PaperClaimPlanItem]:
        claims = []
        fallback_figure_ids = self._ids(figures[:1], "figure_id")
        fallback_source_ids = self._ids(sources[:1], "source_id")
        for item in evidence:
            evidence_id = str(item.get("evidence_id", ""))
            if not evidence_id:
                continue
            claims.append(
                PaperClaimPlanItem(
                    claim_id="claim_" + self._safe_id(evidence_id),
                    section="paper/sections/results.tex",
                    claim_text=str(item.get("claim", f"Evidence {evidence_id} supports a reported result.")),
                    claim_type="metric_result",
                    evidence_ids=[evidence_id],
                    figure_ids=self._figure_ids_for_evidence(figures, evidence_id) or fallback_figure_ids,
                    source_ids=self._source_ids_for_evidence(figures, evidence_id) or fallback_source_ids,
                    priority="major",
                )
            )
        return claims

    def _figure_claims(self, figures: list[dict[str, object]]) -> list[PaperClaimPlanItem]:
        claims = []
        for item in figures:
            figure_id = str(item.get("figure_id", ""))
            claim_supported = str(item.get("claim_supported", "")).strip()
            if not figure_id or not claim_supported:
                continue
            claims.append(
                PaperClaimPlanItem(
                    claim_id="claim_" + self._safe_id(figure_id),
                    section=str(item.get("used_in", ["paper/sections/results.tex"])[0])
                    if isinstance(item.get("used_in"), list) and item.get("used_in")
                    else "paper/sections/results.tex",
                    claim_text=claim_supported,
                    claim_type="metric_result",
                    evidence_ids=self._list_values(item.get("evidence_ids")),
                    figure_ids=[figure_id],
                    source_ids=self._list_values(item.get("source_ids")),
                    priority="supporting",
                )
            )
        return claims

    def _limitation_claims(
        self,
        validation_text: str,
        evidence: list[dict[str, object]],
        sources: list[dict[str, object]],
    ) -> list[PaperClaimPlanItem]:
        lowered = validation_text.lower()
        if not any(token in lowered for token in ("unresolved", "limitation", "missing", "weak")):
            return []
        return [
            PaperClaimPlanItem(
                claim_id="claim_validation_limitation",
                section="paper/sections/sensitivity.tex",
                claim_text="The validation stage records remaining limitations that constrain interpretation.",
                claim_type="limitation",
                evidence_ids=self._ids(evidence[:1], "evidence_id"),
                source_ids=self._ids(sources[:1], "source_id"),
                priority="major",
                status="unresolved",
                unresolved_reason="Validation report contains limitation language that requires explicit discussion.",
            )
        ]

    def _conclusion_claim(
        self,
        evidence: list[dict[str, object]],
        figures: list[dict[str, object]],
        sources: list[dict[str, object]],
    ) -> PaperClaimPlanItem:
        evidence_ids = self._ids(evidence[:1], "evidence_id")
        figure_ids = self._ids(figures[:1], "figure_id")
        source_ids = self._ids(sources[:1], "source_id")
        if evidence_ids or figure_ids or source_ids:
            return PaperClaimPlanItem(
                claim_id="claim_conclusion_traceability",
                section="paper/sections/conclusion.tex",
                claim_text="The final recommendation is traceable to registered evidence, figures, and sources.",
                claim_type="conclusion",
                evidence_ids=evidence_ids,
                figure_ids=figure_ids,
                source_ids=source_ids,
                priority="critical",
            )
        return PaperClaimPlanItem(
            claim_id="claim_conclusion_traceability",
            section="paper/sections/conclusion.tex",
            claim_text="The final recommendation is traceable to registered evidence, figures, and sources.",
            claim_type="conclusion",
            priority="critical",
            status="unresolved",
            unresolved_reason="Missing verified evidence, approved figure, or registered source for final conclusion.",
        )

    def _verified_evidence(self, rows: object) -> list[dict[str, object]]:
        return [
            row
            for row in self._rows(rows)
            if row.get("evidence_id") and row.get("verified", True) is not False
        ]

    def _approved_figures(self, rows: object) -> list[dict[str, object]]:
        return [
            row
            for row in self._rows(rows)
            if row.get("figure_id") and str(row.get("status", "approved")) != "rejected"
        ]

    def _rows(self, rows: object) -> list[dict[str, object]]:
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    def _ids(self, rows: list[dict[str, object]], key: str) -> list[str]:
        return [str(row[key]) for row in rows if row.get(key)]

    def _figure_ids_for_evidence(self, figures: list[dict[str, object]], evidence_id: str) -> list[str]:
        return [
            str(figure["figure_id"])
            for figure in figures
            if evidence_id in self._list_values(figure.get("evidence_ids")) and figure.get("figure_id")
        ]

    def _source_ids_for_evidence(self, figures: list[dict[str, object]], evidence_id: str) -> list[str]:
        source_ids: list[str] = []
        for figure in figures:
            if evidence_id in self._list_values(figure.get("evidence_ids")):
                source_ids.extend(self._list_values(figure.get("source_ids")))
        return list(dict.fromkeys(source_ids))

    def _list_values(self, value: object) -> list[str]:
        return [str(item) for item in value if item] if isinstance(value, list) else []

    def _safe_id(self, value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")

    def _read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _dedupe_claims(self, claims: list[PaperClaimPlanItem]) -> list[PaperClaimPlanItem]:
        deduped: dict[str, PaperClaimPlanItem] = {}
        for claim in claims:
            deduped.setdefault(claim.claim_id, claim)
        return list(deduped.values())

    def _write_report(self, workspace_root: Path, claims: list[PaperClaimPlanItem]) -> None:
        unresolved = [claim for claim in claims if claim.status == "unresolved"]
        lines = [
            "# Claim Plan Report",
            "",
            f"Planned claims: {len(claims)}",
            f"Unresolved claims: {len(unresolved)}",
            "",
            "## Claims",
        ]
        for claim in claims:
            lines.append(
                f"- `{claim.claim_id}` ({claim.priority}, {claim.status}) -> `{claim.section}`"
            )
            lines.append(f"  - {claim.claim_text}")
            if claim.unresolved_reason:
                lines.append(f"  - unresolved_reason: {claim.unresolved_reason}")
        (workspace_root / "review" / "claim_plan_report.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest tests/test_claim_planning.py -q
```

Expected:

```text
6 passed
```

- [ ] **Step 5: Commit**

Run:

```bash
git add src/mcm_agent/agents/claim_planning.py tests/test_claim_planning.py
git commit -m "feat: add claim planning agent"
```

---

### Task 3: Wire Claim Planning Into Workflow

**Files:**
- Modify: `src/mcm_agent/core/workflow_graph.py`
- Modify: `src/mcm_agent/workflows/mvp.py`
- Modify: `tests/test_workflow_topology.py`
- Modify: `tests/test_mvp_workflow.py`

- [ ] **Step 1: Add failing topology test**

Modify `test_default_workflow_contains_review_feedback_loops` in `tests/test_workflow_topology.py`:

```python
def test_default_workflow_contains_review_feedback_loops() -> None:
    graph = build_default_workflow_graph()

    assert graph.next_nodes("final_gatekeeper") == ["submission_packager"]
    assert graph.failure_route("final_gatekeeper", "missing_requirement") == "problem_understanding"
    assert graph.failure_route("final_gatekeeper", "weak_model") == "modeling_council"
    assert graph.failure_route("final_gatekeeper", "bad_figures") == "figure_planning"
    assert graph.failure_route("figure_quality_gate", "visual_or_vector_issue") == "figure_planning"
    assert graph.has_edge("figure_quality_gate", "claim_planning")
    assert graph.has_edge("claim_planning", "paper_writer")
    assert not graph.has_edge("figure_quality_gate", "paper_writer")
    assert graph.has_edge("paper_writer", "paper_evidence_binding")
    assert graph.has_edge("paper_evidence_binding", "typesetting")
```

- [ ] **Step 2: Add failing MVP artifact assertions**

In `tests/test_mvp_workflow.py`, add these required artifacts to `required`:

```python
"paper/claim_plan.json",
"review/claim_plan_report.md",
```

Also assert stage order:

```python
assert stage_ids.index("figure_quality_gate") < stage_ids.index("claim_planning")
assert stage_ids.index("claim_planning") < stage_ids.index("paper_writer")
```

- [ ] **Step 3: Run workflow tests to verify failure**

Run:

```bash
pytest tests/test_workflow_topology.py tests/test_mvp_workflow.py -q
```

Expected:

```text
FAILED tests/test_workflow_topology.py
FAILED tests/test_mvp_workflow.py
```

- [ ] **Step 4: Add workflow node and edges**

In `src/mcm_agent/core/workflow_graph.py`, add this node before `paper_writer`:

```python
"claim_planning": AgentNode(
    node_id="claim_planning",
    label="Claim Planning Agent",
    responsibility="Plan paper claims, target sections, priorities, and supporting artifacts before drafting.",
    input_artifacts=[
        "results/model_route_summary.json",
        "results/evidence_registry.json",
        "figures/figure_registry.json",
        "data/source_registry.json",
        "reports/validation_report.md",
    ],
    output_artifacts=["paper/claim_plan.json", "review/claim_plan_report.md"],
    pass_criteria=[
        "Every critical paper claim is supported or explicitly unresolved.",
        "The writer has an authoritative claim list before drafting.",
    ],
),
```

Replace this edge:

```python
WorkflowEdge("figure_quality_gate", "paper_writer"),
```

with:

```python
WorkflowEdge("figure_quality_gate", "claim_planning"),
WorkflowEdge("claim_planning", "paper_writer"),
```

- [ ] **Step 5: Register MVP handler**

In `src/mcm_agent/workflows/mvp.py`, add the import:

```python
from mcm_agent.agents.claim_planning import ClaimPlanningAgent
```

Add the handler before `paper_writer`:

```python
def claim_planning(workspace_root: Path) -> list[str]:
    ClaimPlanningAgent().run(workspace_root)
    return ["paper/claim_plan.json", "review/claim_plan_report.md"]
```

Add it to the `handlers` dictionary:

```python
"claim_planning": claim_planning,
```

- [ ] **Step 6: Run workflow tests**

Run:

```bash
pytest tests/test_workflow_topology.py tests/test_mvp_workflow.py -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 7: Commit**

Run:

```bash
git add src/mcm_agent/core/workflow_graph.py src/mcm_agent/workflows/mvp.py tests/test_workflow_topology.py tests/test_mvp_workflow.py
git commit -m "feat: wire claim planning into workflow"
```

---

### Task 4: Make `PaperWriterAgent` Claim-Plan Driven

**Files:**
- Modify: `src/mcm_agent/agents/writer.py`
- Modify: `tests/test_llm_agents.py`
- Modify: `tests/test_paper_evidence_binding.py`

- [ ] **Step 1: Add failing writer test**

Append this to `tests/test_paper_evidence_binding.py`:

```python
def test_paper_writer_uses_claim_plan_when_available(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "paper" / "claim_plan.json",
        [
            {
                "claim_id": "claim_planned_result",
                "section": "paper/sections/results.tex",
                "claim_text": "The planned result is supported by the registered metric.",
                "claim_type": "metric_result",
                "evidence_ids": ["ev_001"],
                "figure_ids": ["fig_001"],
                "source_ids": ["web_001"],
                "priority": "critical",
                "status": "planned",
                "unresolved_reason": "",
            }
        ],
    )
    write_json(workspace.root / "results" / "evidence_registry.json", [{"evidence_id": "ev_001"}])
    write_json(workspace.root / "figures" / "figure_registry.json", [{"figure_id": "fig_001"}])
    write_json(workspace.root / "data" / "source_registry.json", [{"source_id": "web_001"}])

    PaperWriterAgent().run(workspace.root)

    results = (workspace.root / "paper" / "sections" / "results.tex").read_text(encoding="utf-8")
    assert "The planned result is supported by the registered metric." in results
    assert "% claim_id=claim_planned_result evidence_id=ev_001 figure_id=fig_001 source_id=web_001" in results
```

Append this unresolved test:

```python
def test_paper_writer_records_unresolved_planned_claims(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "paper" / "claim_plan.json",
        [
            {
                "claim_id": "claim_unresolved_result",
                "section": "paper/sections/results.tex",
                "claim_text": "The missing metric cannot be reported.",
                "claim_type": "metric_result",
                "evidence_ids": [],
                "figure_ids": [],
                "source_ids": [],
                "priority": "critical",
                "status": "unresolved",
                "unresolved_reason": "Solver evidence is missing.",
            }
        ],
    )

    PaperWriterAgent().run(workspace.root)

    unresolved = (workspace.root / "unresolved_issues.md").read_text(encoding="utf-8")
    results = (workspace.root / "paper" / "sections" / "results.tex").read_text(encoding="utf-8")
    assert "claim_unresolved_result" in unresolved
    assert "Solver evidence is missing." in unresolved
    assert "% claim_id=claim_unresolved_result evidence_id=missing figure_id=missing source_id=missing" in results
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_paper_evidence_binding.py::test_paper_writer_uses_claim_plan_when_available tests/test_paper_evidence_binding.py::test_paper_writer_records_unresolved_planned_claims -q
```

Expected:

```text
FAILED
```

- [ ] **Step 3: Add claim-plan path in writer**

In `src/mcm_agent/agents/writer.py`, import the model:

```python
from mcm_agent.core.models import PaperClaimPlanItem
```

At the start of `run`, after creating `section_dir`, add:

```python
claim_plan = self._read_claim_plan(workspace_root)
if claim_plan:
    self._write_claim_plan_sections(workspace_root, section_dir, claim_plan)
    self._write_main_files(paper_dir)
    Coordinator(workspace_root).emit(
        "paper.draft.ready",
        payload={"artifact_ids": ["paper_draft_v1"]},
        source="PaperWriterAgent",
    )
    return
```

Extract the existing `references.bib` and `main.tex` writes into:

```python
def _write_main_files(self, paper_dir: Path) -> None:
    (paper_dir / "references.bib").write_text(
        "@misc{registered_sources,\n  title={Registered data sources},\n  year={2026}\n}\n",
        encoding="utf-8",
    )
    (paper_dir / "main.tex").write_text(
        "\n".join(
            [
                "\\documentclass[12pt]{article}",
                "\\usepackage{graphicx}",
                "\\usepackage{amsmath}",
                "\\usepackage{booktabs}",
                "\\begin{document}",
                "\\input{sections/abstract}",
                "\\input{sections/introduction}",
                "\\input{sections/assumptions}",
                "\\input{sections/model}",
                "\\input{sections/results}",
                "\\input{sections/sensitivity}",
                "\\input{sections/conclusion}",
                "\\bibliographystyle{plain}",
                "\\bibliography{references}",
                "\\end{document}",
                "",
            ]
        ),
        encoding="utf-8",
    )
```

Add helpers:

```python
def _read_claim_plan(self, workspace_root: Path) -> list[PaperClaimPlanItem]:
    rows = read_json(workspace_root / "paper" / "claim_plan.json", [])
    if not isinstance(rows, list):
        return []
    return [PaperClaimPlanItem.model_validate(row) for row in rows if isinstance(row, dict)]


def _write_claim_plan_sections(
    self,
    workspace_root: Path,
    section_dir: Path,
    claim_plan: list[PaperClaimPlanItem],
) -> None:
    section_content = dict(SECTION_CONTENT)
    for claim in claim_plan:
        section_name = Path(claim.section).name
        if section_name not in section_content:
            section_content[section_name] = "\\section{Planned Claims}\n"
        section_content[section_name] = (
            section_content[section_name].rstrip()
            + "\n"
            + self._claim_plan_paragraph(workspace_root, claim)
            + "\n"
        )
    for filename, content in section_content.items():
        (section_dir / filename).write_text(content, encoding="utf-8")


def _claim_plan_paragraph(self, workspace_root: Path, claim: PaperClaimPlanItem) -> str:
    evidence_id = claim.evidence_ids[0] if claim.evidence_ids else "missing"
    figure_id = claim.figure_ids[0] if claim.figure_ids else "missing"
    source_id = claim.source_ids[0] if claim.source_ids else "missing"
    trace = self._claim_trace_comment(claim.claim_id, evidence_id, figure_id, source_id)
    if claim.status == "unresolved":
        self._append_unresolved_claim(workspace_root, claim)
        return "\n".join(
            [
                "The planned claim "
                + self._texttt(claim.claim_id)
                + " remains unresolved: "
                + self._latex_escape(claim.unresolved_reason),
                trace,
            ]
        )
    return "\n".join([self._latex_escape(claim.claim_text), trace])


def _append_unresolved_claim(self, workspace_root: Path, claim: PaperClaimPlanItem) -> None:
    path = workspace_root / "unresolved_issues.md"
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(
        current
        + "[[UNRESOLVED:\n"
        + f'reason = "{claim.unresolved_reason}"\n'
        + f'needed_input = "Resolve planned claim {claim.claim_id}"\n'
        + f'affected_section = "{claim.section}"\n'
        + "]]\n",
        encoding="utf-8",
    )
```

Then replace the duplicated main-file writing in the fallback branch with:

```python
self._write_main_files(paper_dir)
```

- [ ] **Step 4: Run writer tests**

Run:

```bash
pytest tests/test_paper_evidence_binding.py tests/test_llm_agents.py -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 5: Commit**

Run:

```bash
git add src/mcm_agent/agents/writer.py tests/test_paper_evidence_binding.py tests/test_llm_agents.py
git commit -m "feat: drive paper writer from claim plan"
```

---

### Task 5: Extend Paper Evidence Binding For Planned Coverage

**Files:**
- Modify: `src/mcm_agent/agents/paper_evidence.py`
- Modify: `tests/test_paper_evidence_binding.py`

- [ ] **Step 1: Add failing planned-coverage tests**

Append this to `tests/test_paper_evidence_binding.py`:

```python
def test_paper_evidence_binding_fails_missing_planned_critical_claim(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    section_dir = workspace.root / "paper" / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    (section_dir / "results.tex").write_text("\\section{Results}\nNo planned claim marker.\n", encoding="utf-8")
    write_json(
        workspace.root / "paper" / "claim_plan.json",
        [
            {
                "claim_id": "claim_planned_result",
                "section": "paper/sections/results.tex",
                "claim_text": "The planned result must be written.",
                "claim_type": "metric_result",
                "evidence_ids": ["ev_001"],
                "figure_ids": [],
                "source_ids": [],
                "priority": "critical",
                "status": "planned",
                "unresolved_reason": "",
            }
        ],
    )
    write_json(workspace.root / "results" / "evidence_registry.json", [{"evidence_id": "ev_001"}])
    write_json(workspace.root / "figures" / "figure_registry.json", [])
    write_json(workspace.root / "data" / "source_registry.json", [])

    PaperEvidenceBindingAgent().run(workspace.root)

    bindings = read_json(workspace.root / "review" / "paper_evidence_bindings.json", [])
    report = (workspace.root / "review" / "paper_evidence_report.md").read_text(encoding="utf-8")
    assert bindings[0]["status"] == "fail"
    assert "Omitted planned claims: claim_planned_result" in report


def test_paper_evidence_binding_rejects_bindings_outside_plan(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    section_dir = workspace.root / "paper" / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    (section_dir / "results.tex").write_text(
        "\\section{Results}\n"
        "% claim_id=claim_planned_result evidence_id=ev_wrong\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "paper" / "claim_plan.json",
        [
            {
                "claim_id": "claim_planned_result",
                "section": "paper/sections/results.tex",
                "claim_text": "The planned result must use ev_001.",
                "claim_type": "metric_result",
                "evidence_ids": ["ev_001"],
                "figure_ids": [],
                "source_ids": [],
                "priority": "major",
                "status": "planned",
                "unresolved_reason": "",
            }
        ],
    )
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [{"evidence_id": "ev_001"}, {"evidence_id": "ev_wrong"}],
    )
    write_json(workspace.root / "figures" / "figure_registry.json", [])
    write_json(workspace.root / "data" / "source_registry.json", [])

    PaperEvidenceBindingAgent().run(workspace.root)

    bindings = read_json(workspace.root / "review" / "paper_evidence_bindings.json", [])
    assert bindings[0]["status"] == "fail"
    assert any(
        "Evidence ids outside claim plan: ev_wrong" in item
        for item in bindings[0]["missing_bindings"]
    )
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_paper_evidence_binding.py::test_paper_evidence_binding_fails_missing_planned_critical_claim tests/test_paper_evidence_binding.py::test_paper_evidence_binding_rejects_bindings_outside_plan -q
```

Expected:

```text
FAILED
```

- [ ] **Step 3: Implement planned coverage**

In `src/mcm_agent/agents/paper_evidence.py`, import:

```python
from mcm_agent.core.models import PaperClaimPlanItem
```

In `run`, read the plan before scanning sections:

```python
claim_plan = self._read_claim_plan(workspace_root)
```

Pass `claim_plan` to `_binding_for_section` and `_write_report`.

Add helpers:

```python
def _read_claim_plan(self, workspace_root: Path) -> dict[str, PaperClaimPlanItem]:
    rows = read_json(workspace_root / "paper" / "claim_plan.json", [])
    if not isinstance(rows, list):
        return {}
    return {
        item.claim_id: item
        for item in (PaperClaimPlanItem.model_validate(row) for row in rows if isinstance(row, dict))
    }


def _planned_claims_for_section(
    self,
    claim_plan: dict[str, PaperClaimPlanItem],
    section: Path,
    workspace_root: Path,
) -> list[PaperClaimPlanItem]:
    section_path = str(section.relative_to(workspace_root))
    return [
        item
        for item in claim_plan.values()
        if item.section == section_path and item.status != "unresolved" and item.priority in {"critical", "major"}
    ]


def _planned_coverage_missing(
    self,
    claim_plan: dict[str, PaperClaimPlanItem],
    section: Path,
    workspace_root: Path,
    claim_bindings: list[dict[str, object]],
) -> list[str]:
    written_claim_ids = {
        str(binding["claim_id"])
        for binding in claim_bindings
        if isinstance(binding, dict) and binding.get("claim_id")
    }
    planned = self._planned_claims_for_section(claim_plan, section, workspace_root)
    omitted = [item.claim_id for item in planned if item.claim_id not in written_claim_ids]
    return ["Omitted planned claims: " + ", ".join(omitted)] if omitted else []


def _claim_plan_subset_missing(
    self,
    claim_plan: dict[str, PaperClaimPlanItem],
    claim_binding: dict[str, object],
) -> list[str]:
    claim_id = str(claim_binding.get("claim_id", ""))
    planned = claim_plan.get(claim_id)
    if planned is None or planned.status == "unresolved":
        return []
    missing = []
    for key, planned_values, label in (
        ("evidence_ids", planned.evidence_ids, "Evidence"),
        ("figure_ids", planned.figure_ids, "Figure"),
        ("source_ids", planned.source_ids, "Source"),
    ):
        found_values = [str(value) for value in claim_binding.get(key, [])]
        outside = sorted(set(found_values) - set(planned_values))
        if outside:
            missing.append(f"{label} ids outside claim plan: " + ", ".join(outside))
    return missing
```

In `_binding_for_section`, after `claim_bindings` is created:

```python
missing.extend(self._planned_coverage_missing(claim_plan, section, workspace_root, claim_bindings))
for claim_binding in claim_bindings:
    missing.extend(self._claim_plan_subset_missing(claim_plan, claim_binding))
```

- [ ] **Step 4: Run evidence tests**

Run:

```bash
pytest tests/test_paper_evidence_binding.py -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 5: Commit**

Run:

```bash
git add src/mcm_agent/agents/paper_evidence.py tests/test_paper_evidence_binding.py
git commit -m "feat: enforce planned paper claim coverage"
```

---

### Task 6: Extend Reviewer For Claim Plan Quality

**Files:**
- Modify: `src/mcm_agent/agents/reviewer.py`
- Modify: `tests/test_reviewer_revision.py`

- [ ] **Step 1: Add failing reviewer tests**

Append this to `tests/test_reviewer_revision.py`:

```python
from mcm_agent.utils.json_io import read_json


def test_reviewer_routes_omitted_planned_claims_to_writer(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "review" / "paper_evidence_bindings.json",
        [
            {
                "section": "paper/sections/results.tex",
                "status": "fail",
                "missing_bindings": ["Omitted planned claims: claim_planned_result"],
                "claim_bindings": [],
            }
        ],
    )

    ReviewerAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "final_gate.json", {})
    assert gate["status"] == "fail"
    assert gate["failure_reason"] == "bad_writing"
    assert gate["repair_stage"] == "paper_writer"


def test_reviewer_routes_unresolved_critical_claims_to_solver(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "paper" / "claim_plan.json",
        [
            {
                "claim_id": "claim_unresolved_metric",
                "section": "paper/sections/results.tex",
                "claim_text": "The missing metric is required for the result.",
                "claim_type": "metric_result",
                "evidence_ids": [],
                "figure_ids": [],
                "source_ids": [],
                "priority": "critical",
                "status": "unresolved",
                "unresolved_reason": "Solver evidence is missing.",
            }
        ],
    )
    write_json(workspace.root / "review" / "paper_evidence_bindings.json", [])

    ReviewerAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "final_gate.json", {})
    assert gate["status"] == "fail"
    assert gate["failure_reason"] == "bad_results"
    assert gate["repair_stage"] == "solver_coder"
    assert any("Critical planned claims remain unresolved" in item for item in gate["blocking_findings"])
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_reviewer_revision.py::test_reviewer_routes_omitted_planned_claims_to_writer tests/test_reviewer_revision.py::test_reviewer_routes_unresolved_critical_claims_to_solver -q
```

Expected:

```text
FAILED
```

- [ ] **Step 3: Add reviewer helpers**

In `src/mcm_agent/agents/reviewer.py`, import:

```python
from mcm_agent.core.models import PaperClaimPlanItem
```

Add helpers:

```python
def _unresolved_critical_claims(self, workspace_root: Path) -> list[str]:
    rows = read_json(workspace_root / "paper" / "claim_plan.json", [])
    if not isinstance(rows, list):
        return []
    unresolved = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = PaperClaimPlanItem.model_validate(row)
        if item.priority == "critical" and item.status == "unresolved":
            unresolved.append(item.claim_id)
    return unresolved


def _paper_binding_failure_reason(self, workspace_root: Path) -> tuple[list[str], bool]:
    bindings = read_json(workspace_root / "review" / "paper_evidence_bindings.json", [])
    if not isinstance(bindings, list):
        return [], False
    missing_sections = []
    has_omitted_plan = False
    for binding in bindings:
        if not isinstance(binding, dict) or binding.get("status") != "fail":
            continue
        section = str(binding.get("section", "unknown_section"))
        missing_sections.append(section)
        missing = binding.get("missing_bindings", [])
        if isinstance(missing, list) and any("Omitted planned claims:" in str(item) for item in missing):
            has_omitted_plan = True
    return missing_sections, has_omitted_plan
```

In `run`, replace:

```python
missing_paper_bindings = self._missing_paper_bindings(workspace_root)
```

with:

```python
missing_paper_bindings, has_omitted_planned_claim = self._paper_binding_failure_reason(workspace_root)
unresolved_critical_claims = self._unresolved_critical_claims(workspace_root)
if unresolved_critical_claims:
    blocking.append(
        "Critical planned claims remain unresolved: "
        + ", ".join(f"`{claim_id}`" for claim_id in unresolved_critical_claims)
        + "."
    )
```

Adjust failure routing before the generic `blocking` branch:

```python
elif unresolved_critical_claims:
    failure_reason = "bad_results"
    repair_stage = "solver_coder"
elif has_omitted_planned_claim:
    failure_reason = "bad_writing"
    repair_stage = "paper_writer"
elif missing_paper_bindings:
    failure_reason = "bad_writing"
    repair_stage = "paper_writer"
```

Keep `_missing_paper_bindings` only if other callers still use it; otherwise remove it after selected tests pass.

- [ ] **Step 4: Run reviewer tests**

Run:

```bash
pytest tests/test_reviewer_revision.py tests/test_gate_decisions.py tests/test_reference_manager.py -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 5: Commit**

Run:

```bash
git add src/mcm_agent/agents/reviewer.py tests/test_reviewer_revision.py
git commit -m "feat: review planned paper claims"
```

---

### Task 7: Update Docs And Demo Status

**Files:**
- Modify: `docs/DESIGN.md`
- Modify: `docs/WORKFLOW.md`
- Modify: `docs/AGENT_TOPOLOGY.md`
- Modify: `docs/PROJECT_STATUS.md`

- [ ] **Step 1: Update workflow docs**

In `docs/WORKFLOW.md`, add `paper/claim_plan.json` and `review/claim_plan_report.md` to the workspace table under `paper/` and `review/`.

Update the pass path:

```text
validation_gate
figure_planning
visualization
figure_quality_gate
claim_planning
paper_writer
paper_evidence_binding
typesetting
pre_submission_review
final_gatekeeper
submission_packager
```

Add a paragraph:

```markdown
`claim_planning` runs after figure QA and before paper writing. It writes
`paper/claim_plan.json`, which lists each planned paper claim, target section, claim type,
priority, support IDs, and unresolved reason when support is missing. `paper_writer`
uses this file as the authoritative list of important claims when it exists.
```

- [ ] **Step 2: Update design docs**

In `docs/DESIGN.md`, insert `Claim Planning Agent` between Visualization and Paper Writer in the overall workflow diagram:

```text
Visualization Agent 生成论文级图表
        ↓
Claim Planning Agent 规划关键论断、目标章节和证据绑定
        ↓
Paper Writer Agent 写论文正文
```

Add this design rule:

```markdown
Writer Agent must not silently invent or omit critical claims. A critical claim must
either bind to registered evidence, figures, or sources in `paper/claim_plan.json`, or be
marked `status="unresolved"` with a concrete unresolved reason.
```

- [ ] **Step 3: Update topology diagram**

In `docs/AGENT_TOPOLOGY.md`, replace the late-paper chain with:

```mermaid
FQ -->|ok| CP["Claim Plan"]
CP --> PW["Write Paper"]
PW --> PEB["Bind Evidence"]
PEB --> TS["Typeset"]
```

Add table rows:

```markdown
| Claim Plan | Claim Planning Agent | Plans every important paper claim, target section, priority, and evidence/source/figure support before drafting. |
| Bind Evidence | Paper Evidence Binding Agent | Checks written sections against registries and planned claim coverage. |
```

- [ ] **Step 4: Update project status**

In `docs/PROJECT_STATUS.md`, move `ClaimPlanningAgent` from "Not Yet Built" to "Implemented" only after Tasks 1-6 pass.

Add this to the evidence governance list:

```markdown
- Planned paper claims enter `paper/claim_plan.json`.
```

- [ ] **Step 5: Run docs tests**

Run:

```bash
pytest tests/test_docs.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit**

Run:

```bash
git add docs/DESIGN.md docs/WORKFLOW.md docs/AGENT_TOPOLOGY.md docs/PROJECT_STATUS.md
git commit -m "docs: describe claim planning workflow"
```

---

### Task 8: Full Verification And Push

**Files:**
- Verify all touched code, tests, and docs.

- [ ] **Step 1: Run complete test suite**

Run:

```bash
pytest -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Run ruff**

Run:

```bash
ruff check src tests scripts
```

Expected:

```text
All checks passed!
```

- [ ] **Step 3: Check git status**

Run:

```bash
git status --short
```

Expected:

```text
no unstaged or uncommitted files except intentionally generated local artifacts
```

- [ ] **Step 4: Push**

Run:

```bash
git push
```

Expected:

```text
branch main pushed successfully
```

## Self-Review

- Spec coverage: Tasks 1-2 create the claim data contract and agent. Task 3 wires the stage. Task 4 makes writing plan-driven. Task 5 checks planned coverage. Task 6 makes review block unresolved or omitted critical claims. Task 7 updates docs. Task 8 verifies everything.
- Placeholder scan: The plan uses concrete file paths, code snippets, commands, expected failure modes, and commit messages.
- Type consistency: The canonical model is `PaperClaimPlanItem`; canonical artifact is `paper/claim_plan.json`; canonical stage is `claim_planning`; canonical event is `paper.claim_plan.ready`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-15-claim-planning-paper-generation.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints for review.
