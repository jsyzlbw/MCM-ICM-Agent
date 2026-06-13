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


class MethodologyStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS methodology_docs
                USING fts5(source, title, content)
                """
            )

    def add_document(self, source: str, title: str, content: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO methodology_docs(source, title, content) VALUES (?, ?, ?)",
                (source, title, content),
            )

    def search(self, query: str, limit: int = 5) -> list[MethodologyHit]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT source, title, content
                FROM methodology_docs
                WHERE methodology_docs MATCH ?
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        return [
            MethodologyHit(source=row[0], title=row[1], content=row[2], rank=index)
            for index, row in enumerate(rows, 1)
        ]


PATTERNS = [
    "**/idea-evaluator*/SKILL.md",
    "**/figure-designer*/SKILL.md",
    "**/pre-submission-reviewer*/SKILL.md",
    "**/intro-drafter*/SKILL.md",
    "**/tech-paper-template*/SKILL.md",
]


def import_supervisor_skills(source_dir: Path, store: MethodologyStore) -> list[str]:
    warnings: list[str] = []
    for pattern in PATTERNS:
        matches = sorted(source_dir.glob(pattern))
        if not matches:
            warnings.append(f"Missing methodology source: {pattern}")
            continue
        for path in matches:
            store.add_document(
                source=str(path),
                title=path.parent.name,
                content=path.read_text(encoding="utf-8"),
            )
    return warnings


class MethodologyRAGAgent:
    def run(self, workspace_root: Path, supervisor_skills_dir: Path | None) -> None:
        rag_dir = workspace_root / "rag"
        checklist_dir = rag_dir / "review_checklists"
        checklist_dir.mkdir(parents=True, exist_ok=True)
        store = MethodologyStore(rag_dir / "methodology.db")
        store.initialize()

        warnings: list[str] = []
        if supervisor_skills_dir is not None:
            warnings = import_supervisor_skills(supervisor_skills_dir, store)

        hits = store.search("figure design", limit=5)
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
