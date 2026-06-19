import re
from datetime import UTC, datetime
from pathlib import Path

from mcm_agent.agents.reference_manager import ReferenceManager
from mcm_agent.core.models import CitationCandidate
from mcm_agent.core.workspace import create_workspace


def test_write_bibtex_escapes_latex_specials(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    candidate = CitationCandidate(
        citation_id="c1",
        source_id="web_001",
        title="Fan_Vote & Attachment 100% Guide #1",
        url="https://example.com/a_b",
        accessed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    ReferenceManager()._write_bibtex(root, [candidate])

    bib = (root / "paper" / "references.bib").read_text(encoding="utf-8")
    assert "\\&" in bib
    assert "\\%" in bib
    assert "\\#" in bib
    assert "Fan\\_Vote" in bib  # underscore inside a value is escaped
    # No bare (unescaped) alignment-tab characters remain — they break LaTeX.
    assert not re.search(r"(?<!\\)&", bib)
    # The bibtex key must stay intact (underscore in the KEY is NOT escaped).
    assert "@misc{web_001," in bib
