from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class ConvertResult(BaseModel):
    paper_id: str
    markdown_path: str
    converted: bool  # True if freshly parsed, False if served from cache


def convert_entry(
    paper_id: str, pdf_path: Path, kb_dir: Path, mineru_provider: object
) -> ConvertResult:
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
