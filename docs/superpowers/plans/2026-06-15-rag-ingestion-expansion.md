# RAG Ingestion Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the user-filled `knowledge_base/` a provenance-aware methodology RAG library that can ingest Markdown, text, and MinerU-parsed PDFs without treating local notes as external factual data.

**Architecture:** Keep `MethodologyRAGAgent` as the public workflow boundary. Extend `MethodologyStore` from plain FTS rows into chunked records with source type, relative path, usage restriction, and parse metadata. Wire the existing MinerU provider from `ProviderBundle` into the RAG stage so `.pdf` files become searchable when a parser is configured and remain clearly pending when no parser is available.

**Tech Stack:** Python 3.12+, SQLite FTS5, Pydantic v2, existing MinerU provider protocol, pytest, ruff.

---

## File Structure

- Modify `src/mcm_agent/agents/rag.py`: define provenance metadata, source-type inference, chunking, MinerU-backed PDF ingestion, and richer retrieval notes.
- Modify `src/mcm_agent/workflows/mvp.py`: pass `provider_bundle.mineru` into `MethodologyRAGAgent.run`.
- Modify `tests/test_rag.py`: add red-green tests for provenance, usage restrictions, PDF parsing, PDF fallback, and chunks.
- Modify `tests/test_mvp_workflow.py`: prove the workflow passes the configured MinerU provider to knowledge-base PDF ingestion.
- Modify `docs/WORKFLOW.md`, `docs/PROJECT_STATUS.md`, `docs/IMPLEMENTATION_PLAN.md`, and `README.md`: document filled-knowledge-base behavior and mark E complete after implementation.

## Task 1: Provenance Metadata Contract

**Files:**
- Modify: `tests/test_rag.py`
- Modify: `src/mcm_agent/agents/rag.py`

- [ ] **Step 1: Add failing provenance test**

Add this test to `tests/test_rag.py`:

```python
def test_methodology_hits_include_provenance_and_usage_restrictions(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    knowledge_base = tmp_path / "knowledge_base"
    (knowledge_base / "contest_rules").mkdir(parents=True)
    (knowledge_base / "contest_rules" / "rules.txt").write_text(
        "Figure design must keep every chart tied to an explicit paper claim.",
        encoding="utf-8",
    )

    MethodologyRAGAgent().run(
        workspace.root,
        supervisor_skills_dir=None,
        knowledge_base_dir=knowledge_base,
    )

    hits = read_json(workspace.root / "rag" / "methodology_hits.json", [])
    rule_hit = next(hit for hit in hits if hit["title"] == "rules.txt")
    assert rule_hit["source_type"] == "contest_rule"
    assert rule_hit["relative_path"] == "contest_rules/rules.txt"
    assert rule_hit["chunk_id"] == "contest_rules/rules.txt#chunk-001"
    assert rule_hit["usage"] == (
        "Use as contest or formatting guidance only; do not cite as external factual data."
    )
```

- [ ] **Step 2: Run the single test to verify it fails**

Run: `pytest tests/test_rag.py::test_methodology_hits_include_provenance_and_usage_restrictions -q`

Expected: FAIL because `MethodologyHit` does not expose `source_type`, `relative_path`, `chunk_id`, or `usage`.

- [ ] **Step 3: Implement the metadata model and FTS schema**

In `src/mcm_agent/agents/rag.py`, extend `MethodologyHit` with these fields:

```python
source_type: str = "method_note"
relative_path: str = ""
usage: str = "Use as methodology guidance only; do not cite as external factual data."
chunk_id: str = ""
chunk_index: int = 1
page_hint: str = ""
```

Change `MethodologyStore.initialize()` so the FTS5 table has columns:

```sql
source, title, content, source_type, relative_path, usage, chunk_id, chunk_index, page_hint
```

If an existing table has the legacy columns `source`, `title`, and `content` only, drop and recreate it. This is acceptable because `rag/methodology.db` is a generated workspace artifact.

Update `MethodologyStore.add_document(...)` to accept the new metadata fields with defaults, and update `search(...)` to return the metadata in each `MethodologyHit`.

- [ ] **Step 4: Implement source-type and usage helpers**

Add helpers in `src/mcm_agent/agents/rag.py`:

```python
def infer_source_type(relative_path: str) -> str:
    lowered = relative_path.lower()
    if "rule" in lowered or "contest" in lowered or "format" in lowered:
        return "contest_rule"
    if "paper" in lowered or "solution" in lowered or "winner" in lowered:
        return "paper_example"
    if "checklist" in lowered or "review" in lowered:
        return "checklist"
    return "method_note"


def usage_restriction(source_type: str) -> str:
    restrictions = {
        "contest_rule": "Use as contest or formatting guidance only; do not cite as external factual data.",
        "paper_example": "Use as writing and modeling pattern guidance only; do not copy claims or cite as external factual data.",
        "checklist": "Use as internal review guidance only; do not cite as external factual data.",
        "method_note": "Use as methodology guidance only; do not cite as external factual data.",
        "supervisor_skill": "Use as internal agent methodology guidance only; do not cite as external factual data.",
    }
    return restrictions.get(source_type, restrictions["method_note"])
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_rag.py::test_methodology_hits_include_provenance_and_usage_restrictions -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_rag.py src/mcm_agent/agents/rag.py
git commit -m "feat: add provenance metadata to rag hits"
```

## Task 2: Chunked Markdown And Text Ingestion

**Files:**
- Modify: `tests/test_rag.py`
- Modify: `src/mcm_agent/agents/rag.py`

- [ ] **Step 1: Add failing chunking test**

Add this test:

```python
def test_methodology_rag_agent_chunks_large_knowledge_base_documents(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    knowledge_base = tmp_path / "knowledge_base"
    knowledge_base.mkdir()
    first = "Figure design should explain the model claim. " * 80
    second = "Model formulation should define variables and constraints. " * 80
    (knowledge_base / "method_note.md").write_text(first + "\n\n" + second, encoding="utf-8")

    MethodologyRAGAgent().run(
        workspace.root,
        supervisor_skills_dir=None,
        knowledge_base_dir=knowledge_base,
    )

    hits = read_json(workspace.root / "rag" / "methodology_hits.json", [])
    chunk_ids = {hit["chunk_id"] for hit in hits if hit["title"] == "method_note.md"}
    assert "method_note.md#chunk-001" in chunk_ids
    assert "method_note.md#chunk-002" in chunk_ids
```

- [ ] **Step 2: Run the single test to verify it fails**

Run: `pytest tests/test_rag.py::test_methodology_rag_agent_chunks_large_knowledge_base_documents -q`

Expected: FAIL because ingestion currently stores each file as one row.

- [ ] **Step 3: Add deterministic chunking**

Add `chunk_text(content: str, *, max_chars: int = 2400) -> list[str]` that groups paragraph blocks into stable chunks. Use paragraph boundaries where possible; if one paragraph is longer than `max_chars`, split it into fixed-size slices. Store chunk IDs as `<relative_path>#chunk-001`, `<relative_path>#chunk-002`, and so on.

Update `.md` and `.txt` ingestion to add one row per chunk while preserving existing note wording:

```text
Ingested user knowledge-base document: methods/network_flow.md
```

- [ ] **Step 4: Run the chunking test**

Run: `pytest tests/test_rag.py::test_methodology_rag_agent_chunks_large_knowledge_base_documents -q`

Expected: PASS.

- [ ] **Step 5: Run existing RAG tests**

Run: `pytest tests/test_rag.py -q`

Expected: all RAG tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_rag.py src/mcm_agent/agents/rag.py
git commit -m "feat: chunk knowledge base rag documents"
```

## Task 3: MinerU-Backed PDF Knowledge-Base Ingestion

**Files:**
- Modify: `tests/test_rag.py`
- Modify: `src/mcm_agent/agents/rag.py`

- [ ] **Step 1: Add fake PDF parser test**

Add this fake and test:

```python
class KnowledgeBaseMinerUProvider:
    def parse_document(self, input_path: Path, output_dir: Path):
        output_dir.mkdir(parents=True, exist_ok=True)
        markdown_path = output_dir / "problem.md"
        json_path = output_dir / "problem.json"
        markdown_path.write_text(
            "# Parsed Paper\n\nFigure design should explain the validation claim.",
            encoding="utf-8",
        )
        json_path.write_text("{}", encoding="utf-8")
        return type(
            "Parsed",
            (),
            {
                "markdown_path": str(markdown_path),
                "json_path": str(json_path),
                "page_count": 3,
                "warnings": ["low confidence table"],
            },
        )()


def test_methodology_rag_agent_ingests_pdf_knowledge_base_with_mineru(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    knowledge_base = tmp_path / "knowledge_base"
    (knowledge_base / "winning_papers").mkdir(parents=True)
    (knowledge_base / "winning_papers" / "solution.pdf").write_bytes(b"%PDF")

    MethodologyRAGAgent().run(
        workspace.root,
        supervisor_skills_dir=None,
        knowledge_base_dir=knowledge_base,
        mineru_provider=KnowledgeBaseMinerUProvider(),
    )

    hits = read_json(workspace.root / "rag" / "methodology_hits.json", [])
    parsed_hit = next(hit for hit in hits if hit["title"] == "solution.pdf")
    assert parsed_hit["source_type"] == "paper_example"
    assert parsed_hit["relative_path"] == "winning_papers/solution.pdf"
    assert parsed_hit["page_hint"] == "pages=3"
    assert "validation claim" in parsed_hit["content"]
    notes = (workspace.root / "rag" / "retrieval_notes.md").read_text(encoding="utf-8")
    assert "Parsed PDF knowledge-base document via MinerU: winning_papers/solution.pdf" in notes
    assert "MinerU warning for winning_papers/solution.pdf: low confidence table" in notes
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_rag.py::test_methodology_rag_agent_ingests_pdf_knowledge_base_with_mineru -q`

Expected: FAIL because `MethodologyRAGAgent.run` does not accept `mineru_provider`.

- [ ] **Step 3: Implement PDF parsing path**

Extend `MethodologyRAGAgent.run(...)` and `ingest_knowledge_base(...)` with optional `mineru_provider`.

For `.pdf`:

1. If `mineru_provider` is missing or has no callable `parse_document`, append `Pending PDF ingestion via MinerU: <relative_path>` and continue.
2. Build output dir as `workspace_root / "rag" / "parsed_knowledge" / safe_relative_stem`.
3. Call `parse_document(path, output_dir)`.
4. Read `parsed.markdown_path`.
5. Ingest chunks using the original PDF title and relative path.
6. Write notes for parse success and parser warnings.
7. On exception, append `Failed PDF ingestion via MinerU: <relative_path> (<error>)` and continue.

- [ ] **Step 4: Run PDF tests**

Run:

```bash
pytest tests/test_rag.py::test_methodology_rag_agent_ingests_pdf_knowledge_base_with_mineru \
  tests/test_rag.py::test_methodology_rag_agent_reports_pdf_as_pending -q
```

Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_rag.py src/mcm_agent/agents/rag.py
git commit -m "feat: ingest pdf knowledge base through mineru"
```

## Task 4: Workflow Provider Wiring

**Files:**
- Modify: `tests/test_mvp_workflow.py`
- Modify: `src/mcm_agent/workflows/mvp.py`

- [ ] **Step 1: Add failing workflow test**

Add this test to `tests/test_mvp_workflow.py`:

```python
def test_run_mvp_workflow_uses_configured_mineru_for_rag_pdf(tmp_path: Path) -> None:
    workspace = tmp_path / "task"
    problem = tmp_path / "problem.md"
    attachment = tmp_path / "data.csv"
    problem.write_text("# Problem\n\nUse a local PDF knowledge base.", encoding="utf-8")
    attachment.write_text("x,y\n1,2\n2,3\n", encoding="utf-8")
    knowledge_base = tmp_path / "knowledge_base"
    knowledge_base.mkdir()
    (knowledge_base / "paper_example.pdf").write_bytes(b"%PDF")
    providers = ProviderBundle(
        llm=FakeLLMProvider({"default": ""}),
        mineru=InjectedMinerUProvider(),
        search=InjectedSearchProvider(),
        extractor=InjectedExtractProvider(),
        official_data=None,
        humanizer=FakeHumanizerProvider({}),
        latex=InjectedLatexProvider(),
    )

    run_mvp_workflow(
        workspace,
        TaskInput(problem_file=problem, attachments=[attachment]),
        providers=providers,
        settings=Settings(rag_knowledge_base_dir=str(knowledge_base)),
        auto_approve=True,
    )

    notes = (workspace / "rag" / "retrieval_notes.md").read_text(encoding="utf-8")
    assert "Parsed PDF knowledge-base document via MinerU: paper_example.pdf" in notes
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_mvp_workflow.py::test_run_mvp_workflow_uses_configured_mineru_for_rag_pdf -q`

Expected: FAIL because the RAG stage does not pass `provider_bundle.mineru`.

- [ ] **Step 3: Pass the provider**

In `src/mcm_agent/workflows/mvp.py`, change the `methodology_rag` handler:

```python
MethodologyRAGAgent().run(
    workspace_root,
    supervisor_skills_dir,
    knowledge_base_dir=knowledge_base_dir,
    ingest_extensions=settings.rag_ingest_extensions,
    mineru_provider=provider_bundle.mineru,
)
```

- [ ] **Step 4: Run workflow tests**

Run:

```bash
pytest tests/test_mvp_workflow.py::test_run_mvp_workflow_uses_configured_mineru_for_rag_pdf \
  tests/test_mvp_workflow.py::test_run_mvp_workflow_uses_configured_rag_knowledge_base -q
```

Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_mvp_workflow.py src/mcm_agent/workflows/mvp.py
git commit -m "feat: wire mineru into rag pdf ingestion"
```

## Task 5: Documentation And Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/WORKFLOW.md`
- Modify: `docs/PROJECT_STATUS.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update docs**

Document:

- `knowledge_base/` can contain `.md`, `.txt`, and `.pdf`.
- `.pdf` files are parsed through the configured MinerU provider during `methodology_rag`.
- `rag/methodology_hits.json` includes `source_type`, `relative_path`, `chunk_id`, `page_hint`, and `usage`.
- RAG knowledge documents guide writing/model selection but are not external factual data sources.
- If MinerU is unavailable or parsing fails, PDFs are reported in retrieval notes without blocking the workflow.

- [ ] **Step 2: Run focused verification**

Run:

```bash
pytest tests/test_rag.py tests/test_mvp_workflow.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run full verification**

Run:

```bash
pytest -q
ruff check src tests scripts
```

Expected: all tests and lint checks pass.

- [ ] **Step 4: Commit docs**

```bash
git add README.md docs/WORKFLOW.md docs/PROJECT_STATUS.md docs/IMPLEMENTATION_PLAN.md
git commit -m "docs: describe rag ingestion expansion"
```

## Self-Review

- Spec coverage: The plan covers MinerU PDF ingestion, chunk-level provenance, source types, usage restrictions, workflow provider wiring, tests, and docs.
- Placeholder scan: No unresolved TODO/TBD placeholders remain.
- Type consistency: `source_type`, `relative_path`, `usage`, `chunk_id`, `chunk_index`, and `page_hint` are used consistently across tests and implementation tasks.
