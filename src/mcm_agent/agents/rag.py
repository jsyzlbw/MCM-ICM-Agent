from __future__ import annotations

import sqlite3
from pathlib import Path

from pydantic import BaseModel

from mcm_agent.utils.json_io import write_json


class MethodologyHit(BaseModel):
    source: str
    title: str
    content: str
    rank: int
    query: str = ""
    source_type: str = "method_note"
    relative_path: str = ""
    usage: str = "Use as methodology guidance only; do not cite as external factual data."
    chunk_id: str = ""
    chunk_index: int = 1
    page_hint: str = ""


EXPECTED_DOC_COLUMNS = [
    "source",
    "title",
    "content",
    "source_type",
    "relative_path",
    "usage",
    "chunk_id",
    "chunk_index",
    "page_hint",
]


class MethodologyStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            table_exists = conn.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table' AND name = 'methodology_docs'
                """
            ).fetchone()
            if table_exists:
                columns = [
                    row[1]
                    for row in conn.execute("PRAGMA table_info(methodology_docs)").fetchall()
                ]
                if columns != EXPECTED_DOC_COLUMNS:
                    conn.execute("DROP TABLE methodology_docs")
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS methodology_docs
                USING fts5(
                    source,
                    title,
                    content,
                    source_type,
                    relative_path,
                    usage,
                    chunk_id,
                    chunk_index,
                    page_hint
                )
                """
            )

    def add_document(
        self,
        source: str,
        title: str,
        content: str,
        *,
        source_type: str = "method_note",
        relative_path: str = "",
        usage: str | None = None,
        chunk_id: str = "",
        chunk_index: int = 1,
        page_hint: str = "",
    ) -> None:
        relative_path = relative_path or Path(source).name or source
        usage = usage or usage_restriction(source_type)
        chunk_id = chunk_id or f"{relative_path}#chunk-{chunk_index:03d}"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO methodology_docs(
                    source,
                    title,
                    content,
                    source_type,
                    relative_path,
                    usage,
                    chunk_id,
                    chunk_index,
                    page_hint
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    title,
                    content,
                    source_type,
                    relative_path,
                    usage,
                    chunk_id,
                    chunk_index,
                    page_hint,
                ),
            )

    def search(self, query: str, limit: int = 5) -> list[MethodologyHit]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    source,
                    title,
                    content,
                    source_type,
                    relative_path,
                    usage,
                    chunk_id,
                    chunk_index,
                    page_hint
                FROM methodology_docs
                WHERE methodology_docs MATCH ?
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        return [
            MethodologyHit(
                source=row[0],
                title=row[1],
                content=row[2],
                rank=index,
                source_type=row[3],
                relative_path=row[4],
                usage=row[5],
                chunk_id=row[6],
                chunk_index=_int_or_default(row[7], 1),
                page_hint=row[8],
            )
            for index, row in enumerate(rows, 1)
        ]


PATTERNS = [
    "**/idea-evaluator*/SKILL.md",
    "**/figure-designer*/SKILL.md",
    "**/pre-submission-reviewer*/SKILL.md",
    "**/intro-drafter*/SKILL.md",
    "**/tech-paper-template*/SKILL.md",
]

PAPER_QUALITY_QUERIES = [
    "assumption writing",
    "model formulation",
    "limitation discussion",
    "figure design",
    "pre submission review",
]


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
        "contest_rule": (
            "Use as contest or formatting guidance only; do not cite as external factual data."
        ),
        "paper_example": (
            "Use as writing and modeling pattern guidance only; do not copy claims or cite as "
            "external factual data."
        ),
        "checklist": "Use as internal review guidance only; do not cite as external factual data.",
        "method_note": "Use as methodology guidance only; do not cite as external factual data.",
        "supervisor_skill": (
            "Use as internal agent methodology guidance only; do not cite as external factual data."
        ),
    }
    return restrictions.get(source_type, restrictions["method_note"])


def _int_or_default(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def chunk_text(content: str, *, max_chars: int = 2400) -> list[str]:
    normalized = content.strip()
    if not normalized:
        return []
    paragraphs = [block.strip() for block in normalized.split("\n\n") if block.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(
                paragraph[start : start + max_chars]
                for start in range(0, len(paragraph), max_chars)
            )
            continue
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = paragraph

    if current:
        chunks.append(current)
    return chunks


def _add_chunked_document(
    store: MethodologyStore,
    *,
    source: Path,
    title: str,
    content: str,
    source_type: str,
    relative_path: str,
    page_hint: str = "",
) -> int:
    chunks = chunk_text(content)
    usage = usage_restriction(source_type)
    for index, chunk in enumerate(chunks, 1):
        store.add_document(
            source=str(source),
            title=title,
            content=chunk,
            source_type=source_type,
            relative_path=relative_path,
            usage=usage,
            chunk_id=f"{relative_path}#chunk-{index:03d}",
            chunk_index=index,
            page_hint=page_hint,
        )
    return len(chunks)


def ingest_knowledge_base(
    knowledge_base_dir: Path,
    store: MethodologyStore,
    ingest_extensions: list[str] | None = None,
) -> list[str]:
    notes: list[str] = []
    allowed_extensions = {
        suffix if suffix.startswith(".") else f".{suffix}"
        for suffix in (ingest_extensions or [".md", ".txt", ".pdf"])
    }
    knowledge_base_dir.mkdir(parents=True, exist_ok=True)
    ingested_count = 0

    for path in sorted(item for item in knowledge_base_dir.rglob("*") if item.is_file()):
        relative_path = path.relative_to(knowledge_base_dir).as_posix()
        suffix = path.suffix.lower()
        if suffix not in allowed_extensions:
            notes.append(f"Skipped unsupported knowledge-base file: {relative_path}")
            continue
        if suffix == ".pdf":
            notes.append(f"Pending PDF ingestion via MinerU: {relative_path}")
            continue
        if suffix in {".md", ".txt"}:
            source_type = infer_source_type(relative_path)
            ingested_chunks = _add_chunked_document(
                store,
                source=str(path),
                title=path.name,
                content=path.read_text(encoding="utf-8"),
                source_type=source_type,
                relative_path=relative_path,
            )
            ingested_count += ingested_chunks
            notes.append(f"Ingested user knowledge-base document: {relative_path}")
            continue
        notes.append(f"Skipped unsupported knowledge-base file: {relative_path}")

    if ingested_count == 0 and not any(note.startswith("Pending PDF") for note in notes):
        notes.append("No user knowledge-base documents were ingested.")
    return notes


def import_supervisor_skills(source_dir: Path, store: MethodologyStore) -> list[str]:
    warnings: list[str] = []
    for pattern in PATTERNS:
        matches = sorted(source_dir.glob(pattern))
        if not matches:
            warnings.append(f"Missing methodology source: {pattern}")
            continue
        for path in matches:
            relative_path = path.relative_to(source_dir).as_posix()
            _add_chunked_document(
                store,
                source=str(path),
                title=path.parent.name,
                content=path.read_text(encoding="utf-8"),
                source_type="supervisor_skill",
                relative_path=relative_path,
            )
    return warnings


def search_methodology_queries(
    store: MethodologyStore,
    queries: list[str],
) -> list[MethodologyHit]:
    hits: list[MethodologyHit] = []
    for query in queries:
        for hit in store.search(query, limit=3):
            hits.append(hit.model_copy(update={"query": query}))
    return hits


class MethodologyRAGAgent:
    def run(
        self,
        workspace_root: Path,
        supervisor_skills_dir: Path | None,
        knowledge_base_dir: Path | None = None,
        ingest_extensions: list[str] | None = None,
    ) -> None:
        rag_dir = workspace_root / "rag"
        checklist_dir = rag_dir / "review_checklists"
        checklist_dir.mkdir(parents=True, exist_ok=True)
        store = MethodologyStore(rag_dir / "methodology.db")
        store.initialize()

        warnings: list[str] = []
        if supervisor_skills_dir is not None:
            warnings = import_supervisor_skills(supervisor_skills_dir, store)
        if knowledge_base_dir is not None:
            warnings.extend(ingest_knowledge_base(knowledge_base_dir, store, ingest_extensions))

        hits = search_methodology_queries(store, PAPER_QUALITY_QUERIES)
        write_json(rag_dir / "methodology_hits.json", [hit.model_dump() for hit in hits])

        notes = ["# RAG Retrieval Notes", ""]
        notes.extend(f"- {warning}" for warning in warnings)
        (rag_dir / "retrieval_notes.md").write_text("\n".join(notes) + "\n", encoding="utf-8")

        (checklist_dir / "modeling_checklist.md").write_text(
            "\n".join(
                [
                    "# Modeling Checklist",
                    "",
                    "- Check problem fit.",
                    "- Check data feasibility.",
                    "- Check implementation risk.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (checklist_dir / "figure_checklist.md").write_text(
            "\n".join(
                [
                    "# Figure Checklist",
                    "",
                    "- Every data figure must have a data source.",
                    "- Every concept figure must be vector-first.",
                    "- Every result figure must support a paper claim.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (checklist_dir / "pre_submission_checklist.md").write_text(
            "\n".join(
                [
                    "# Pre Submission Checklist",
                    "",
                    "- Check macro logic.",
                    "- Check writing details.",
                    "- Check English expression.",
                    "- Check LaTeX formatting.",
                    "- Check figure quality.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
