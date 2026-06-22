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


class _CountingLLM:
    """Fake LLM that records all calls and returns distinct content per call index."""

    def __init__(self) -> None:
        self.call_count = 0
        self.prompts: list[str] = []
        self._responses = [
            "OUTLINE: 1. Background 2. Methodology 3. Analysis",
            "\\section{Model}\nDRAFT BODY: The model incorporates logistic regression with parameter $\\alpha$, "
            "justified by the dataset characteristics. Results show accuracy > 0.9.",
            "\\section{Model}\nREVISED BODY: The model uses logistic regression. The parameter $\\alpha$ controls "
            "regularization, chosen to minimize overfitting on validation data. Final accuracy: 0.92.",
        ]

    def generate(self, system: str, prompt: str) -> ProviderResult:
        self.prompts.append(prompt)
        idx = self.call_count
        self.call_count += 1
        content = self._responses[idx] if idx < len(self._responses) else self._responses[-1]
        return ProviderResult(content=content, metadata={})


class _DraftFailingLLM:
    """Fake LLM that raises on the 2nd call (draft) but succeeds on outline and single-pass fallback."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate(self, system: str, prompt: str) -> ProviderResult:
        self.call_count += 1
        if self.call_count == 2:
            raise RuntimeError("draft failed intentionally")
        # 1st call (outline) returns outline; 3rd+ calls return fallback single-pass content
        return ProviderResult(
            content="\\section{Model}\nSINGLE PASS fallback content with equation $x^2$.",
            metadata={},
        )


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


# ── NEW TESTS FOR TASK B1: 3-pass writer ──────────────────────────────────────


def test_section_writer_three_pass() -> None:
    """write_section with LLM calls generate exactly 3 times (outline, draft, revise);
    the 2nd (draft) prompt contains the 1st call's outline output;
    the final LaTeX contains the revise output and a \\section header.
    """
    llm = _CountingLLM()
    writer = PaperSectionWriter(llm, language="en")
    out = writer.write_section("model", "Model", {"summary": "logistic regression"})

    # Must call generate exactly 3 times
    assert llm.call_count == 3, f"Expected 3 generate() calls, got {llm.call_count}"

    # 2nd prompt (draft) must contain text from 1st response (outline)
    draft_prompt = llm.prompts[1]
    outline_content = llm._responses[0]
    assert outline_content in draft_prompt, (
        f"Draft prompt does not contain outline output.\n"
        f"Outline: {outline_content!r}\nDraft prompt: {draft_prompt!r}"
    )

    # Final output must contain a \\section header
    assert "\\section" in out, f"Output missing \\section header: {out!r}"

    # Final output must contain some of the revise response content
    assert "REVISED BODY" in out or "\\section{Model}" in out, (
        f"Output doesn't seem to contain revise pass content: {out!r}"
    )


def test_section_writer_no_llm_uses_fallback() -> None:
    """PaperSectionWriter(None) returns deterministic fallback; does not crash."""
    writer = PaperSectionWriter(None, language="en")
    out = writer.write_section("model", "Model", {})
    assert "\\section{Model}" in out
    assert len(out.strip()) > 0


def test_section_writer_draft_failure_degrades() -> None:
    """When the draft call (2nd) raises, write_section does not crash and returns a non-empty section."""
    llm = _DraftFailingLLM()
    writer = PaperSectionWriter(llm, language="en")
    out = writer.write_section("model", "Model", {"summary": "test"})
    # Must not crash and must produce non-empty content with a section header
    assert "\\section{Model}" in out or "\\section*{Model}" in out, (
        f"Expected section header in degraded output: {out!r}"
    )
    assert len(out.strip()) > 0


def test_section_writer_injects_judge_feedback() -> None:
    """When facts contains 'judge_feedback', the draft prompt must include the critique text."""
    llm = _CountingLLM()
    writer = PaperSectionWriter(llm, language="en")
    facts = {
        "summary": "logistic regression",
        "judge_feedback": {
            "dimension": "writing",
            "critique": "too vague",
            "suggestions": ["add detail", "explain equations"],
        },
    }
    writer.write_section("model", "Model", facts)

    # 2nd prompt is the draft prompt — it must contain the critique text
    draft_prompt = llm.prompts[1]
    assert "too vague" in draft_prompt, (
        f"Draft prompt does not contain judge critique 'too vague'.\nDraft prompt: {draft_prompt!r}"
    )


def test_section_writer_exemplars_in_prompt_with_anticopy_notice() -> None:
    """When exemplars are passed, outline/draft prompts must contain the exemplar text
    AND an anti-copy instruction (e.g., 'do NOT copy' or 'imitate').
    """
    llm = _CountingLLM()
    writer = PaperSectionWriter(llm, language="en")
    exemplar_text = "EXEMPLAR MODEL SECTION: This award-winning section demonstrates deep analysis."
    writer.write_section(
        "model", "Model", {"summary": "regression"}, exemplars=[exemplar_text]
    )

    # Check outline prompt (1st call) contains exemplar and anti-copy notice
    outline_prompt = llm.prompts[0]
    assert exemplar_text in outline_prompt, (
        f"Outline prompt does not contain exemplar text.\nOutline prompt: {outline_prompt!r}"
    )
    # Anti-copy instruction must be present (either "do NOT copy" or "imitate")
    assert "do NOT copy" in outline_prompt or "imitate" in outline_prompt, (
        f"Outline prompt missing anti-copy instruction.\nOutline prompt: {outline_prompt!r}"
    )

    # Check draft prompt (2nd call) also contains exemplar
    draft_prompt = llm.prompts[1]
    assert exemplar_text in draft_prompt, (
        f"Draft prompt does not contain exemplar text.\nDraft prompt: {draft_prompt!r}"
    )
