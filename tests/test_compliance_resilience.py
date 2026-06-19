from pathlib import Path

from mcm_agent.agents.compliance import ComplianceOriginalityAgent
from mcm_agent.core.workspace import create_workspace


class _BoomHumanizer:
    def humanize(self, text: str, *, language: str = "en") -> str:
        raise RuntimeError("UShallPass submit failed: 400")


def test_compliance_survives_humanizer_failure(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    section_dir = root / "paper" / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    original = "\\section{Model}\nThe model estimates fan votes from judge scores.\n"
    (section_dir / "model.tex").write_text(original, encoding="utf-8")

    # Must not raise even though the humanizer fails on every paragraph.
    ComplianceOriginalityAgent(_BoomHumanizer()).run(root)

    assert (section_dir / "model.tex").read_text(encoding="utf-8") == original
    report = (root / "review" / "originality_report.md").read_text(encoding="utf-8")
    assert "humaniz" in report.lower()
