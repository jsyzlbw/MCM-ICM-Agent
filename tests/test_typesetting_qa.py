from pathlib import Path

from mcm_agent.agents.typesetting_qa import TypesettingQAAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json


def test_typesetting_qa_flags_compile_error_and_overflow(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    paper = workspace.root / "paper"
    paper.mkdir(exist_ok=True)
    (paper / "main.tex").write_text(
        "\\begin{document}\n"
        "\\begin{tabular}{llllllllllll}\n"
        "a & b & c & d & e & f & g & h & i & j & k & l\\\\\n"
        "\\end{tabular}\n"
        "\\begin{equation}\n"
        "x = "
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "\\end{equation}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    (paper / "compile_log.txt").write_text(
        "! Undefined control sequence.\nOverfull \\hbox\n",
        encoding="utf-8",
    )

    TypesettingQAAgent().run(workspace.root)

    report = read_json(workspace.root / "review" / "typesetting_quality.json", {})
    assert report["status"] == "fail"
    assert "compile_error" in report["issue_types"]
    assert "table_overflow_risk" in report["issue_types"]
    assert "equation_overflow_risk" in report["issue_types"]
    markdown = (workspace.root / "review" / "typesetting_quality_report.md").read_text(
        encoding="utf-8"
    )
    assert "Undefined control sequence" in markdown


def test_typesetting_qa_passes_clean_short_paper(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    paper = workspace.root / "paper"
    paper.mkdir(exist_ok=True)
    (paper / "main.tex").write_text(
        "\\begin{document}\nShort paper.\n\\end{document}\n",
        encoding="utf-8",
    )
    (paper / "main.pdf").write_bytes(b"%PDF")
    (paper / "compile_log.txt").write_text(
        "Latexmk: All targets are up-to-date\n",
        encoding="utf-8",
    )

    TypesettingQAAgent().run(workspace.root)

    report = read_json(workspace.root / "review" / "typesetting_quality.json", {})
    assert report["status"] == "pass"
    assert report["blocking_findings"] == []


def test_typesetting_qa_does_not_block_when_latex_tool_is_unavailable(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    paper = workspace.root / "paper"
    paper.mkdir(exist_ok=True)
    (paper / "main.tex").write_text(
        "\\begin{document}\nShort paper.\n\\end{document}\n",
        encoding="utf-8",
    )
    (paper / "compile_log.txt").write_text("latexmk not installed\n", encoding="utf-8")
    (workspace.root / "review" / "typesetting_report.md").write_text(
        "# Typesetting Report\n\n"
        "- Success: False\n"
        "- PDF: `missing`\n"
        "- Reason: latexmk not installed\n",
        encoding="utf-8",
    )

    TypesettingQAAgent().run(workspace.root)

    report = read_json(workspace.root / "review" / "typesetting_quality.json", {})
    assert report["status"] == "pass"
    assert "latex_tool_unavailable" in report["issue_types"]
    assert report["blocking_findings"] == []
