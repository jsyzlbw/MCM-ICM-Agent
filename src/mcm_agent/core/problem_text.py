"""Extract problem text from the workspace's input/problem directory.

Supports .txt, .md, and .pdf files. PDF text is cached to a sidecar
.extracted.txt file to avoid re-parsing on every chat turn.
"""
from __future__ import annotations

from pathlib import Path


def extract_problem_text(workspace_root: Path, limit: int = 6000) -> str:
    """Return up to `limit` characters of problem text from input/problem/.

    Strategy:
    1. Look in input/problem/ for any file.
    2. If a sibling .txt or .md file exists (next to a PDF), read it.
    3. If the file itself is a .txt or .md, read it directly.
    4. If the file is a .pdf:
       a. Check for a sidecar <stem>.extracted.txt; if present, return its content.
       b. Extract text with pypdf; fallback to pymupdf/fitz if pypdf yields nothing.
       c. Cache to the sidecar file.
    5. On any failure return "" (never raise).
    """
    try:
        return _extract(workspace_root, limit)
    except Exception:  # noqa: BLE001
        return ""


def _extract(workspace_root: Path, limit: int) -> str:
    problem_dir = workspace_root / "input" / "problem"
    if not problem_dir.exists():
        return ""

    files = sorted(p for p in problem_dir.iterdir() if p.is_file() and not p.name.endswith(".extracted.txt"))
    if not files:
        return ""

    candidate = files[0]

    # Prefer an explicit .txt/.md sibling for any file type
    sibling_txt = candidate.with_suffix(".txt")
    sibling_md = candidate.with_suffix(".md")
    if sibling_txt.exists() and sibling_txt != candidate:
        return sibling_txt.read_text(encoding="utf-8")[:limit]
    if sibling_md.exists() and sibling_md != candidate:
        return sibling_md.read_text(encoding="utf-8")[:limit]

    suffix = candidate.suffix.lower()

    if suffix in (".txt", ".md"):
        return candidate.read_text(encoding="utf-8")[:limit]

    if suffix == ".pdf":
        return _extract_pdf(candidate, limit)

    # Unknown type — try reading as UTF-8 text
    try:
        return candidate.read_text(encoding="utf-8")[:limit]
    except (UnicodeDecodeError, OSError):
        return ""


def _extract_pdf(pdf_path: Path, limit: int) -> str:
    """Extract text from a PDF, using/writing a sidecar cache."""
    sidecar = pdf_path.with_suffix(".extracted.txt")

    # Return from cache if present
    if sidecar.exists():
        try:
            return sidecar.read_text(encoding="utf-8")[:limit]
        except OSError:
            pass

    # Try pypdf first
    text = ""
    try:
        from pypdf import PdfReader  # type: ignore[import]

        reader = PdfReader(str(pdf_path))
        text = "".join(page.extract_text() or "" for page in reader.pages)
    except Exception:  # noqa: BLE001
        text = ""

    # Fallback to pymupdf if pypdf returned nothing
    if not text.strip():
        try:
            import fitz  # type: ignore[import]  # pymupdf

            doc = fitz.open(str(pdf_path))
            text = "".join(page.get_text() for page in doc)
        except Exception:  # noqa: BLE001
            text = ""

    if text:
        # Write sidecar cache (best-effort; never raise)
        try:
            sidecar.write_text(text, encoding="utf-8")
        except OSError:
            pass

    return text[:limit]
