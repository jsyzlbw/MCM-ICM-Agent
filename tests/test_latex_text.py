from mcm_agent.core.latex_text import (
    latex_escape_text,
    markdown_to_latex,
    render_metrics_table,
)


def test_markdown_bold_to_textbf() -> None:
    assert markdown_to_latex("**M1:** the **model**") == "\\textbf{M1:} the \\textbf{model}"


def test_markdown_italic_to_emph() -> None:
    assert "\\emph{x}" in markdown_to_latex("an *x* term")


def test_markdown_strips_code_fence() -> None:
    out = markdown_to_latex("```python\ncode here\n```")
    assert "```" not in out
    assert "code here" in out


def test_markdown_heading_to_bold() -> None:
    out = markdown_to_latex("### 模型形式\nbody text")
    assert "#" not in out
    assert "\\textbf{模型形式}" in out
    assert "body text" in out


def test_markdown_bullets_to_itemize() -> None:
    out = markdown_to_latex("- a\n- b")
    assert "\\begin{itemize}" in out
    assert "\\item a" in out
    assert "\\item b" in out
    assert "\\end{itemize}" in out


def test_latex_escape_specials() -> None:
    assert latex_escape_text("a_b 50% x&y #1") == "a\\_b 50\\% x\\&y \\#1"


def test_latex_escape_backslash_first() -> None:
    out = latex_escape_text("path\\to")
    assert "\\textbackslash" in out
    assert "\\textbackslashto" not in out  # backslash escaped without eating following text


def test_markdown_leaves_real_latex_untouched() -> None:
    src = "The model is \\textbf{good} with $\\alpha=0.5$."
    assert markdown_to_latex(src) == src


def test_render_metrics_table_humanizes_and_rounds() -> None:
    out = render_metrics_table(
        {"elimination_consistency_rate": 0.78409090909, "num_seasons": 34}, "en"
    )
    assert "\\begin{tabular}" in out and "\\end{tabular}" in out
    assert "elimination consistency rate" in out  # humanized name, no raw underscore
    assert "0.7841" in out  # float rounded
    assert "34" in out  # int kept
    assert "Metric" in out and "Value" in out


def test_render_metrics_table_zh_header() -> None:
    out = render_metrics_table({"a": 1}, "zh")
    assert "指标" in out and "数值" in out


def test_render_metrics_table_empty() -> None:
    assert render_metrics_table({}, "en") == ""
