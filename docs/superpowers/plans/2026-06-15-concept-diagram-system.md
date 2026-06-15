# Concept Diagram System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade concept diagrams from a fixed Mermaid placeholder into route-aware, claim-aware methodology figures with reproducible Mermaid source, SVG vector output, registry metadata, and QA checks.

**Architecture:** Add a deterministic concept-diagram specification layer that converts existing workspace artifacts into diagram nodes, edges, captions, and supported claims. Extend the existing figure planning and visualization agents rather than adding a new workflow stage. Keep Mermaid as the authoring source and generate a simple SVG fallback locally so tests do not depend on external Mermaid CLI, Graphviz, browser rendering, or live services.

**Tech Stack:** Python 3.12+, Pydantic v2, existing figure models, pytest, ruff, Mermaid text, deterministic SVG.

---

## File Structure

- Create `src/mcm_agent/core/concept_diagrams.py`: canonical concept diagram spec models and builders.
- Modify `src/mcm_agent/agents/visualization.py`: plan route-aware concept diagrams and render Mermaid plus SVG.
- Modify `src/mcm_agent/agents/figure_quality.py`: require concept diagrams to have Mermaid source and vector output.
- Modify `tests/test_visualization.py`: cover methodology and claim-evidence concept diagram planning/rendering.
- Modify `tests/test_figure_quality.py`: cover concept-diagram QA failures and passes.
- Modify docs: `README.md`, `docs/WORKFLOW.md`, `docs/PROJECT_STATUS.md`, `docs/IMPLEMENTATION_PLAN.md`.

## Task 1: Concept Diagram Spec Builder

**Files:**
- Create: `src/mcm_agent/core/concept_diagrams.py`
- Modify: `tests/test_visualization.py`

- [ ] **Step 1: Add failing spec-builder test**

Add to `tests/test_visualization.py`:

```python
def test_concept_diagram_builder_uses_routes_claims_and_sources(tmp_path: Path) -> None:
    from mcm_agent.core.concept_diagrams import build_concept_diagram_specs

    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {
            "selected_routes": ["classification_model", "queuing_service_model"],
            "route_metrics": {"queue_utilization": {"route_id": "queuing_service_model", "value": 0.35}},
        },
    )
    write_json(
        workspace.root / "paper" / "claim_plan.json",
        [
            {
                "claim_id": "claim_model_route",
                "section": "paper/sections/model.tex",
                "claim_text": "The selected route is classification plus queueing.",
                "claim_type": "model_choice",
                "evidence_ids": ["metric_queue_utilization"],
                "figure_ids": [],
                "source_ids": ["source_001"],
                "priority": "critical",
            }
        ],
    )

    specs = build_concept_diagram_specs(workspace.root)

    spec_by_id = {spec.diagram_id: spec for spec in specs}
    assert "fig_method_overview" in spec_by_id
    assert "fig_claim_evidence_map" in spec_by_id
    method = spec_by_id["fig_method_overview"]
    assert any(node.label == "classification_model" for node in method.nodes)
    assert any(node.label == "queuing_service_model" for node in method.nodes)
    claim_map = spec_by_id["fig_claim_evidence_map"]
    assert any("claim_model_route" in node.label for node in claim_map.nodes)
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_visualization.py::test_concept_diagram_builder_uses_routes_claims_and_sources -q
```

Expected: FAIL with missing module `mcm_agent.core.concept_diagrams`.

- [ ] **Step 3: Implement spec builder**

Create models:

```python
class ConceptDiagramNode(BaseModel):
    node_id: str
    label: str
    kind: Literal["input", "process", "model", "evidence", "claim", "output"]

class ConceptDiagramEdge(BaseModel):
    source: str
    target: str
    label: str = ""

class ConceptDiagramSpec(BaseModel):
    diagram_id: str
    title: str
    target_section: str
    caption_intent: str
    claim_supported: str
    nodes: list[ConceptDiagramNode]
    edges: list[ConceptDiagramEdge]
    evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
```

Implement `build_concept_diagram_specs(workspace_root: Path) -> list[ConceptDiagramSpec]` that returns:

- `fig_method_overview`: problem/data -> selected route nodes -> solver/evidence -> validation/paper.
- `fig_claim_evidence_map`: critical/major claims -> evidence/source/figure support -> paper sections.

Use safe fallback nodes when artifacts are missing. Sanitize node IDs deterministically.

- [ ] **Step 4: Run spec-builder test**

Run:

```bash
pytest tests/test_visualization.py::test_concept_diagram_builder_uses_routes_claims_and_sources -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_visualization.py src/mcm_agent/core/concept_diagrams.py
git commit -m "feat: add concept diagram specs"
```

## Task 2: Figure Planning Uses Concept Diagram Specs

**Files:**
- Modify: `tests/test_visualization.py`
- Modify: `src/mcm_agent/agents/visualization.py`

- [ ] **Step 1: Add failing planning test**

Add to `tests/test_visualization.py`:

```python
def test_figure_planning_adds_method_and_claim_concept_diagrams(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {"selected_routes": ["classification_model"], "route_metrics": {}},
    )
    write_json(workspace.root / "results" / "evidence_registry.json", [])
    write_json(
        workspace.root / "paper" / "claim_plan.json",
        [
            {
                "claim_id": "claim_model_route",
                "section": "paper/sections/model.tex",
                "claim_text": "The selected model is classification.",
                "claim_type": "model_choice",
                "evidence_ids": [],
                "figure_ids": [],
                "source_ids": [],
                "priority": "critical",
                "status": "unresolved",
                "unresolved_reason": "test unresolved claim",
            }
        ],
    )
    (workspace.root / "results" / "problem1_results.csv").write_text("x,y\n1,2\n2,4\n", encoding="utf-8")

    FigurePlanningAgent().run(workspace.root)

    plan = read_json(workspace.root / "figures" / "figure_plan.json", [])
    by_id = {item["figure_id"]: item for item in plan}
    assert by_id["fig_method_overview"]["figure_type"] == "concept_diagram"
    assert by_id["fig_claim_evidence_map"]["target_section"] == "paper/sections/model.tex"
    assert "svg" in by_id["fig_method_overview"]["output_formats"]
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_visualization.py::test_figure_planning_adds_method_and_claim_concept_diagrams -q
```

Expected: FAIL because only `fig_framework` is planned.

- [ ] **Step 3: Extend figure planning**

In `FigurePlanningAgent.run`, replace the hard-coded `fig_framework` append with concept diagram specs from `build_concept_diagram_specs`. Add each spec as a `FigurePlanItem` with:

- `figure_id=spec.diagram_id`
- `figure_type="concept_diagram"`
- `generation_script=f"figures/source/{spec.diagram_id}.mmd"`
- `output_formats=["svg", "pdf"]` or `["svg"]` if PDF is not generated
- `target_section=spec.target_section`
- `caption_intent=spec.caption_intent`
- `claim_supported=spec.claim_supported`
- `evidence_ids=spec.evidence_ids`
- `source_ids=spec.source_ids`

Keep route data plots unchanged.

- [ ] **Step 4: Run planning test**

Run:

```bash
pytest tests/test_visualization.py::test_figure_planning_adds_method_and_claim_concept_diagrams -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_visualization.py src/mcm_agent/agents/visualization.py
git commit -m "feat: plan methodology concept diagrams"
```

## Task 3: Mermaid And SVG Rendering

**Files:**
- Modify: `tests/test_visualization.py`
- Modify: `src/mcm_agent/agents/visualization.py`

- [ ] **Step 1: Add failing rendering test**

Add to `tests/test_visualization.py`:

```python
def test_visualization_agent_renders_concept_diagram_mermaid_and_svg(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {"selected_routes": ["classification_model", "queuing_service_model"], "route_metrics": {}},
    )
    write_json(workspace.root / "results" / "evidence_registry.json", [])
    (workspace.root / "results" / "problem1_results.csv").write_text("x,y\n1,2\n2,4\n", encoding="utf-8")
    FigurePlanningAgent().run(workspace.root)

    VisualizationAgent().run(workspace.root)

    mermaid = workspace.root / "figures" / "source" / "fig_method_overview.mmd"
    svg = workspace.root / "figures" / "fig_method_overview.svg"
    registry = read_json(workspace.root / "figures" / "figure_registry.json", [])
    method_record = next(item for item in registry if item["figure_id"] == "fig_method_overview")
    assert mermaid.exists()
    assert svg.exists()
    assert "classification_model" in mermaid.read_text(encoding="utf-8")
    assert "<svg" in svg.read_text(encoding="utf-8")
    assert "figures/fig_method_overview.svg" in method_record["outputs"]
    assert method_record["status"] == "approved"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_visualization.py::test_visualization_agent_renders_concept_diagram_mermaid_and_svg -q
```

Expected: FAIL because concept diagrams only write fixed Mermaid and no SVG.

- [ ] **Step 3: Implement rendering**

In `VisualizationAgent._write_mermaid`:

- Rebuild or load the matching `ConceptDiagramSpec`.
- Write Mermaid source using real nodes and labeled edges.
- Write `figures/<diagram_id>.svg` using deterministic SVG rectangles/text/arrows.
- Return `FigureRecord` with `outputs` containing `.mmd` and `.svg`, `tool="mermaid+svg"`, and `status=ArtifactStatus.APPROVED`.

Do not call external CLIs in tests.

- [ ] **Step 4: Run visualization tests**

Run:

```bash
pytest tests/test_visualization.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_visualization.py src/mcm_agent/agents/visualization.py
git commit -m "feat: render concept diagrams as mermaid and svg"
```

## Task 4: Figure QA For Concept Diagrams

**Files:**
- Modify: `tests/test_figure_quality.py`
- Modify: `src/mcm_agent/agents/figure_quality.py`

- [ ] **Step 1: Add failing QA tests**

Add to `tests/test_figure_quality.py`:

```python
def test_figure_quality_fails_concept_diagram_without_vector_output(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "figures" / "figure_plan.json",
        [
            FigurePlanItem(
                figure_id="fig_method_overview",
                purpose="show method",
                figure_type="concept_diagram",
                source_data=[],
                generation_script="figures/source/fig_method_overview.mmd",
                output_formats=["svg"],
                target_section="paper/sections/model.tex",
                caption_intent="Method overview.",
                claim_supported="The method is traceable.",
            ).model_dump(mode="json")
        ],
    )
    (workspace.root / "figures" / "source" / "fig_method_overview.mmd").parent.mkdir(parents=True, exist_ok=True)
    (workspace.root / "figures" / "source" / "fig_method_overview.mmd").write_text("flowchart LR\nA-->B\n", encoding="utf-8")
    write_json(
        workspace.root / "figures" / "figure_registry.json",
        [
            {
                "figure_id": "fig_method_overview",
                "type": "concept_diagram",
                "tool": "mermaid",
                "source_file": "figures/source/fig_method_overview.mmd",
                "outputs": ["figures/source/fig_method_overview.mmd"],
                "used_in": ["paper/sections/model.tex"],
                "status": "approved",
            }
        ],
    )

    FigureQualityAgent().run(workspace.root)

    report = (workspace.root / "review" / "figure_quality_report.md").read_text(encoding="utf-8")
    assert "Concept diagram `fig_method_overview` has no SVG/PDF output." in report
```

Add:

```python
def test_figure_quality_passes_complete_concept_diagram(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "figures" / "figure_plan.json",
        [
            FigurePlanItem(
                figure_id="fig_method_overview",
                purpose="show method",
                figure_type="concept_diagram",
                source_data=[],
                generation_script="figures/source/fig_method_overview.mmd",
                output_formats=["svg"],
                target_section="paper/sections/model.tex",
                caption_intent="Method overview.",
                claim_supported="The method is traceable.",
            ).model_dump(mode="json")
        ],
    )
    (workspace.root / "figures" / "source").mkdir(parents=True, exist_ok=True)
    (workspace.root / "figures" / "source" / "fig_method_overview.mmd").write_text("flowchart LR\nA-->B\n", encoding="utf-8")
    (workspace.root / "figures" / "fig_method_overview.svg").write_text("<svg></svg>", encoding="utf-8")
    write_json(
        workspace.root / "figures" / "figure_registry.json",
        [
            {
                "figure_id": "fig_method_overview",
                "type": "concept_diagram",
                "tool": "mermaid+svg",
                "source_file": "figures/source/fig_method_overview.mmd",
                "outputs": ["figures/source/fig_method_overview.mmd", "figures/fig_method_overview.svg"],
                "used_in": ["paper/sections/model.tex"],
                "status": "approved",
            }
        ],
    )

    FigureQualityAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "figure_gate.json", {})
    assert gate["status"] == "pass"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_figure_quality.py::test_figure_quality_fails_concept_diagram_without_vector_output \
  tests/test_figure_quality.py::test_figure_quality_passes_complete_concept_diagram -q
```

Expected: first test FAIL because the QA does not check concept-diagram vector output.

- [ ] **Step 3: Implement QA checks**

In `FigureQualityAgent._registry_issues`, for `figure_type == "concept_diagram"` require:

- source file ends with `.mmd` and exists.
- at least one registered output ends with `.svg`, `.pdf`, or `.eps`.
- caption intent and target section are already covered by plan checks.

- [ ] **Step 4: Run figure QA tests**

Run:

```bash
pytest tests/test_figure_quality.py tests/test_visualization.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_figure_quality.py src/mcm_agent/agents/figure_quality.py
git commit -m "feat: qa concept diagram vector outputs"
```

## Task 5: Documentation And Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/WORKFLOW.md`
- Modify: `docs/PROJECT_STATUS.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update docs**

Document:

- Concept diagrams are generated from workspace artifacts, not freeform decoration.
- Method overview and claim-evidence map outputs.
- Mermaid source files in `figures/source/*.mmd`.
- SVG vector outputs in `figures/*.svg`.
- Figure QA checks concept diagrams for source and vector outputs.

- [ ] **Step 2: Run focused verification**

Run:

```bash
pytest tests/test_visualization.py tests/test_figure_quality.py tests/test_mvp_workflow.py::test_run_demo_workflow_creates_required_artifacts -q
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
git commit -m "docs: describe concept diagram system"
```

## Self-Review

- Spec coverage: The plan covers concept specs, route/claim-aware planning, Mermaid/SVG rendering, QA, docs, and verification.
- Placeholder scan: No unresolved TODO/TBD placeholders remain.
- Type consistency: `fig_method_overview`, `fig_claim_evidence_map`, `ConceptDiagramSpec`, `FigurePlanItem`, and `FigureRecord` names are used consistently.
