from pathlib import Path

from mcm_agent.core.latex_compile import compile_with_repair
from mcm_agent.providers.base import ProviderResult
from mcm_agent.providers.latex import LatexCompileResult


class _FlakyLatex:
    """Fails until model.tex contains 'FIXED'."""

    command = "tectonic"

    def __init__(self) -> None:
        self.calls = 0

    def compile(self, paper_dir: Path) -> LatexCompileResult:
        self.calls += 1
        log = paper_dir / "compile_log.txt"
        log.write_text("! Undefined control sequence.\nl.3 \\badcmd", encoding="utf-8")
        model = paper_dir / "sections" / "model.tex"
        ok = model.exists() and "FIXED" in model.read_text(encoding="utf-8")
        return LatexCompileResult(
            success=ok,
            pdf_path=str(paper_dir / "main.pdf") if ok else None,
            log_path=str(log),
            reason="" if ok else "compile failed",
        )


class _FixLLM:
    def generate(self, system: str, prompt: str) -> ProviderResult:
        return ProviderResult(content='{"model.tex": "\\\\section{Model}\\nFIXED body"}', metadata={})


def _make_paper(tmp_path: Path) -> Path:
    paper = tmp_path / "paper"
    (paper / "sections").mkdir(parents=True)
    (paper / "sections" / "model.tex").write_text("\\section{Model}\n\\badcmd", encoding="utf-8")
    (paper / "main.tex").write_text("\\documentclass{article}\\begin{document}x\\end{document}")
    return paper


def test_compile_with_repair_fixes_then_succeeds(tmp_path: Path) -> None:
    paper = _make_paper(tmp_path)
    provider = _FlakyLatex()

    result = compile_with_repair(paper, provider, _FixLLM(), language="en", max_attempts=4)

    assert result.success
    assert "FIXED" in (paper / "sections" / "model.tex").read_text(encoding="utf-8")
    assert provider.calls >= 2  # initial fail + at least one repair recompile


def test_compile_with_repair_no_llm_single_attempt(tmp_path: Path) -> None:
    paper = _make_paper(tmp_path)
    provider = _FlakyLatex()

    result = compile_with_repair(paper, provider, None, language="en")

    assert result.success is False
    assert provider.calls == 1  # no LLM -> no repair loop


def test_compile_with_repair_success_first_try_no_llm_call(tmp_path: Path) -> None:
    paper = _make_paper(tmp_path)
    (paper / "sections" / "model.tex").write_text("\\section{Model}\nFIXED", encoding="utf-8")
    provider = _FlakyLatex()

    calls = {"n": 0}

    class _CountingLLM:
        def generate(self, system: str, prompt: str) -> ProviderResult:
            calls["n"] += 1
            return ProviderResult(content="{}", metadata={})

    result = compile_with_repair(paper, provider, _CountingLLM(), language="en")

    assert result.success
    assert calls["n"] == 0  # already compiles -> LLM never invoked
