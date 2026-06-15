# Citation And Source Writing Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make paper prose cite registered sources directly and auditably, using the existing source registry, citation candidates, claim plan, and paper evidence bindings.

**Architecture:** Add a citation context layer that maps `source_id` to BibTeX keys and source metadata. Route claim-plan rendering through that context so generated sections include both trace comments and source-specific `\cite{...}` commands. Extend reference audit output so missing citations and source-to-bibliography mappings are visible to the user and final reviewer.

**Tech Stack:** Python 3.12+, Pydantic v2, existing JSON artifacts, LaTeX text generation, pytest, ruff.

---

## File Structure

- Create `src/mcm_agent/core/citations.py`: citation context models and lookup helpers.
- Modify `src/mcm_agent/agents/paper_sections.py`: render claim paragraphs with source-specific citations.
- Modify `src/mcm_agent/agents/writer.py`: pass citation context into claim-plan rendering.
- Modify `src/mcm_agent/agents/reference_manager.py`: expose source-to-bibkey audit details and avoid duplicate citation insertion.
- Modify `tests/test_reference_manager.py`: citation context and audit behavior.
- Modify `tests/test_paper_evidence_binding.py`: paper writer claim-plan citation behavior.
- Modify docs: `README.md`, `docs/WORKFLOW.md`, `docs/PROJECT_STATUS.md`, `docs/IMPLEMENTATION_PLAN.md`.

## Task 1: Citation Context Builder

**Files:**
- Create: `src/mcm_agent/core/citations.py`
- Modify: `tests/test_reference_manager.py`

- [ ] **Step 1: Add failing citation-context test**

Add to `tests/test_reference_manager.py`:

```python
def test_citation_context_maps_sources_to_bibtex_keys(tmp_path: Path) -> None:
    from mcm_agent.core.citations import build_citation_context

    workspace = create_workspace(tmp_path / "run_001")
    _write_registered_source(workspace.root)
    write_json(
        workspace.root / "data" / "citation_candidates.json",
        [
            {
                "citation_id": "cite_web_001",
                "source_id": "web_001",
                "title": "Official data",
                "url": "https://data.gov/example",
                "accessed_at": "2026-06-13T12:00:00Z",
                "bibtex_key": "official_data_2026",
            }
        ],
    )

    context = build_citation_context(workspace.root)

    assert context.bibtex_key_for_source("web_001") == "official_data_2026"
    assert context.cite_command(["web_001"]) == "\\cite{official_data_2026}"
    assert context.source_title("web_001") == "Official data"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_reference_manager.py::test_citation_context_maps_sources_to_bibtex_keys -q
```

Expected: FAIL with missing module `mcm_agent.core.citations`.

- [ ] **Step 3: Implement citation context**

Create:

```python
class CitationSource(BaseModel):
    source_id: str
    title: str = ""
    source_rank: str = ""
    bibtex_key: str = ""

class CitationContext(BaseModel):
    sources: dict[str, CitationSource] = Field(default_factory=dict)
    def bibtex_key_for_source(self, source_id: str) -> str: ...
    def source_title(self, source_id: str) -> str: ...
    def cite_command(self, source_ids: list[str]) -> str: ...
```

Rules:

- Only include source IDs in `data/source_registry.json`.
- Prefer `bibtex_key` from `data/citation_candidates.json`; fallback to source ID.
- Ignore placeholder IDs `missing`, `none`, and `unknown`.
- Deduplicate citation keys while preserving source order.

- [ ] **Step 4: Run citation-context test**

Run:

```bash
pytest tests/test_reference_manager.py::test_citation_context_maps_sources_to_bibtex_keys -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_reference_manager.py src/mcm_agent/core/citations.py
git commit -m "feat: add citation context builder"
```

## Task 2: Claim-Plan Sections Render Citations

**Files:**
- Modify: `tests/test_paper_evidence_binding.py`
- Modify: `src/mcm_agent/agents/paper_sections.py`
- Modify: `src/mcm_agent/agents/writer.py`

- [ ] **Step 1: Add failing paper-writer citation test**

Add to `tests/test_paper_evidence_binding.py`:

```python
def test_paper_writer_inserts_claim_plan_source_citations(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "paper" / "claim_plan.json",
        [
            {
                "claim_id": "claim_source_grounded_result",
                "section": "paper/sections/results.tex",
                "claim_text": "The reported data source supports the observed trend.",
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
    write_json(workspace.root / "data" / "source_registry.json", [{"source_id": "web_001", "title": "Official data"}])
    write_json(
        workspace.root / "data" / "citation_candidates.json",
        [
            {
                "citation_id": "cite_web_001",
                "source_id": "web_001",
                "title": "Official data",
                "url": "https://data.gov/example",
                "accessed_at": "2026-06-13T12:00:00Z",
                "bibtex_key": "official_data_2026",
            }
        ],
    )

    PaperWriterAgent().run(workspace.root)

    results = (workspace.root / "paper" / "sections" / "results.tex").read_text(encoding="utf-8")
    assert "\\cite{official_data_2026}" in results
    assert "% claim_id=claim_source_grounded_result" in results
    assert "source_id=web_001" in results
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_paper_evidence_binding.py::test_paper_writer_inserts_claim_plan_source_citations -q
```

Expected: FAIL because claim-plan sections only emit `source_id=...` trace comments.

- [ ] **Step 3: Extend paper section rendering**

Change `render_claim_plan_sections` signature to:

```python
def render_claim_plan_sections(
    claim_plan: list[PaperClaimPlanItem],
    context: PaperContext,
    citation_context: CitationContext | None = None,
) -> dict[str, str]:
```

Change `render_claim_paragraph` signature to accept `citation_context`. For resolved claims:

- Escape `claim.claim_text`.
- Append citation command when `claim.source_ids` map to citation keys.
- Keep trace comment unchanged.

For unresolved claims, do not add citations.

In `PaperWriterAgent._write_claim_plan_sections`, pass `build_citation_context(workspace_root)`.

- [ ] **Step 4: Run paper citation test**

Run:

```bash
pytest tests/test_paper_evidence_binding.py::test_paper_writer_inserts_claim_plan_source_citations -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_paper_evidence_binding.py src/mcm_agent/agents/paper_sections.py src/mcm_agent/agents/writer.py
git commit -m "feat: cite sources in claim-plan sections"
```

## Task 3: Reference Audit Source Mapping

**Files:**
- Modify: `tests/test_reference_manager.py`
- Modify: `src/mcm_agent/agents/reference_manager.py`

- [ ] **Step 1: Add failing reference audit test**

Add to `tests/test_reference_manager.py`:

```python
def test_reference_audit_reports_source_to_bibkey_mapping(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    _write_registered_source(workspace.root)
    write_json(
        workspace.root / "data" / "citation_candidates.json",
        [
            {
                "citation_id": "cite_web_001",
                "source_id": "web_001",
                "title": "Official data",
                "url": "https://data.gov/example",
                "accessed_at": "2026-06-13T12:00:00Z",
                "bibtex_key": "official_data_2026",
            }
        ],
    )
    section = workspace.root / "paper" / "sections" / "results.tex"
    section.parent.mkdir(parents=True, exist_ok=True)
    section.write_text("\\section{Results}\nUses source_id=web_001.\n", encoding="utf-8")

    ReferenceManager().run(workspace.root)

    report = (workspace.root / "review" / "reference_audit_report.md").read_text(encoding="utf-8")
    assert "## Source To Bibliography Mapping" in report
    assert "- `web_001` -> `official_data_2026`" in report
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_reference_manager.py::test_reference_audit_reports_source_to_bibkey_mapping -q
```

Expected: FAIL because the audit report only gives counts and missing references.

- [ ] **Step 3: Implement audit mapping**

In `ReferenceManager`:

- Build `CitationContext`.
- Use citation context for `_insert_section_citations` so `source_id=web_001` inserts `\cite{official_data_2026}` when available.
- Add `## Source To Bibliography Mapping` to audit report, one line per candidate source:
  `- `source_id` -> `bibtex_key` (title)`.
- Keep missing-reference behavior unchanged.

- [ ] **Step 4: Run reference manager tests**

Run:

```bash
pytest tests/test_reference_manager.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_reference_manager.py src/mcm_agent/agents/reference_manager.py
git commit -m "feat: audit source citation mappings"
```

## Task 4: Citation-Aware Evidence Binding

**Files:**
- Modify: `tests/test_paper_evidence_binding.py`
- Modify: `src/mcm_agent/agents/paper_evidence.py`

- [ ] **Step 1: Add failing binding test**

Add to `tests/test_paper_evidence_binding.py`:

```python
def test_paper_evidence_binding_records_latex_citations_for_sources(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    section_dir = workspace.root / "paper" / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    (section_dir / "results.tex").write_text(
        "\\section{Results}\n"
        "The result uses official data \\cite{official_data_2026}.\n"
        "% claim_id=claim_result evidence_id=ev_001 figure_id=fig_001 source_id=web_001\n",
        encoding="utf-8",
    )
    write_json(workspace.root / "results" / "evidence_registry.json", [{"evidence_id": "ev_001"}])
    write_json(workspace.root / "figures" / "figure_registry.json", [{"figure_id": "fig_001"}])
    write_json(workspace.root / "data" / "source_registry.json", [{"source_id": "web_001"}])
    write_json(
        workspace.root / "data" / "citation_candidates.json",
        [
            {
                "citation_id": "cite_web_001",
                "source_id": "web_001",
                "title": "Official data",
                "url": "https://data.gov/example",
                "accessed_at": "2026-06-13T12:00:00Z",
                "bibtex_key": "official_data_2026",
            }
        ],
    )

    PaperEvidenceBindingAgent().run(workspace.root)

    bindings = read_json(workspace.root / "review" / "paper_evidence_bindings.json", [])
    assert bindings[0]["citation_keys"] == ["official_data_2026"]
    assert bindings[0]["claim_bindings"][0]["citation_keys"] == ["official_data_2026"]
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_paper_evidence_binding.py::test_paper_evidence_binding_records_latex_citations_for_sources -q
```

Expected: FAIL because paper evidence bindings do not record citation keys.

- [ ] **Step 3: Implement citation key binding**

In `PaperEvidenceBindingAgent`:

- Load `CitationContext`.
- Add `citation_keys` at section binding level from found source IDs.
- Add `citation_keys` at claim binding level from claim source IDs.
- Keep existing pass/fail logic unchanged; citation keys are an audit enrichment, not a new blocker in this phase.

- [ ] **Step 4: Run binding tests**

Run:

```bash
pytest tests/test_paper_evidence_binding.py tests/test_reference_manager.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_paper_evidence_binding.py src/mcm_agent/agents/paper_evidence.py
git commit -m "feat: record citation keys in paper evidence bindings"
```

## Task 5: Documentation And Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/WORKFLOW.md`
- Modify: `docs/PROJECT_STATUS.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update docs**

Document:

- Citation context maps `source_id` to BibTeX keys.
- Claim-plan writing inserts citations for source-backed claims.
- Reference audit reports source-to-bibliography mapping.
- Paper evidence binding records citation keys.

- [ ] **Step 2: Run focused verification**

Run:

```bash
pytest tests/test_reference_manager.py tests/test_paper_evidence_binding.py tests/test_mvp_workflow.py::test_run_demo_workflow_creates_required_artifacts -q
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
git commit -m "docs: describe citation source writing"
```

## Self-Review

- Spec coverage: The plan covers citation lookup, source-backed prose citations, reference audit mapping, evidence-binding citation keys, docs, and verification.
- Placeholder scan: No unresolved TODO/TBD placeholders remain.
- Type consistency: `CitationContext`, `source_id`, `bibtex_key`, `citation_keys`, and `\cite{...}` are used consistently.
