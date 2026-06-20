from mcm_agent.agents.section_writer import PaperSectionWriter
from mcm_agent.providers.base import ProviderResult


class _MarkdownLLM:
    def __init__(self) -> None:
        self.last_system = ""

    def generate(self, system: str, prompt: str) -> ProviderResult:
        self.last_system = system
        return ProviderResult(
            content="\\section{Model}\n**M1:** logistic regression with $\\alpha$.",
            metadata={},
        )


class _RaisingLLM:
    def generate(self, system: str, prompt: str) -> ProviderResult:
        raise TimeoutError("boom")


def test_section_writer_cleans_markdown_keeps_section() -> None:
    writer = PaperSectionWriter(_MarkdownLLM(), language="en")
    out = writer.write_section("model", "Model", {"summary": "logistic regression"})
    assert "\\section{Model}" in out
    assert "**" not in out
    assert "\\textbf{M1:}" in out


def test_section_writer_fallback_without_llm() -> None:
    en = PaperSectionWriter(None, language="en").write_section("introduction", "Introduction", {})
    zh = PaperSectionWriter(None, language="zh").write_section("introduction", "引言", {})
    assert "\\section{Introduction}" in en
    assert "\\section{引言}" in zh


def test_section_writer_fallback_on_llm_error() -> None:
    out = PaperSectionWriter(_RaisingLLM(), language="en").write_section("model", "Model", {})
    assert "\\section{Model}" in out  # error -> deterministic fallback, no crash


def test_section_writer_abstract_is_starred() -> None:
    out = PaperSectionWriter(None, language="en").write_section("abstract", "Abstract", {})
    assert "\\section*{Abstract}" in out


def test_section_writer_zh_system_prompt() -> None:
    llm = _MarkdownLLM()
    PaperSectionWriter(llm, language="zh").write_section("model", "模型", {"summary": "x"})
    assert "中文" in llm.last_system
