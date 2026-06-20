from __future__ import annotations

import re

# Escapes for PLAIN data strings (metric names/values, deterministic fallback text).
# NOT for LLM-authored LaTeX (that goes through markdown_to_latex only).
_ESCAPES = [
    ("\\", "\\textbackslash{}"),
    ("&", "\\&"),
    ("%", "\\%"),
    ("$", "\\$"),
    ("#", "\\#"),
    ("_", "\\_"),
    ("{", "\\{"),
    ("}", "\\}"),
    ("~", "\\textasciitilde{}"),
    ("^", "\\textasciicircum{}"),
]


def latex_escape_text(text: str) -> str:
    """Escape LaTeX specials in a plain data string. Backslash is handled first."""
    out = text
    for needle, replacement in _ESCAPES:
        out = out.replace(needle, replacement)
    return out


def _format_value(value: object) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{round(value, 4):g}"
    return str(value)


def render_metrics_table(metrics: dict[str, object], language: str) -> str:
    """Render a metrics dict as a booktabs LaTeX table. Empty dict -> empty string."""
    if not metrics:
        return ""
    metric_head, value_head = ("指标", "数值") if language == "zh" else ("Metric", "Value")
    rows = [
        f"{latex_escape_text(str(name).replace('_', ' '))} & {latex_escape_text(_format_value(value))} \\\\"
        for name, value in metrics.items()
    ]
    return "\n".join(
        [
            "\\begin{tabular}{ll}",
            "\\toprule",
            f"{metric_head} & {value_head} \\\\",
            "\\midrule",
            *rows,
            "\\bottomrule",
            "\\end{tabular}",
        ]
    )


def markdown_to_latex(text: str) -> str:
    """Convert common markdown leakage in LLM-authored LaTeX into LaTeX.

    Handles code fences, ATX headings, bullet lists, bold and italic. Leaves
    genuine LaTeX (``\\command``, ``$math$``) untouched.
    """
    lines = text.splitlines()
    out_lines: list[str] = []
    bullets: list[str] = []

    def flush_bullets() -> None:
        if not bullets:
            return
        out_lines.append("\\begin{itemize}")
        out_lines.extend(f"\\item {item}" for item in bullets)
        out_lines.append("\\end{itemize}")
        bullets.clear()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):  # drop code-fence markers, keep inner content
            continue
        bullet = re.match(r"^[-*]\s+(.*)$", stripped)
        if bullet:
            bullets.append(bullet.group(1))
            continue
        flush_bullets()
        heading = re.match(r"^#{1,6}\s+(.*)$", stripped)
        if heading:
            out_lines.append(f"\\textbf{{{heading.group(1)}}}")
            continue
        out_lines.append(line)
    flush_bullets()

    joined = "\n".join(out_lines)
    joined = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", joined)
    joined = re.sub(r"(?<![\*\\])\*([^*\n]+?)\*(?!\*)", r"\\emph{\1}", joined)
    return joined
