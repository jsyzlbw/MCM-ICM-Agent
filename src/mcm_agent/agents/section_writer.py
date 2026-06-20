from __future__ import annotations

import json

from mcm_agent.core.latex_text import latex_escape_text, markdown_to_latex
from mcm_agent.providers.base import TextGenerationProvider

# Minimal language-aware fallback bodies (used when no LLM or on error/empty output).
_FALLBACK = {
    "abstract": (
        "This paper presents an evidence-backed model and reports the key results below.",
        "本文给出一个有证据支撑的模型，并在下文报告主要结果。",
    ),
    "introduction": (
        "We decompose the problem into data, modeling, and validation tasks.",
        "我们将问题拆解为数据、建模与验证三部分。",
    ),
    "assumptions": (
        "The assumptions connect the problem conditions to computable variables.",
        "下述假设将题目条件与可计算变量联系起来。",
    ),
    "model": (
        "The selected model is chosen for interpretability and reproducibility.",
        "所选模型兼顾可解释性与可复现性。",
    ),
    "results": (
        "The reported metrics are produced by the executed model.",
        "下列指标由实际运行的模型产出。",
    ),
    "sensitivity": (
        "Robustness is assessed against the registered baseline.",
        "稳健性以登记的基线为参照进行评估。",
    ),
    "conclusion": (
        "The recommendation is traceable to registered evidence and results.",
        "结论可追溯到登记的证据与结果。",
    ),
}


class PaperSectionWriter:
    def __init__(
        self,
        llm_provider: TextGenerationProvider | None = None,
        language: str = "en",
    ) -> None:
        self.llm = llm_provider
        self.language = language

    def write_section(self, name: str, title: str, facts: dict[str, object]) -> str:
        if self.llm is None:
            return self._fallback(name, title)
        try:
            raw = self.llm.generate(self._system(), self._prompt(name, title, facts)).content.strip()
        except Exception:
            return self._fallback(name, title)
        content = markdown_to_latex(raw)
        content = self._ensure_header(content, name, title)
        if "\\section" not in content or len(content.strip()) < len(self._header(name, title)) + 5:
            return self._fallback(name, title)
        return content + "\n"

    def _system(self) -> str:
        if self.language == "zh":
            return (
                "你是数学建模竞赛论文作者。用规范的学术中文撰写指定章节，"
                "专有名词、变量名、LaTeX 命令保留英文。"
                "只输出该章节的 LaTeX 正文，不要用 markdown，不要 \\cite，不要编造数字。"
            )
        return (
            "You are a contest-paper author. Write the requested section in clear academic English. "
            "Output only the section's LaTeX body. Do not use markdown, do not use \\cite, "
            "do not invent numbers beyond the provided facts."
        )

    def _prompt(self, name: str, title: str, facts: dict[str, object]) -> str:
        header = self._header(name, title)
        facts_block = json.dumps(facts, ensure_ascii=False, indent=2, default=str)
        return "\n".join(
            [
                f"Write the '{title}' section. Begin with this exact header line:",
                header,
                "",
                "Use only these facts (structured):",
                facts_block,
            ]
        )

    def _header(self, name: str, title: str) -> str:
        return f"\\section*{{{title}}}" if name == "abstract" else f"\\section{{{title}}}"

    def _ensure_header(self, content: str, name: str, title: str) -> str:
        if "\\section" in content:
            return content
        return self._header(name, title) + "\n" + content

    def _fallback(self, name: str, title: str) -> str:
        en, zh = _FALLBACK.get(name, (f"Section {title}.", f"{title}。"))
        body = zh if self.language == "zh" else en
        summary = ""
        return f"{self._header(name, title)}\n{latex_escape_text(body)}\n{summary}".rstrip() + "\n"
