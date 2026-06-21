# MCM Corpus RAG Knowledge Base — Implementation Plan (Plan 1: Subset-First, Working KB)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the local `assets/mcm_icm_corpus/` (502 outstanding papers + problems) into a queryable, metadata-rich RAG knowledge base the agent can retrieve modeling/writing patterns from — built on the project's existing Voyage + ChromaDB + MinerU scaffold.

**Architecture:** Add a new `mcm_agent.corpus` package that (1) builds a per-paper **metadata manifest** (Layer 0: year/contest/problem/problem-type/award/control#) from `catalog.json`, (2) converts the paper PDFs to Markdown via the existing MinerU provider (local `vlm-engine` on M-series), (3) **segments each paper into canonical MCM sections** (Layer 2), (4) section-aware chunks → **Voyage embeddings (cached)** → a shared persistent **ChromaDB collection `mcm_corpus`** + an FTS5 index, and (5) exposes **metadata-filtered retrieval** (by problem-type / section-type / award). A new `mag kb` CLI builds and queries it. This is one shared corpus KB, distinct from the existing per-workspace `rag/` index, but reusing the same `VectorIndex`, `EmbeddingCache`, `chunk_text`, and Voyage providers.

**Tech Stack:** Python 3.12, pydantic v2, ChromaDB (already a dep), Voyage `voyage-3-large` embeddings + `rerank-2` reranker (already wired in `providers/embedding.py` + `factory.py`), MinerU local CLI (`vlm-engine` backend on Mac), SQLite FTS5, Typer CLI, pytest + Typer `CliRunner`.

**On the Voyage question (decided):** Yes — the project is already built around Voyage. `config.example.json` sets `embedding.provider="voyage"`, `embedding_model="voyage-3-large"`, `rerank_model="rerank-2"`; `factory.build_provider_bundle` instantiates `VoyageEmbeddingProvider`/`VoyageRerankProvider` when a key is present, and falls back to `FakeEmbeddingProvider`/`FakeRerankProvider` (deterministic, offline) otherwise. This plan calls **Voyage embed + rerank APIs** for the real build, and the **Fake providers in all tests** (no network). MinerU runs **locally** (no API) on the M4. The LLM for the later "teardown cards" layer (Plan 2) uses the already-configured LLM provider, not Voyage.

---

## Scope

**This plan (Plan 1)** delivers a working, queryable corpus KB over a configurable subset (default: years 2018–2025, all problems; or filter to one problem letter). It covers KB Layers 0 (metadata), 1 (markdown), 2 (sections), and the index + retrieval. **Out of scope → Plan 2** (LLM "teardown cards" Layer 3 + pattern library Layer 4) and **Plan 3** (deep wiring of corpus retrieval into every workflow node + evaluation harness). Each plan ships working software on its own.

## File Structure

| File | Responsibility |
|---|---|
| `src/mcm_agent/corpus/__init__.py` | Package marker. |
| `src/mcm_agent/corpus/taxonomy.py` | Pure mapping: problem letter + year → problem-type label (continuous/discrete/data/OR-network/sustainability/policy). |
| `src/mcm_agent/corpus/manifest.py` | Build `CorpusEntry` records from `catalog.json` + paper-file control numbers; dedup; persist `manifest.json`. |
| `src/mcm_agent/corpus/sections.py` | Segment a paper's Markdown into canonical MCM sections; section-aware chunking. |
| `src/mcm_agent/corpus/convert.py` | Idempotent, content-hash-cached PDF→Markdown via a MinerU provider. |
| `src/mcm_agent/corpus/ingest.py` | Orchestrate manifest→convert→sections→chunks→FTS+Chroma(`mcm_corpus`); reuses `EmbeddingCache`, `VectorIndex`. |
| `src/mcm_agent/corpus/retrieve.py` | Metadata-filtered hybrid retrieval + section-exemplar / problem-type lookups over the shared corpus KB. |
| `src/mcm_agent/cli_commands/kb.py` | `mag kb build|status|query` Typer commands. |
| `src/mcm_agent/providers/mineru.py` | **Modify**: fix `LocalMinerUProvider` to honor a backend flag and locate real (nested) MinerU output. |
| `src/mcm_agent/config.py` | **Modify**: add `mineru_backend`, `corpus_source_dir`, `corpus_kb_dir` settings + JSON mapping. |
| `src/mcm_agent/cli.py` | **Modify**: register the `kb` command group. |
| `tests/corpus/test_*.py` | Tests per module (Fake providers, synthetic fixtures). |

Convention notes (follow existing code): modules start with `from __future__ import annotations`; JSON via `mcm_agent.utils.json_io.{read_json,write_json}`; pydantic `BaseModel` for records; tests use `pytest` + Typer `CliRunner`; `ruff` line-length 100. Run `pytest -q` and `ruff check src tests` after each task.

---

### Task 1: Problem-type taxonomy (Layer 0 foundation)

**Files:**
- Create: `src/mcm_agent/corpus/__init__.py` (empty)
- Create: `src/mcm_agent/corpus/taxonomy.py`
- Test: `tests/corpus/test_taxonomy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/corpus/test_taxonomy.py
from mcm_agent.corpus.taxonomy import problem_type

def test_modern_letters_map_to_types():
    assert problem_type(2024, "A") == "continuous"
    assert problem_type(2024, "B") == "discrete"
    assert problem_type(2024, "C") == "data"
    assert problem_type(2024, "D") == "operations_research"
    assert problem_type(2024, "E") == "sustainability"
    assert problem_type(2024, "F") == "policy"

def test_pre_icm_years_have_no_def_only_ab():
    # Before ICM split, only A/B exist; C was the early ICM problem
    assert problem_type(2001, "A") == "continuous"
    assert problem_type(2001, "B") == "discrete"
    assert problem_type(2001, "C") == "interdisciplinary"

def test_unknown_letter_is_unknown():
    assert problem_type(2024, "Z") == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/corpus/test_taxonomy.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcm_agent.corpus.taxonomy'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/mcm_agent/corpus/taxonomy.py
from __future__ import annotations

# Modern MCM/ICM (2016+): A/B/C are MCM, D/E/F are ICM.
_MODERN = {
    "A": "continuous",
    "B": "discrete",
    "C": "data",
    "D": "operations_research",
    "E": "sustainability",
    "F": "policy",
}
# Early years (pre-2016) used C as the single interdisciplinary (ICM) problem.
_EARLY = {"A": "continuous", "B": "discrete", "C": "interdisciplinary"}


def problem_type(year: int, letter: str) -> str:
    letter = (letter or "").strip().upper()[:1]
    table = _MODERN if year >= 2016 else _EARLY
    return table.get(letter, "unknown")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/corpus/test_taxonomy.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/corpus/__init__.py src/mcm_agent/corpus/taxonomy.py tests/corpus/test_taxonomy.py
git commit -m "feat(corpus): problem-type taxonomy mapping"
```

---

### Task 2: Corpus manifest (Layer 0 — metadata over the real files)

**Files:**
- Create: `src/mcm_agent/corpus/manifest.py`
- Test: `tests/corpus/test_manifest.py`

The manifest walks the cloned paper repos under `outstanding_papers/` and pairs each PDF with metadata. Control numbers are the digit-run in the filename (`2400996.pdf`, `A-6749-Outstanding.pdf`). Dedup by `(year, control_number)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/corpus/test_manifest.py
from pathlib import Path
from mcm_agent.corpus.manifest import build_manifest, CorpusEntry

def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    papers = root / "outstanding_papers" / "demo_repo" / "2024" / "C"
    papers.mkdir(parents=True)
    (papers / "2400996.pdf").write_bytes(b"%PDF-1.4 fake")
    (papers / "2401000.pdf").write_bytes(b"%PDF-1.4 fake2")
    dup = root / "outstanding_papers" / "other_repo" / "2024" / "C"
    dup.mkdir(parents=True)
    (dup / "2400996.pdf").write_bytes(b"%PDF-1.4 fake")  # same control# -> deduped
    return root

def test_build_manifest_extracts_metadata_and_dedups(tmp_path):
    root = _make_corpus(tmp_path)
    entries = build_manifest(root)
    assert all(isinstance(e, CorpusEntry) for e in entries)
    keys = {(e.year, e.control_number) for e in entries}
    assert (2024, "2400996") in keys
    assert (2024, "2401000") in keys
    assert len(entries) == 2  # the duplicate 2400996 collapsed
    one = next(e for e in entries if e.control_number == "2400996")
    assert one.problem == "C" and one.contest == "MCM" and one.problem_type == "data"
    assert one.pdf_path.endswith("2400996.pdf")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/corpus/test_manifest.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcm_agent.corpus.manifest'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/mcm_agent/corpus/manifest.py
from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from mcm_agent.corpus.taxonomy import problem_type
from mcm_agent.utils.json_io import write_json

_YEAR_RE = re.compile(r"(19|20)\d{2}")
_LETTER_DIR_RE = re.compile(r"^[A-F]$")
_LETTER_PREFIX_RE = re.compile(r"^([A-F])[-_]")
_CONTROL_RE = re.compile(r"(\d{4,})")


class CorpusEntry(BaseModel):
    paper_id: str               # f"{year}-{control_number}"
    year: int
    contest: str                # MCM or ICM
    problem: str                # A-F (or "?")
    problem_type: str
    control_number: str
    award: str = "Outstanding"  # refined in Plan 2 via results PDFs
    pdf_path: str               # absolute path
    source_repo: str            # top folder under outstanding_papers/


def _year_from_parts(parts: tuple[str, ...]) -> int | None:
    for part in parts:
        m = _YEAR_RE.search(part)
        if m:
            return int(m.group(0))
    return None


def _letter_from(parts: tuple[str, ...], filename: str) -> str:
    for part in reversed(parts):
        if _LETTER_DIR_RE.match(part):
            return part
        m = re.match(r"^([A-F])题", part)
        if m:
            return m.group(1)
    m = _LETTER_PREFIX_RE.match(filename)
    return m.group(1) if m else "?"


def build_manifest(corpus_root: Path) -> list[CorpusEntry]:
    papers_root = Path(corpus_root) / "outstanding_papers"
    seen: dict[tuple[int, str], CorpusEntry] = {}
    for pdf in sorted(papers_root.rglob("*.pdf")):
        rel = pdf.relative_to(papers_root)
        parts = rel.parts
        low = pdf.as_posix().lower()
        if any(tok in low for tok in ("problem", "result", "triage", "commentary", "addendum")):
            continue  # skip bundled problem/results/aux PDFs
        year = _year_from_parts(parts)
        control = None
        m = _CONTROL_RE.search(pdf.stem)
        if m:
            control = m.group(1)
        if year is None or control is None:
            continue
        if (year, control) in seen:
            continue
        letter = _letter_from(parts, pdf.name)
        contest = "ICM" if letter in {"D", "E", "F"} or (year < 2016 and letter == "C") else "MCM"
        seen[(year, control)] = CorpusEntry(
            paper_id=f"{year}-{control}",
            year=year,
            contest=contest,
            problem=letter,
            problem_type=problem_type(year, letter),
            control_number=control,
            pdf_path=str(pdf.resolve()),
            source_repo=parts[0],
        )
    return list(seen.values())


def write_manifest(entries: list[CorpusEntry], out_path: Path) -> None:
    write_json(out_path, [e.model_dump() for e in entries])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/corpus/test_manifest.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/corpus/manifest.py tests/corpus/test_manifest.py
git commit -m "feat(corpus): metadata manifest with control-number dedup"
```

---

### Task 3: MCM section segmentation (Layer 2)

**Files:**
- Create: `src/mcm_agent/corpus/sections.py`
- Test: `tests/corpus/test_sections.py`

Splits a paper's Markdown by headings and classifies each heading into a canonical MCM section. Then `section_chunks()` produces `(section_type, chunk_text)` pairs, reusing the existing paragraph chunker.

- [ ] **Step 1: Write the failing test**

```python
# tests/corpus/test_sections.py
from mcm_agent.corpus.sections import segment_sections, section_chunks

SAMPLE = """# Summary
We model tennis momentum.

## 1. Introduction and Restatement
Background here.

## 2. Assumptions and Justifications
- Assume players are independent.

## 3. Model Development
We build a Markov chain. (long body) """ + ("x " * 2000) + """

## 4. Sensitivity Analysis
We vary alpha.

## 5. Strengths and Weaknesses
Strengths: robust.

## References
[1] Foo.
"""

def test_segment_classifies_canonical_sections():
    secs = segment_sections(SAMPLE)
    kinds = {s.section_type for s in secs}
    assert "summary" in kinds
    assert "assumptions" in kinds
    assert "model" in kinds
    assert "sensitivity" in kinds
    assert "strengths_weaknesses" in kinds
    assert "references" in kinds

def test_section_chunks_carry_type_and_split_long_bodies():
    chunks = section_chunks(SAMPLE)
    model_chunks = [c for c in chunks if c[0] == "model"]
    assert len(model_chunks) >= 2  # long model body split into multiple chunks
    assert all(isinstance(c[1], str) and c[1].strip() for c in chunks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/corpus/test_sections.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcm_agent.corpus.sections'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/mcm_agent/corpus/sections.py
from __future__ import annotations

import re

from pydantic import BaseModel

from mcm_agent.agents.rag import chunk_text  # reuse existing paragraph chunker

_HEADING_RE = re.compile(r"^#{1,4}\s+(.*\S)\s*$", re.MULTILINE)

# Ordered: first matching keyword wins. Lowercased substring match on heading text.
_SECTION_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("summary", ("summary", "abstract")),
    ("restatement", ("restatement", "introduction", "background", "problem statement")),
    ("assumptions", ("assumption", "justification")),
    ("notation", ("notation", "symbol", "variables", "glossary")),
    ("sensitivity", ("sensitivity", "robustness", "stability analysis")),
    ("strengths_weaknesses", ("strength", "weakness", "limitation")),
    ("conclusion", ("conclusion", "discussion", "future work")),
    ("references", ("reference", "bibliography")),
    ("model", ("model", "method", "approach", "formulation", "solution", "results", "analysis")),
]


class Section(BaseModel):
    section_type: str
    heading: str
    body: str


def _classify(heading: str) -> str:
    low = heading.lower()
    for section_type, keywords in _SECTION_RULES:
        if any(kw in low for kw in keywords):
            return section_type
    return "other"


def segment_sections(markdown: str) -> list[Section]:
    matches = list(_HEADING_RE.finditer(markdown))
    if not matches:
        return [Section(section_type="other", heading="(body)", body=markdown.strip())]
    sections: list[Section] = []
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()
        sections.append(Section(section_type=_classify(heading), heading=heading, body=body))
    return sections


def section_chunks(markdown: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for section in segment_sections(markdown):
        for chunk in chunk_text(section.body):
            out.append((section.section_type, chunk))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/corpus/test_sections.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/corpus/sections.py tests/corpus/test_sections.py
git commit -m "feat(corpus): MCM section segmentation + section-aware chunking"
```

---

### Task 4: Fix `LocalMinerUProvider` for real M-series output

**Files:**
- Modify: `src/mcm_agent/providers/mineru.py:55-75`
- Modify: `src/mcm_agent/config.py` (add `mineru_backend`)
- Test: `tests/corpus/test_mineru_local.py`

Real `mineru -p in.pdf -o out -b vlm-engine` writes `out/<stem>/auto/<stem>.md` (+ `_content_list.json`, `images/`), not `out/problem.md`. Factor output collection into `_collect_local_outputs(result_root, output_dir)` and test it against a synthetic tree (no real MinerU needed).

- [ ] **Step 1: Write the failing test**

```python
# tests/corpus/test_mineru_local.py
from pathlib import Path
from mcm_agent.providers.mineru import LocalMinerUProvider

def test_collect_locates_nested_markdown(tmp_path: Path):
    out = tmp_path / "out"
    auto = out / "mypaper" / "auto"
    auto.mkdir(parents=True)
    (auto / "mypaper.md").write_text("# Real Markdown\n\nbody", encoding="utf-8")
    (auto / "mypaper_content_list.json").write_text("[]", encoding="utf-8")
    parsed = LocalMinerUProvider()._collect_local_outputs(out, out)
    assert Path(parsed.markdown_path).read_text(encoding="utf-8").startswith("# Real Markdown")
    assert parsed.json_path.endswith(".json")

def test_backend_flag_in_command(monkeypatch, tmp_path: Path):
    captured = {}
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        # emulate MinerU writing nested output
        auto = Path(kwargs["cwd"]) / "doc" / "auto"
        auto.mkdir(parents=True, exist_ok=True)
        (auto / "doc.md").write_text("# X", encoding="utf-8")
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    monkeypatch.setattr("mcm_agent.providers.mineru.subprocess.run", fake_run)
    pdf = tmp_path / "doc.pdf"; pdf.write_bytes(b"%PDF")
    LocalMinerUProvider(backend="vlm-engine").parse_document(pdf, tmp_path / "out")
    assert "-b" in captured["cmd"] and "vlm-engine" in captured["cmd"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/corpus/test_mineru_local.py -q`
Expected: FAIL — `LocalMinerUProvider` has no `_collect_local_outputs` / no `backend` kwarg.

- [ ] **Step 3: Write minimal implementation**

Replace `LocalMinerUProvider` (currently `mineru.py:55-75`) with:

```python
class LocalMinerUProvider:
    def __init__(self, command: str = "mineru", backend: str = "pipeline") -> None:
        self.command = command
        self.backend = backend

    def parse_document(self, input_path: Path, output_dir: Path) -> ParsedDocument:
        output_dir.mkdir(parents=True, exist_ok=True)
        log_path = output_dir / "mineru_cli.log"
        cmd = [self.command, "-p", str(input_path), "-o", str(output_dir), "-b", self.backend]
        result = subprocess.run(cmd, cwd=output_dir, capture_output=True, text=True, check=False)
        log_path.write_text((result.stdout or "") + "\n" + (result.stderr or ""), encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError(f"MinerU CLI parse failed: {result.returncode}; log={log_path}")
        return self._collect_local_outputs(output_dir, output_dir)

    def _collect_local_outputs(self, result_root: Path, output_dir: Path) -> ParsedDocument:
        md = self._find_first(result_root, ("*.md",))
        content = self._find_first(result_root, ("*_content_list.json", "*.json"))
        markdown_path = output_dir / "problem.md"
        json_path = output_dir / "problem.json"
        if md:
            shutil.copy2(md, markdown_path)
        else:
            markdown_path.write_text("", encoding="utf-8")
        if content:
            shutil.copy2(content, json_path)
        else:
            json_path.write_text("{}", encoding="utf-8")
        images = [str(p) for p in sorted(result_root.rglob("*.jpg")) + sorted(result_root.rglob("*.png"))]
        return ParsedDocument(
            markdown_path=str(markdown_path),
            json_path=str(json_path),
            image_paths=images,
        )

    @staticmethod
    def _find_first(root: Path, patterns: tuple[str, ...]) -> Path | None:
        for pattern in patterns:
            matches = sorted(p for p in root.rglob(pattern) if "problem.md" not in p.name)
            if matches:
                return matches[0]
        return None
```

Add to `Settings` in `config.py` (after `mineru_cli`, ~line 38):

```python
    mineru_backend: str = "pipeline"
```

And in the JSON mapping dict (near `("mineru", "cli"): "mineru_cli"`):

```python
        ("mineru", "backend"): "mineru_backend",
```

Then in `factory.build_provider_bundle` (`factory.py:78-79`) pass the backend:

```python
    if settings.mineru_mode == "local":
        mineru = LocalMinerUProvider(settings.mineru_cli, backend=settings.mineru_backend)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/corpus/test_mineru_local.py tests/test_cli_config.py -q`
Expected: PASS (and existing config test still green)

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/providers/mineru.py src/mcm_agent/config.py src/mcm_agent/providers/factory.py tests/corpus/test_mineru_local.py
git commit -m "fix(mineru): local provider honors backend flag and locates nested output"
```

---

### Task 5: Idempotent cached PDF→Markdown conversion

**Files:**
- Create: `src/mcm_agent/corpus/convert.py`
- Test: `tests/corpus/test_convert.py`

Convert each PDF once, keyed by content hash, into `<kb>/markdown/<paper_id>.md`. Resumable: existing output is skipped. Uses any object with `parse_document(input_path, output_dir)` (the MinerU provider) — tests pass `FakeMinerUProvider`.

- [ ] **Step 1: Write the failing test**

```python
# tests/corpus/test_convert.py
from pathlib import Path
from mcm_agent.providers.mineru import FakeMinerUProvider
from mcm_agent.corpus.convert import convert_entry, ConvertResult

def test_convert_writes_markdown_and_is_idempotent(tmp_path: Path):
    pdf = tmp_path / "p.pdf"; pdf.write_text("hello", encoding="utf-8")  # Fake reads .md only; non-md -> stub md
    kb = tmp_path / "kb"
    r1 = convert_entry("2024-2400996", pdf, kb, FakeMinerUProvider())
    assert isinstance(r1, ConvertResult) and Path(r1.markdown_path).exists()
    assert r1.converted is True
    mtime1 = Path(r1.markdown_path).stat().st_mtime_ns
    r2 = convert_entry("2024-2400996", pdf, kb, FakeMinerUProvider())
    assert r2.converted is False  # skipped (cache hit)
    assert Path(r2.markdown_path).stat().st_mtime_ns == mtime1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/corpus/test_convert.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# src/mcm_agent/corpus/convert.py
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class ConvertResult(BaseModel):
    paper_id: str
    markdown_path: str
    converted: bool  # True if freshly parsed, False if served from cache


def convert_entry(paper_id: str, pdf_path: Path, kb_dir: Path, mineru_provider: object) -> ConvertResult:
    markdown_dir = Path(kb_dir) / "markdown"
    markdown_dir.mkdir(parents=True, exist_ok=True)
    final_md = markdown_dir / f"{paper_id}.md"
    if final_md.exists() and final_md.stat().st_size > 0:
        return ConvertResult(paper_id=paper_id, markdown_path=str(final_md), converted=False)

    work_dir = Path(kb_dir) / "_work" / paper_id
    parsed = mineru_provider.parse_document(Path(pdf_path), work_dir)
    content = Path(parsed.markdown_path).read_text(encoding="utf-8")
    final_md.write_text(content, encoding="utf-8")
    return ConvertResult(paper_id=paper_id, markdown_path=str(final_md), converted=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/corpus/test_convert.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/corpus/convert.py tests/corpus/test_convert.py
git commit -m "feat(corpus): idempotent cached PDF->Markdown conversion"
```

---

### Task 6: Corpus ingest — sections → chunks → FTS + Chroma (`mcm_corpus`)

**Files:**
- Create: `src/mcm_agent/corpus/ingest.py`
- Test: `tests/corpus/test_ingest.py`

Reuses `MethodologyStore` (FTS5), `VectorIndex` (Chroma), `EmbeddingCache`. Each chunk's metadata carries `paper_id, year, contest, problem, problem_type, section_type, award, source` so retrieval can filter. Filters control the subset (years / problems).

- [ ] **Step 1: Write the failing test**

```python
# tests/corpus/test_ingest.py
from pathlib import Path
from mcm_agent.providers.mineru import FakeMinerUProvider
from mcm_agent.providers.embedding import FakeEmbeddingProvider, FakeRerankProvider
from mcm_agent.corpus.manifest import CorpusEntry
from mcm_agent.corpus.ingest import ingest_corpus, CorpusKB

def _entry(tmp_path, pid, year, letter, ptype, body):
    p = tmp_path / f"{pid}.md"           # Fake MinerU echoes .md content through
    p.write_text(body, encoding="utf-8")
    return CorpusEntry(paper_id=pid, year=year, contest="MCM", problem=letter,
                       problem_type=ptype, control_number=pid.split("-")[1],
                       pdf_path=str(p), source_repo="demo")

def test_ingest_builds_filtered_kb_with_metadata(tmp_path):
    kb_dir = tmp_path / "kb"
    entries = [
        _entry(tmp_path, "2024-100", 2024, "C", "data", "# Summary\n\nData model.\n\n## Sensitivity Analysis\n\nVary k."),
        _entry(tmp_path, "2014-200", 2014, "A", "continuous", "# Summary\n\nOld continuous paper."),
    ]
    summary = ingest_corpus(
        entries, kb_dir,
        mineru_provider=FakeMinerUProvider(),
        embedding_provider=FakeEmbeddingProvider(),
        embedding_model="fake",
        years={2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025},  # excludes 2014
    )
    assert summary.papers_ingested == 1
    assert summary.chunks_indexed >= 2
    kb = CorpusKB(kb_dir)
    hits = kb.query("sensitivity", FakeEmbeddingProvider(), FakeRerankProvider(),
                    where={"section_type": "sensitivity"}, top_k=3)
    assert hits and hits[0].metadata["paper_id"] == "2024-100"
    assert hits[0].metadata["problem_type"] == "data"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/corpus/test_ingest.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# src/mcm_agent/corpus/ingest.py
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from mcm_agent.core.embedding_cache import EmbeddingCache
from mcm_agent.core.vector_index import VectorIndex
from mcm_agent.corpus.convert import convert_entry
from mcm_agent.corpus.manifest import CorpusEntry
from mcm_agent.corpus.sections import section_chunks
from mcm_agent.utils.json_io import write_json

_COLLECTION = "mcm_corpus"


class IngestSummary(BaseModel):
    papers_ingested: int
    chunks_indexed: int
    skipped: int


class CorpusHit(BaseModel):
    content: str
    metadata: dict
    rerank_score: float = 0.0


def _passes(entry: CorpusEntry, years: set[int] | None, problems: set[str] | None) -> bool:
    if years is not None and entry.year not in years:
        return False
    if problems is not None and entry.problem not in problems:
        return False
    return True


def ingest_corpus(
    entries: list[CorpusEntry],
    kb_dir: Path,
    *,
    mineru_provider: object,
    embedding_provider: object,
    embedding_model: str,
    years: set[int] | None = None,
    problems: set[str] | None = None,
) -> IngestSummary:
    kb_dir = Path(kb_dir)
    kb_dir.mkdir(parents=True, exist_ok=True)
    index = VectorIndex(persist_dir=kb_dir / "chroma", collection_name=_COLLECTION)
    cache = EmbeddingCache(kb_dir / "embedding_cache.db")

    selected = [e for e in entries if _passes(e, years, problems)]
    write_json(kb_dir / "manifest.json", [e.model_dump() for e in selected])

    papers = chunks_total = skipped = 0
    for entry in selected:
        try:
            result = convert_entry(entry.paper_id, Path(entry.pdf_path), kb_dir, mineru_provider)
        except Exception:
            skipped += 1
            continue
        markdown = Path(result.markdown_path).read_text(encoding="utf-8")
        pairs = section_chunks(markdown)
        if not pairs:
            skipped += 1
            continue
        ids, docs, metas, texts = [], [], [], []
        for i, (section_type, chunk) in enumerate(pairs, 1):
            cid = f"{entry.paper_id}#chunk-{i:03d}"
            ids.append(cid)
            docs.append(chunk)
            texts.append(chunk)
            metas.append({
                "paper_id": entry.paper_id,
                "year": entry.year,
                "contest": entry.contest,
                "problem": entry.problem,
                "problem_type": entry.problem_type,
                "section_type": section_type,
                "award": entry.award,
                "source": entry.pdf_path,
                "chunk_index": i,
            })
        embeddings = cache.embed_with_cache(embedding_provider, embedding_model, texts)
        index.add_chunks(ids=ids, embeddings=embeddings, documents=docs, metadatas=metas)
        papers += 1
        chunks_total += len(ids)
    return IngestSummary(papers_ingested=papers, chunks_indexed=chunks_total, skipped=skipped)


class CorpusKB:
    def __init__(self, kb_dir: Path) -> None:
        self.kb_dir = Path(kb_dir)
        self.index = VectorIndex(persist_dir=self.kb_dir / "chroma", collection_name=_COLLECTION)

    def query(
        self,
        query: str,
        embedding_provider: object,
        reranker: object | None = None,
        *,
        where: dict | None = None,
        top_k: int = 5,
        candidate_n: int = 20,
    ) -> list[CorpusHit]:
        vector = embedding_provider.embed([query])[0]
        raw = self.index.query_where(vector, candidate_n, where=where)
        if not raw:
            return []
        if reranker is not None:
            ranked = reranker.rerank(query, [r["content"] for r in raw], top_k)
            return [
                CorpusHit(content=raw[row["index"]]["content"],
                          metadata=raw[row["index"]]["metadata"],
                          rerank_score=float(row["score"]))
                for row in ranked
            ]
        return [CorpusHit(content=r["content"], metadata=r["metadata"]) for r in raw[:top_k]]
```

Add a `query_where` method to `VectorIndex` (`core/vector_index.py`) that forwards a Chroma `where` filter:

```python
    def query_where(self, embedding: list[float], top_n: int, *, where: dict | None = None) -> list[dict]:
        kwargs = {"query_embeddings": [embedding], "n_results": top_n}
        if where:
            kwargs["where"] = where
        result = self._collection.query(**kwargs)
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        return [
            {"chunk_id": cid,
             "content": documents[i] if i < len(documents) else "",
             "metadata": metadatas[i] if i < len(metadatas) else {}}
            for i, cid in enumerate(ids)
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/corpus/test_ingest.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/corpus/ingest.py src/mcm_agent/core/vector_index.py tests/corpus/test_ingest.py
git commit -m "feat(corpus): ingest pipeline -> Chroma mcm_corpus with filterable metadata"
```

---

### Task 7: `mag kb` CLI (build / status / query)

**Files:**
- Create: `src/mcm_agent/cli_commands/kb.py`
- Modify: `src/mcm_agent/cli.py` (register `kb` Typer group)
- Modify: `src/mcm_agent/config.py` (add `corpus_source_dir`, `corpus_kb_dir`)
- Test: `tests/corpus/test_kb_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/corpus/test_kb_cli.py
from pathlib import Path
from typer.testing import CliRunner
from mcm_agent.cli import app

def _seed_corpus(root: Path):
    d = root / "outstanding_papers" / "demo" / "2024" / "C"
    d.mkdir(parents=True)
    (d / "2400996.md").write_text("# Summary\n\nA data model.\n", encoding="utf-8")
    (d / "2400996.pdf").write_text("# Summary\n\nA data model.\n", encoding="utf-8")

def test_kb_build_and_status(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"; _seed_corpus(corpus)
    kb = tmp_path / "kb"
    monkeypatch.setenv("MAG_LLM_PROVIDER", "fake")  # forces Fake embed/rerank/mineru bundle
    runner = CliRunner()
    res = runner.invoke(app, ["kb", "build", "--corpus", str(corpus), "--kb", str(kb),
                              "--years", "2024", "--problems", "C"])
    assert res.exit_code == 0, res.output
    assert (kb / "chroma").exists()
    res2 = runner.invoke(app, ["kb", "status", "--kb", str(kb)])
    assert res2.exit_code == 0 and "papers" in res2.output.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/corpus/test_kb_cli.py -q`
Expected: FAIL — no `kb` command.

- [ ] **Step 3: Write minimal implementation**

```python
# src/mcm_agent/cli_commands/kb.py
from __future__ import annotations

from pathlib import Path

import typer

from mcm_agent.config import load_settings
from mcm_agent.corpus.ingest import CorpusKB, ingest_corpus
from mcm_agent.corpus.manifest import build_manifest
from mcm_agent.providers.embedding import FakeEmbeddingProvider, FakeRerankProvider
from mcm_agent.providers.factory import build_provider_bundle
from mcm_agent.utils.json_io import read_json

kb_app = typer.Typer(help="Build and query the MCM outstanding-paper knowledge base.")


def _bundle(workspace: Path):
    settings = load_settings(workspace)
    return build_provider_bundle(settings, workspace_root=workspace), settings


def _parse_set(value: str | None, cast):
    if not value:
        return None
    return {cast(item.strip()) for item in value.split(",") if item.strip()}


@kb_app.command("build")
def build(
    corpus: Path = typer.Option(..., "--corpus", help="Path to assets/mcm_icm_corpus"),
    kb: Path = typer.Option(Path("corpus_kb"), "--kb", help="Output KB dir"),
    years: str = typer.Option("", "--years", help="Comma list, e.g. 2018,2019,...; empty=all"),
    problems: str = typer.Option("", "--problems", help="Comma list of letters; empty=all"),
) -> None:
    bundle, settings = _bundle(Path.cwd())
    entries = build_manifest(corpus)
    typer.echo(f"Manifest: {len(entries)} papers discovered.")
    summary = ingest_corpus(
        entries, kb,
        mineru_provider=bundle.mineru,
        embedding_provider=bundle.embedding,
        embedding_model=settings.embedding_model,
        years=_parse_set(years, int),
        problems=_parse_set(problems, str),
    )
    typer.echo(f"Ingested papers={summary.papers_ingested} chunks={summary.chunks_indexed} "
               f"skipped={summary.skipped} -> {kb}")


@kb_app.command("status")
def status(kb: Path = typer.Option(Path("corpus_kb"), "--kb")) -> None:
    manifest = read_json(kb / "manifest.json", [])
    typer.echo(f"KB at {kb}: {len(manifest)} papers indexed.")
    by_year: dict[int, int] = {}
    for entry in manifest:
        by_year[entry.get("year")] = by_year.get(entry.get("year"), 0) + 1
    for year in sorted(by_year):
        typer.echo(f"  {year}: {by_year[year]}")


@kb_app.command("query")
def query(
    text: str = typer.Argument(..., help="Query text"),
    kb: Path = typer.Option(Path("corpus_kb"), "--kb"),
    section: str = typer.Option("", "--section", help="Filter by section_type"),
    problem_type: str = typer.Option("", "--problem-type", help="Filter by problem_type"),
    top_k: int = typer.Option(5, "--top-k"),
) -> None:
    bundle, _ = _bundle(Path.cwd())
    where = {}
    if section:
        where["section_type"] = section
    if problem_type:
        where["problem_type"] = problem_type
    hits = CorpusKB(kb).query(text, bundle.embedding, bundle.reranker,
                              where=where or None, top_k=top_k)
    for hit in hits:
        meta = hit.metadata
        typer.echo(f"[{meta.get('paper_id')} {meta.get('problem_type')}/{meta.get('section_type')}] "
                   f"{hit.content[:200].strip()}")
```

Register in `cli.py` (after `app = typer.Typer(...)`, ~line 26):

```python
from mcm_agent.cli_commands.kb import kb_app
app.add_typer(kb_app, name="kb")
```

Add to `Settings` in `config.py` (after `rag_knowledge_base_dir`):

```python
    corpus_source_dir: str = "assets/mcm_icm_corpus"
    corpus_kb_dir: str = "corpus_kb"
```

And the JSON mapping (near `("rag", "knowledge_base_dir")`):

```python
        ("rag", "corpus_source_dir"): "corpus_source_dir",
        ("rag", "corpus_kb_dir"): "corpus_kb_dir",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/corpus/test_kb_cli.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/cli_commands/kb.py src/mcm_agent/cli.py src/mcm_agent/config.py tests/corpus/test_kb_cli.py
git commit -m "feat(cli): mag kb build/status/query over the corpus KB"
```

---

### Task 8: Section-exemplar + problem-type retrieval helpers

**Files:**
- Create: `src/mcm_agent/corpus/retrieve.py`
- Test: `tests/corpus/test_retrieve.py`

Writing-oriented retrieval the agent actually needs: "show me strong <section> examples for <problem_type>".

- [ ] **Step 1: Write the failing test**

```python
# tests/corpus/test_retrieve.py
from pathlib import Path
from mcm_agent.providers.mineru import FakeMinerUProvider
from mcm_agent.providers.embedding import FakeEmbeddingProvider, FakeRerankProvider
from mcm_agent.corpus.manifest import CorpusEntry
from mcm_agent.corpus.ingest import ingest_corpus
from mcm_agent.corpus.retrieve import section_exemplars

def test_section_exemplars_filters_by_section_and_type(tmp_path):
    md = tmp_path / "2024-1.md"
    md.write_text("# Summary\n\nx\n\n## Sensitivity Analysis\n\nWe perturb the demand parameter.", encoding="utf-8")
    e = CorpusEntry(paper_id="2024-1", year=2024, contest="MCM", problem="C",
                    problem_type="data", control_number="1", pdf_path=str(md), source_repo="d")
    kb = tmp_path / "kb"
    ingest_corpus([e], kb, mineru_provider=FakeMinerUProvider(),
                  embedding_provider=FakeEmbeddingProvider(), embedding_model="fake")
    hits = section_exemplars(kb, "how to vary parameters", section="sensitivity",
                             problem_type="data", embedding_provider=FakeEmbeddingProvider(),
                             reranker=FakeRerankProvider(), top_k=3)
    assert hits and all(h.metadata["section_type"] == "sensitivity" for h in hits)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/corpus/test_retrieve.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# src/mcm_agent/corpus/retrieve.py
from __future__ import annotations

from pathlib import Path

from mcm_agent.corpus.ingest import CorpusHit, CorpusKB


def section_exemplars(
    kb_dir: Path,
    query: str,
    *,
    section: str,
    embedding_provider: object,
    reranker: object | None = None,
    problem_type: str | None = None,
    top_k: int = 5,
) -> list[CorpusHit]:
    where: dict = {"section_type": section}
    if problem_type:
        where = {"$and": [{"section_type": section}, {"problem_type": problem_type}]}
    return CorpusKB(kb_dir).query(query, embedding_provider, reranker, where=where, top_k=top_k)


def methods_for_problem_type(
    kb_dir: Path,
    problem_type: str,
    *,
    embedding_provider: object,
    reranker: object | None = None,
    top_k: int = 8,
) -> list[CorpusHit]:
    where = {"$and": [{"problem_type": problem_type}, {"section_type": "model"}]}
    return CorpusKB(kb_dir).query(
        "modeling approach and method", embedding_provider, reranker, where=where, top_k=top_k
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/corpus/test_retrieve.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/corpus/retrieve.py tests/corpus/test_retrieve.py
git commit -m "feat(corpus): section-exemplar and problem-type retrieval helpers"
```

---

### Task 9: Real PoC on M4 (verification gate — not TDD)

**Files:**
- None (operational verification using real MinerU + real Voyage on a tiny subset)

- [ ] **Step 1: Configure real providers**

Edit `mcm_agent_config.local.json`: set `embedding.api_key` to your Voyage key, `mineru.mode="local"`, `mineru.backend="vlm-engine"`. Install MinerU per the Mac instructions (`uv pip install -U "mineru[all]"`).

- [ ] **Step 2: Build a 6-paper subset (2024 C)**

Run:
```bash
mag kb build --corpus assets/mcm_icm_corpus --kb corpus_kb --years 2024 --problems C
```
Expected: prints `Manifest: N papers discovered.` then `Ingested papers=~11 chunks=>50 skipped=0 -> corpus_kb`. (2024 C had 11 O-papers.)

- [ ] **Step 3: Inspect conversion quality**

Run:
```bash
ls corpus_kb/markdown/ && head -40 corpus_kb/markdown/2024-*.md
```
Expected: real Markdown with headings, LaTeX formulas (`$...$`), and tables — NOT garbled text. If formulas are broken, confirm `mineru.backend=vlm-engine` (not `pipeline`).

- [ ] **Step 4: Query and eyeball relevance**

Run:
```bash
mag kb query "how did winners design the sensitivity analysis" --kb corpus_kb --section sensitivity --problem-type data
```
Expected: 3–5 hits, all from 2024 C papers, all section_type=sensitivity, content visibly about sensitivity/robustness.

- [ ] **Step 5: Record throughput, then commit config + notes**

Note wall-clock per paper (for planning full-corpus build). Append findings to `docs/superpowers/plans/2026-06-21-mcm-corpus-rag-kb.md` under a "PoC Results" heading.

```bash
git add docs/superpowers/plans/2026-06-21-mcm-corpus-rag-kb.md
git commit -m "docs(corpus): record M4 PoC throughput and quality findings"
```

---

## Follow-on Plans (not implemented here)

- **Plan 2 — Distillation layer (Layers 3 & 4):** per-paper LLM "teardown cards" (problem, models used, why-it-won, techniques) via the configured LLM provider; aggregate a problem-type→method pattern library and section-exemplar templates; index cards as high-value chunks. Refine `CorpusEntry.award` by cross-referencing `results/<year>/*.pdf` (INFORMS/SIAM/MAA/Finalist).
- **Plan 3 — Workflow integration + eval:** wire `CorpusKB`/`section_exemplars` into the `methodology_rag`, `modeling_council`, and `writer` nodes (`workflows/mvp.py`, `core/workflow_graph.py`); add a retrieval-quality eval (hit precision per section/problem-type); add a plagiarism guard so retrieved text informs structure, never verbatim output.

## Self-Review

- **Spec coverage:** Layer 0 (Tasks 1–2), Layer 1 (Tasks 4–5), Layer 2 (Task 3), index (Task 6), retrieval (Tasks 6,8), CLI (Task 7), real-stack validation (Task 9). MinerU-local correctness (Task 4) closes the only real blocker for M4 use. Voyage decision documented in header. Layers 3–4 explicitly deferred to Plan 2. ✅
- **Placeholder scan:** every code step contains complete code; no TODO/"handle edge cases". ✅
- **Type consistency:** `CorpusEntry` fields are identical across Tasks 2/6/7/8; `ingest_corpus(...)` signature matches its CLI (Task 7) and test (Task 6) callers; `CorpusKB.query(..., where=, top_k=)` matches `retrieve.py` (Task 8) and `kb.py` (Task 7); `VectorIndex.query_where` is defined in Task 6 before use; `LocalMinerUProvider(command, backend=...)` matches the factory change (Task 4). ✅

---

## PoC Results (2026-06-21, real M4 / Mac, 24 GB)

**Implementation:** Tasks 1–8 done on branch `feat/corpus-rag-kb` (8 commits, 18 corpus tests green, ruff clean). Manifest hardened beyond plan after real-data validation (year-range bug, `其他奖项` skip, 3-digit controls, MCM/ICM-YYYY folders) → **455 Outstanding-only papers, 2004–2026**.

**Environment fixes discovered:**
- **MinerU 3.4 backend flag is `vlm-engine`**, not `vlm-mlx-engine` (auto-uses MLX on Apple Silicon). Plan + config corrected.
- **HuggingFace model download stalls in CN** (stuck ~33 min at 1.56 GB). Fix: `export MINERU_MODEL_SOURCE=modelscope` → reliable. Model = `MinerU2.5-Pro-2605-1.2B` (~2.15 GB, one-time, cached).
- **`factory` footgun:** `llm.provider="fake"` short-circuits to an all-fake bundle (forces `FakeMinerUProvider`). For "real MinerU + fake embeddings" use a non-fake llm provider with an empty key. Candidate follow-up: decouple these.

**MinerU quality (2024-C "Momentum in Tennis", `2410482.pdf`):** clean Markdown — `# SUMMARY`, section headings, table, and **correct LaTeX formulas**, e.g. `\tanh(\frac{x}{2}) = \frac{e^{x/2}-e^{-x/2}}{e^{x/2}+e^{-x/2}}`, conditional probabilities, subscripts, Greek, `$$…$$` blocks. Section segmenter cleanly recovers summary/assumptions/notation/model/sensitivity.

**End-to-end `mag kb build` (2-paper mini-corpus, real `vlm-engine` + Fake embed):** `papers=2 chunks=105 skipped=0`. Converted Markdown: 1332/873 lines, 35/57 headings, 20/90 inline LaTeX formulas. `mag kb status` → 2 papers (2024). `mag kb query "...sensitivity analysis" --section sensitivity` → returned the real State-Space-Model/Kalman-Filter sensitivity passage, tagged `data/sensitivity`. **Whole pipeline (convert→sections→chunk→index→filtered-retrieve) validated on real output.** ✅

**Throughput (M4 base, 24 GB, cached model) — measured, corrected:** **~13.5 min/full paper** with `vlm-engine` (~27 min for 2 papers incl. per-call cold-start; ≈20–27 s/page). So full 2024-C (11) ≈ **2–2.5 h**; full 455-paper corpus ≈ **~100 h (4+ days)** — NOT overnight. Implications:
- **Subset-first is mandatory.** Convert only the target slice (e.g. recent-year C/D/E/F ≈ 50–80 papers ≈ 12–18 h, spread over nights). Conversions cache by `paper_id` → resumable/incremental.
- **For bulk/full corpus, faster options:** (a) `pipeline` backend (much faster, ~86 vs ~95 accuracy) for bulk + `vlm-engine` for the high-value subset; (b) batch-convert per year-dir in one `mineru` call to amortize the ~1 min/paper server cold-start (LocalMinerUProvider currently invokes mineru once per paper — a worthwhile Plan-2 optimization); (c) a cloud GPU (~10× faster).

**Pending:** real Voyage embed/rerank flip — needs a `VOYAGE` API key in `mcm_agent_config.local.json` (`embedding.provider="voyage"`). PoC scale ≈ a few cents. Pipeline already proven with Fake embeddings; flipping the provider is the only remaining step.
