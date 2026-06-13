from pathlib import Path

from mcm_agent.agents.compliance import ComplianceOriginalityAgent
from mcm_agent.providers.humanizer import FakeHumanizerProvider
from mcm_agent.utils.text_locks import extract_fact_locks


def test_extract_fact_locks_captures_numbers_citations_and_refs() -> None:
    locks = extract_fact_locks(
        "RMSE is 2.31 in Figure~\\ref{fig:q1} with \\cite{smith2024} and $y=x+1$."
    )

    assert "2.31" in locks.numbers
    assert "\\cite{smith2024}" in locks.citations
    assert "Figure~\\ref{fig:q1}" in locks.figure_refs
    assert "$y=x+1$" in locks.equations


def test_compliance_agent_rejects_humanized_paragraph_when_number_changes(tmp_path: Path) -> None:
    section_dir = tmp_path / "paper" / "sections"
    section_dir.mkdir(parents=True)
    (section_dir / "results.tex").write_text(
        "The model achieves RMSE 2.31 on the validation set.\n",
        encoding="utf-8",
    )
    (tmp_path / "review").mkdir()
    (tmp_path / "unresolved_issues.md").write_text("# Unresolved Issues\n", encoding="utf-8")

    provider = FakeHumanizerProvider(
        {"The model achieves RMSE 2.31 on the validation set.": "The model reaches RMSE 2.13 on validation."}
    )
    ComplianceOriginalityAgent(provider).run(tmp_path)

    content = (section_dir / "results.tex").read_text(encoding="utf-8")
    report = (tmp_path / "review" / "fact_regression_report.md").read_text(encoding="utf-8")
    assert "2.31" in content
    assert "critical" in report


def test_compliance_agent_accepts_safe_humanized_paragraph(tmp_path: Path) -> None:
    section_dir = tmp_path / "paper" / "sections"
    section_dir.mkdir(parents=True)
    (section_dir / "results.tex").write_text(
        "The model gives a stable qualitative pattern.\n",
        encoding="utf-8",
    )
    (tmp_path / "review").mkdir()
    (tmp_path / "unresolved_issues.md").write_text("# Unresolved Issues\n", encoding="utf-8")

    provider = FakeHumanizerProvider(
        {"The model gives a stable qualitative pattern.": "The model shows a stable qualitative pattern."}
    )
    ComplianceOriginalityAgent(provider).run(tmp_path)

    content = (section_dir / "results.tex").read_text(encoding="utf-8")
    assert "shows a stable" in content
