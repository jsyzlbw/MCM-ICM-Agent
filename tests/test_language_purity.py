"""
PQ5: Language-purity tests for reviewer fallback, paper_sections fallback,
and the off-language lint in TypesettingQAAgent.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mcm_agent.agents.paper_context import PaperContext
from mcm_agent.agents.paper_sections import _render_introduction, render_claim_plan_sections
from mcm_agent.agents.reviewer import ReviewerAgent
from mcm_agent.agents.typesetting_qa import TypesettingQAAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import write_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_reviewer(language: str) -> tuple[ReviewerAgent, Path]:
    """Return a ReviewerAgent preconfigured with a workspace whose direction
    lock specifies *language*."""
    return ReviewerAgent(), language


# ---------------------------------------------------------------------------
# 1. ReviewerAgent – _fallback_review is language-aware
# ---------------------------------------------------------------------------

class TestReviewerFallbackLanguagePurity:
    """_fallback_review must emit only the target language."""

    def test_zh_fallback_has_no_english_boilerplate(self) -> None:
        agent = ReviewerAgent()
        report = agent._fallback_review([], language="zh")
        # Must NOT contain English boilerplate sentences
        assert "Pass with comments." not in report
        assert "The workflow records evidence" not in report
        assert "Review all generated sections before submission." not in report
        assert "Missing deep domain-specific modeling" not in report
        assert "Improve model-specific explanation" not in report
        # Must contain Chinese heading
        assert "自动评审报告" in report

    def test_en_fallback_has_no_chinese_headings(self) -> None:
        agent = ReviewerAgent()
        report = agent._fallback_review([], language="en")
        # Must NOT contain Chinese headings
        assert "总体评分" not in report
        assert "主要优点" not in report
        assert "高风险问题" not in report
        assert "修改建议" not in report
        # Must contain English heading
        assert "Automatic Review Report" in report

    def test_zh_fallback_blocked_case(self) -> None:
        agent = ReviewerAgent()
        report = agent._fallback_review(["Critical finding."], language="zh")
        assert "Critical finding." in report
        assert "Pass with comments." not in report

    def test_en_fallback_pass_case(self) -> None:
        agent = ReviewerAgent()
        report = agent._fallback_review([], language="en")
        assert "Pass" in report or "pass" in report.lower()

    def test_default_language_is_en(self) -> None:
        """Calling without language= kwarg must not raise and defaults to en."""
        agent = ReviewerAgent()
        # Should not raise even with old callers that pass no language
        report = agent._fallback_review([])
        assert "Automatic Review Report" in report


# ---------------------------------------------------------------------------
# 2. ReviewerAgent – _generate_review prompt uses correct headings
# ---------------------------------------------------------------------------

class TestReviewerGenerateLanguagePurity:
    """_generate_review must request/validate headings in the correct language."""

    def _fake_provider(self, content: str):
        provider = MagicMock()
        result = MagicMock()
        result.content = content
        provider.generate.return_value = result
        return provider

    def test_zh_generate_validates_zh_headings(self) -> None:
        agent = ReviewerAgent(
            llm_provider=self._fake_provider(
                "# 自动评审报告\n## 总体评分\n## 高风险问题\n## 修改建议\n"
            )
        )
        result = agent._generate_review([], language="zh")
        assert result is not None
        assert "自动评审报告" in result

    def test_en_generate_validates_en_headings(self) -> None:
        agent = ReviewerAgent(
            llm_provider=self._fake_provider(
                "# Automatic Review Report\n## Overall Score\n"
                "## High-Risk Issues\n## Revision Suggestions\n"
            )
        )
        result = agent._generate_review([], language="en")
        assert result is not None
        assert "Automatic Review Report" in result

    def test_zh_generate_rejects_en_headings(self) -> None:
        """If the LLM returns English headings for a zh paper, it must return None."""
        agent = ReviewerAgent(
            llm_provider=self._fake_provider(
                "# Automatic Review Report\n## Overall Score\n"
                "## High-Risk Issues\n## Revision Suggestions\n"
            )
        )
        result = agent._generate_review([], language="zh")
        assert result is None

    def test_en_generate_rejects_zh_headings(self) -> None:
        """If the LLM returns Chinese headings for an en paper, it must return None."""
        agent = ReviewerAgent(
            llm_provider=self._fake_provider(
                "# 自动评审报告\n## 总体评分\n## 高风险问题\n## 修改建议\n"
            )
        )
        result = agent._generate_review([], language="en")
        assert result is None


# ---------------------------------------------------------------------------
# 3. paper_sections – _render_introduction fallback is language-aware
# ---------------------------------------------------------------------------

class TestPaperSectionsFallbackLanguagePurity:
    """Fallback sentences in paper_sections must match the paper language."""

    def test_zh_introduction_fallback_uses_chinese(self) -> None:
        ctx = PaperContext(language="zh")  # no problem_summary → hits fallback
        tex = _render_introduction(ctx)
        # Must contain at least one Chinese fallback sentence
        assert "我们" in tex or "问题" in tex or "建模" in tex

    def test_en_introduction_fallback_uses_english(self) -> None:
        ctx = PaperContext(language="en")
        tex = _render_introduction(ctx)
        # Must NOT start with Chinese
        import re
        cjk_pattern = re.compile(r'[一-鿿]')
        assert not cjk_pattern.search(tex), f"Chinese found in en fallback: {tex!r}"

    def test_zh_introduction_with_summary_passes_through(self) -> None:
        ctx = PaperContext(problem_summary="分析DWTS投票公平性", language="zh")
        tex = _render_introduction(ctx)
        assert "DWTS" in tex

    def test_render_claim_plan_sections_introduction_zh(self) -> None:
        """render_claim_plan_sections introduction fallback for zh paper."""
        ctx = PaperContext(language="zh")
        sections = render_claim_plan_sections([], ctx, None)
        intro = sections["introduction.tex"]
        # Must not have the English-only hardcoded fallback
        assert "The problem is decomposed into data, model" not in intro
        assert "The remainder of the paper follows" not in intro

    def test_render_claim_plan_sections_introduction_en(self) -> None:
        """render_claim_plan_sections introduction fallback for en paper is English."""
        ctx = PaperContext(language="en")
        sections = render_claim_plan_sections([], ctx, None)
        intro = sections["introduction.tex"]
        # Must have English content, no Chinese
        import re
        cjk_pattern = re.compile(r'[一-鿿]')
        assert not cjk_pattern.search(intro), f"Chinese found in en intro: {intro!r}"


# ---------------------------------------------------------------------------
# 4. TypesettingQAAgent – off-language lint
# ---------------------------------------------------------------------------

def _make_qa_workspace(tmp_path: Path, language: str, tex_body: str) -> Path:
    workspace = create_workspace(tmp_path)
    paper = workspace.root / "paper"
    paper.mkdir(exist_ok=True)
    (paper / "main.tex").write_text(tex_body, encoding="utf-8")
    # Write direction lock with language
    (workspace.root / "discussion").mkdir(exist_ok=True)
    write_json(
        workspace.root / "discussion" / "direction_lock.json",
        {"language": language, "status": "locked", "selected_route": "llm_generated"},
    )
    return workspace.root


class TestTypesettingQALanguageLint:
    """TypesettingQAAgent must flag sentence-level off-language content."""

    def test_zh_paper_with_english_paragraph_is_flagged(self, tmp_path: Path) -> None:
        """A zh paper whose section is an entire English paragraph must be blocked."""
        tex = (
            "\\begin{document}\n"
            "\\section{Introduction}\n"
            "This study examines the fairness of the DWTS voting system using a "
            "statistical model. We apply regression analysis and find that the "
            "results are statistically significant at the 0.05 level.\n"
            "\\end{document}\n"
        )
        workspace = _make_qa_workspace(tmp_path / "zh_en", "zh", tex)
        report = TypesettingQAAgent().run(workspace)
        assert report.status == "fail"
        assert any("off_language" in ft or "language" in ft for ft in report.issue_types)
        blocking_text = " ".join(report.blocking_findings)
        assert "language" in blocking_text.lower() or "off" in blocking_text.lower()
        # repair_stage must route to paper_writer
        assert report.repair_stage == "paper_writer"

    def test_zh_paper_with_only_acronyms_is_not_flagged(self, tmp_path: Path) -> None:
        """A zh paper with Chinese prose + only acronyms (SVM, AUC) must NOT be flagged."""
        tex = (
            "\\begin{document}\n"
            "\\section{引言}\n"
            "本文采用SVM和AUC指标评估模型性能。实验结果表明，该方法在F1分数上"
            "优于基线方法。所有实验均使用Python 3.11完成。\n"
            "\\end{document}\n"
        )
        workspace = _make_qa_workspace(tmp_path / "zh_ok", "zh", tex)
        report = TypesettingQAAgent().run(workspace)
        # off-language lint must not block on acronyms
        assert not any("off_language" in ft or "language_purity" in ft for ft in report.issue_types)

    def test_en_paper_with_cjk_prose_is_flagged(self, tmp_path: Path) -> None:
        """An en paper whose section contains CJK prose must be flagged."""
        tex = (
            "\\begin{document}\n"
            "\\section{Introduction}\n"
            "本文采用统计模型分析投票公平性问题。我们发现结果具有统计显著性。\n"
            "\\end{document}\n"
        )
        workspace = _make_qa_workspace(tmp_path / "en_zh", "en", tex)
        report = TypesettingQAAgent().run(workspace)
        assert report.status == "fail"
        assert any("off_language" in ft or "language" in ft for ft in report.issue_types)
        assert report.repair_stage == "paper_writer"

    def test_en_paper_clean_is_not_flagged(self, tmp_path: Path) -> None:
        """A clean English paper must not trigger the off-language lint."""
        tex = (
            "\\begin{document}\n"
            "\\section{Introduction}\n"
            "This paper develops a statistical model for the problem.\n"
            "\\end{document}\n"
        )
        workspace = _make_qa_workspace(tmp_path / "en_ok", "en", tex)
        (workspace / "paper" / "main.pdf").write_bytes(b"%PDF")
        (workspace / "paper" / "compile_log.txt").write_text(
            "Latexmk: All targets are up-to-date\n", encoding="utf-8"
        )
        report = TypesettingQAAgent().run(workspace)
        assert not any("off_language" in ft or "language_purity" in ft for ft in report.issue_types)

    def test_zh_paper_with_latex_commands_not_flagged(self, tmp_path: Path) -> None:
        """LaTeX commands and math in a zh paper must not be treated as English prose."""
        tex = (
            "\\begin{document}\n"
            "\\section{模型}\n"
            "设 $x \\in \\mathbb{R}^n$，目标函数为 $\\min_{x} f(x)$。\n"
            "\\begin{equation}\n"
            "f(x) = \\sum_{i=1}^{n} w_i x_i\n"
            "\\end{equation}\n"
            "实验结果如 Table~\\ref{tab:results} 所示。\n"
            "\\end{document}\n"
        )
        workspace = _make_qa_workspace(tmp_path / "zh_math", "zh", tex)
        report = TypesettingQAAgent().run(workspace)
        assert not any("off_language" in ft or "language_purity" in ft for ft in report.issue_types)
