from pathlib import Path

from mcm_agent.agents.writer import PaperWriterAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.latex import LatexProvider
from mcm_agent.utils.json_io import write_json


def test_paper_writer_generates_sections_and_main_tex(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "problem_understanding.md").write_text(
        "# 题意理解报告\n", encoding="utf-8"
    )
    (workspace.root / "reports" / "model_decision.md").write_text(
        "# Model Decision\n", encoding="utf-8"
    )
    (workspace.root / "reports" / "validation_report.md").write_text(
        "# Validation Report\n", encoding="utf-8"
    )
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [
            {
                "evidence_id": "metric_row_count",
                "claim": "Metric row_count equals 3.",
                "value": 3,
                "source_type": "code_output",
                "source_path": "results/model_metrics.json",
                "generated_by": "code/problem1.py",
                "used_in": [],
                "verified": True,
            }
        ],
    )
    write_json(workspace.root / "figures" / "figure_registry.json", [])

    PaperWriterAgent().run(workspace.root)

    assert (workspace.root / "paper" / "main.tex").exists()
    assert (workspace.root / "paper" / "sections" / "abstract.tex").exists()
    assert "\\input{sections/abstract}" in (workspace.root / "paper" / "main.tex").read_text(
        encoding="utf-8"
    )


def test_latex_provider_blocked_when_forced_command_missing(tmp_path: Path) -> None:
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text("\\documentclass{article}\\begin{document}x\\end{document}")

    result = LatexProvider(command="definitely-missing-engine").compile(paper_dir)

    assert result.success is False
    assert "definitely-missing-engine" in result.reason
    assert (paper_dir / "compile_log.txt").exists()


def test_latex_provider_blocked_when_no_engine_available(tmp_path: Path, monkeypatch) -> None:
    import mcm_agent.providers.latex as latex_mod

    monkeypatch.setattr(latex_mod.shutil, "which", lambda name: None)
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text("\\documentclass{article}\\begin{document}x\\end{document}")

    result = LatexProvider().compile(paper_dir)

    assert result.success is False
    assert "no latex engine" in result.reason.lower()
    assert (paper_dir / "compile_log.txt").exists()


def test_latex_provider_prefers_tectonic_when_available(tmp_path: Path, monkeypatch) -> None:
    import mcm_agent.providers.latex as latex_mod

    monkeypatch.setattr(latex_mod.shutil, "which", lambda name: f"/usr/bin/{name}" if name == "tectonic" else None)
    provider = LatexProvider()

    assert provider._resolve_command() == "tectonic"
    assert provider._invocation("tectonic") == ["tectonic", "main.tex"]
