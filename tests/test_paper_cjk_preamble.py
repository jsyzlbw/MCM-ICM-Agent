from pathlib import Path

from mcm_agent.agents.writer import PaperWriterAgent
from mcm_agent.core.workspace import create_workspace


def _write_sections(root: Path, text: str) -> None:
    sd = root / "paper" / "sections"
    sd.mkdir(parents=True, exist_ok=True)
    for name in ["abstract", "introduction", "assumptions", "model", "results", "sensitivity", "conclusion"]:
        (sd / f"{name}.tex").write_text(f"\\section{{{name}}}\n{text}\n", encoding="utf-8")


def test_main_tex_uses_ctex_when_cjk_present(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    _write_sections(root, "本文估计粉丝投票。")

    PaperWriterAgent()._write_main_files(root / "paper")

    main = (root / "paper" / "main.tex").read_text(encoding="utf-8")
    assert "ctex" in main


def test_main_tex_plain_when_english_only(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    _write_sections(root, "This paper estimates fan votes.")

    PaperWriterAgent()._write_main_files(root / "paper")

    main = (root / "paper" / "main.tex").read_text(encoding="utf-8")
    assert "ctex" not in main
    assert "\\documentclass[12pt]{article}" in main
