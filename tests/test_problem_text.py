"""Tests for problem_text.extract_problem_text.

TDD: These tests were written BEFORE the implementation in
src/mcm_agent/core/problem_text.py
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest


REAL_PDF = Path(__file__).parent.parent / "assets" / "diagnostic_2026_mcm_c" / "2026_MCM_Problem_C.pdf"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _problem_dir(ws: Path) -> Path:
    d = ws / "input" / "problem"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# .txt problem → plain read
# ---------------------------------------------------------------------------

def test_extract_problem_text_from_txt(tmp_path: Path) -> None:
    """A plain .txt problem file is read correctly."""
    from mcm_agent.core.problem_text import extract_problem_text

    d = _problem_dir(tmp_path)
    (d / "problem.txt").write_text("DWTS test problem content.", encoding="utf-8")

    result = extract_problem_text(tmp_path)

    assert "DWTS" in result
    assert "test problem content" in result


# ---------------------------------------------------------------------------
# Missing problem → "" and no exception
# ---------------------------------------------------------------------------

def test_extract_problem_text_missing_returns_empty(tmp_path: Path) -> None:
    """When there is no problem file, returns '' and does not raise."""
    from mcm_agent.core.problem_text import extract_problem_text

    result = extract_problem_text(tmp_path)

    assert result == ""


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not REAL_PDF.exists(), reason="Real PDF asset not present")
def test_extract_problem_text_from_pdf(tmp_path: Path) -> None:
    """PDF problem text is extracted and contains known phrases."""
    from mcm_agent.core.problem_text import extract_problem_text

    d = _problem_dir(tmp_path)
    shutil.copy(REAL_PDF, d / "2026_MCM_Problem_C.pdf")

    result = extract_problem_text(tmp_path)

    # The PDF contains "Dancing with the Stars" and "DWTS"
    assert "Dancing with the Stars" in result or "DWTS" in result
    assert len(result) > 100


@pytest.mark.skipif(not REAL_PDF.exists(), reason="Real PDF asset not present")
def test_extract_problem_text_pdf_caches_sidecar(tmp_path: Path) -> None:
    """After extraction a .extracted.txt sidecar is written."""
    from mcm_agent.core.problem_text import extract_problem_text

    d = _problem_dir(tmp_path)
    pdf_path = d / "2026_MCM_Problem_C.pdf"
    shutil.copy(REAL_PDF, pdf_path)

    extract_problem_text(tmp_path)

    sidecar = d / "2026_MCM_Problem_C.extracted.txt"
    assert sidecar.exists(), "Sidecar .extracted.txt should be written after first extraction"
    cached_text = sidecar.read_text(encoding="utf-8")
    assert "DWTS" in cached_text or "Dancing with the Stars" in cached_text


@pytest.mark.skipif(not REAL_PDF.exists(), reason="Real PDF asset not present")
def test_extract_problem_text_pdf_uses_cache_on_second_call(tmp_path: Path) -> None:
    """Second call returns from sidecar without re-parsing the PDF."""
    from mcm_agent.core.problem_text import extract_problem_text

    d = _problem_dir(tmp_path)
    pdf_path = d / "2026_MCM_Problem_C.pdf"
    shutil.copy(REAL_PDF, pdf_path)

    # First call: write cache
    first_result = extract_problem_text(tmp_path)

    # Corrupt the PDF so a second pypdf parse would fail / differ
    pdf_path.write_bytes(b"corrupted")

    # Second call should still return the cached result
    second_result = extract_problem_text(tmp_path)

    assert first_result == second_result


# ---------------------------------------------------------------------------
# Limit is respected
# ---------------------------------------------------------------------------

def test_extract_problem_text_respects_limit(tmp_path: Path) -> None:
    """The returned text is at most `limit` characters."""
    from mcm_agent.core.problem_text import extract_problem_text

    d = _problem_dir(tmp_path)
    long_text = "A" * 10_000
    (d / "problem.txt").write_text(long_text, encoding="utf-8")

    result = extract_problem_text(tmp_path, limit=500)

    assert len(result) <= 500
