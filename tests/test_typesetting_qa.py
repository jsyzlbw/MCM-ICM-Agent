from pathlib import Path

from mcm_agent.agents.typesetting_qa import TypesettingQAAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json, write_json


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


def test_typesetting_repair_agent_wraps_wide_tables_and_scales_graphics(
    tmp_path: Path,
) -> None:
    from mcm_agent.agents.typesetting_repair import TypesettingRepairAgent

    workspace = create_workspace(tmp_path / "run_001")
    paper = workspace.root / "paper"
    paper.mkdir(exist_ok=True)
    (paper / "main.tex").write_text(
        "\\begin{document}\n"
        "\\includegraphics{figures/missing.png}\n"
        "\\begin{tabular}{llllllllllll}\n"
        "a & b & c & d & e & f & g & h & i & j & k & l\\\\\n"
        "\\end{tabular}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "review" / "typesetting_quality.json",
        {
            "status": "fail",
            "issue_types": ["table_overflow_risk", "figure_file_missing"],
            "blocking_findings": [
                "Wide table has 12 declared columns.",
                "Included figure file is missing: figures/missing.png",
            ],
            "repair_stage": "typesetting",
            "issues": [],
        },
    )

    report = TypesettingRepairAgent().run(workspace.root)

    tex = (paper / "main.tex").read_text(encoding="utf-8")
    assert report.status == "repaired"
    assert "\\resizebox{\\textwidth}{!}{%" in tex
    assert "\\includegraphics[width=0.9\\linewidth]{figures/missing.png}" in tex
    assert (workspace.root / "review" / "typesetting_repair_report.md").exists()


def test_typesetting_repair_agent_wraps_long_equations(tmp_path: Path) -> None:
    from mcm_agent.agents.typesetting_repair import TypesettingRepairAgent

    workspace = create_workspace(tmp_path / "run_001")
    paper = workspace.root / "paper"
    paper.mkdir(exist_ok=True)
    long_rhs = " + ".join(f"x_{{{index}}}" for index in range(30))
    (paper / "main.tex").write_text(
        "\\begin{document}\n"
        "\\begin{equation}\n"
        f"y = {long_rhs}\n"
        "\\end{equation}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "review" / "typesetting_quality.json",
        {
            "status": "fail",
            "issue_types": ["equation_overflow_risk"],
            "blocking_findings": ["Long display equation may overflow the page width."],
            "repair_stage": "paper_writer",
            "issues": [],
        },
    )

    TypesettingRepairAgent().run(workspace.root)

    tex = (paper / "main.tex").read_text(encoding="utf-8")
    assert "\\begin{split}" in tex
    assert "\\end{split}" in tex


def test_typesetting_repair_agent_reports_no_action_for_clean_quality(
    tmp_path: Path,
) -> None:
    from mcm_agent.agents.typesetting_repair import TypesettingRepairAgent

    workspace = create_workspace(tmp_path / "run_001")
    paper = workspace.root / "paper"
    paper.mkdir(exist_ok=True)
    (paper / "main.tex").write_text(
        "\\begin{document}Short.\\end{document}\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "review" / "typesetting_quality.json",
        {
            "status": "pass",
            "issue_types": [],
            "blocking_findings": [],
            "repair_stage": None,
        },
    )

    report = TypesettingRepairAgent().run(workspace.root)

    assert report.status == "skipped"
    repair_json = read_json(workspace.root / "review" / "typesetting_repair.json", {})
    assert repair_json["status"] == "skipped"


def test_typesetting_qa_report_mentions_repair_status(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    paper = workspace.root / "paper"
    paper.mkdir(exist_ok=True)
    (paper / "main.tex").write_text(
        "\\begin{document}\nShort.\\end{document}\n",
        encoding="utf-8",
    )
    (paper / "main.pdf").write_bytes(b"%PDF")
    (paper / "compile_log.txt").write_text(
        "Latexmk: All targets are up-to-date\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "review" / "typesetting_repair.json",
        {
            "status": "repaired",
            "actions": [
                {
                    "action_type": "scale_graphics",
                    "message": "Scaled graphics.",
                    "changed": True,
                }
            ],
        },
    )

    TypesettingQAAgent().run(workspace.root)

    markdown = (workspace.root / "review" / "typesetting_quality_report.md").read_text(
        encoding="utf-8"
    )
    assert "Repair status: repaired" in markdown
    assert "Scaled graphics." in markdown
