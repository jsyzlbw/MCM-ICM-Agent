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

    def write_section(
        self,
        name: str,
        title: str,
        facts: dict[str, object],
        *,
        exemplars: list[str] | None = None,
    ) -> str:
        if self.llm is None:
            return self._fallback(name, title, facts)

        # ── Pass 1: outline ──────────────────────────────────────────────────
        outline = ""
        try:
            result = self.llm.generate(
                self._system(), self._outline_prompt(name, title, facts, exemplars)
            )
            outline = (result.content or "").strip()
        except Exception:
            outline = ""

        # ── Pass 2: draft ────────────────────────────────────────────────────
        draft = ""
        try:
            result = self.llm.generate(
                self._system(), self._draft_prompt(name, title, facts, outline, exemplars)
            )
            draft = (result.content or "").strip()
        except Exception:
            # Draft failed — try single-pass fallback (old _prompt behavior)
            try:
                result = self.llm.generate(
                    self._system(), self._prompt(name, title, facts)
                )
                draft = (result.content or "").strip()
            except Exception:
                return self._fallback(name, title, facts)

        if not draft:
            # Draft was empty — try single-pass
            try:
                result = self.llm.generate(
                    self._system(), self._prompt(name, title, facts)
                )
                draft = (result.content or "").strip()
            except Exception:
                pass

        if not draft:
            return self._fallback(name, title, facts)

        # ── Pass 3: revise ───────────────────────────────────────────────────
        revised = draft
        try:
            result = self.llm.generate(
                self._system(), self._revise_prompt(name, title, draft)
            )
            candidate = (result.content or "").strip()
            if candidate:
                revised = candidate
        except Exception:
            pass  # keep draft

        # ── Finalize ─────────────────────────────────────────────────────────
        content = markdown_to_latex(revised)
        content = self._ensure_header(content, name, title)
        if "\\section" not in content or len(content.strip()) < len(self._header(name, title)) + 5:
            return self._fallback(name, title, facts)
        return content + "\n"

    # ── Prompt builders ──────────────────────────────────────────────────────

    def _outline_prompt(
        self,
        name: str,
        title: str,
        facts: dict[str, object],
        exemplars: list[str] | None,
    ) -> str:
        header = self._header(name, title)
        facts_block = json.dumps(facts, ensure_ascii=False, indent=2, default=str)
        parts = [
            f"Create a detailed outline for the '{title}' section. "
            f"Begin with this exact header line:",
            header,
            "",
            "The outline must list: subsections with titles, what each subsection must cover, "
            "key equations or arguments to include, and rough length guidance.",
            "",
            "Use only these facts (structured):",
            facts_block,
        ]
        parts.extend(self._exemplar_block(exemplars))
        return "\n".join(parts)

    def _draft_prompt(
        self,
        name: str,
        title: str,
        facts: dict[str, object],
        outline: str,
        exemplars: list[str] | None,
    ) -> str:
        header = self._header(name, title)
        facts_block = json.dumps(facts, ensure_ascii=False, indent=2, default=str)
        parts = [
            f"Write a substantive LaTeX body for the '{title}' section. "
            f"Begin with this exact header line:",
            header,
            "",
            "SECTION OUTLINE (follow this structure):",
            outline if outline else "(no outline available — write a complete substantive section)",
            "",
            "Requirements: explain all equations, justify every assumption, interpret results "
            "with specifics; do not invent numbers not present in the facts.",
            "",
            "Use only these facts (structured):",
            facts_block,
        ]
        # Inject judge feedback if present
        jf = facts.get("judge_feedback")
        if isinstance(jf, dict):
            critique = jf.get("critique", "")
            suggestions = jf.get("suggestions", [])
            suggestion_text = "; ".join(str(s) for s in suggestions) if suggestions else ""
            parts.append("")
            parts.append(
                f"PRIOR JUDGE FEEDBACK — fix this specifically: {critique}. "
                f"Suggestions: {suggestion_text}"
            )
        parts.extend(self._exemplar_block(exemplars))
        return "\n".join(parts)

    def _revise_prompt(self, name: str, title: str, draft: str) -> str:
        header = self._header(name, title)
        rubric_note = (
            "This section is responsible for: clarity of writing, depth of explanation, "
            "logical coherence, and coverage of the problem's mathematical/modeling aspects."
        )
        return "\n".join(
            [
                f"Self-critique and improve the following draft of the '{title}' section.",
                "Begin your improved version with this exact header line:",
                header,
                "",
                rubric_note,
                "",
                "DRAFT TO REVISE:",
                draft,
                "",
                "Output only the improved LaTeX section body. Do not add commentary outside the LaTeX.",
            ]
        )

    def _exemplar_block(self, exemplars: list[str] | None) -> list[str]:
        """Return prompt lines for exemplars (empty list if no exemplars)."""
        if not exemplars:
            return []
        parts = [
            "",
            "EXEMPLAR SECTIONS (from award-winning papers):",
        ]
        for i, ex in enumerate(exemplars, 1):
            parts.append(f"--- Exemplar {i} ---")
            parts.append(ex)
        parts.append(
            "These are exemplar sections from award-winning papers — "
            "imitate their STRUCTURE and DEPTH only; "
            "do NOT copy sentences, numbers, or specific content; "
            "the content here must be original to THIS problem."
        )
        return parts

    # ── Existing helpers (unchanged) ─────────────────────────────────────────

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

    def _fallback(self, name: str, title: str, facts: dict[str, object] | None = None) -> str:
        """Deterministic, compile-safe section (no LLM). Renders only safe fields
        (problem summary + claim texts), fully LaTeX-escaped so it never breaks
        compilation; falls back to a generic sentence when nothing is available.
        """
        facts = facts or {}
        pieces = [self._header(name, title)]
        problem = facts.get("problem")
        if isinstance(problem, str) and problem.strip():
            pieces.append(latex_escape_text(problem.strip()))
        claims = facts.get("claims")
        if isinstance(claims, list):
            pieces.extend(latex_escape_text(str(c).strip()) for c in claims if str(c).strip())
        extra = facts.get("extra_lines")
        if isinstance(extra, list):
            pieces.extend(latex_escape_text(str(line).strip()) for line in extra if str(line).strip())
        if len(pieces) == 1:
            en, zh = _FALLBACK.get(name, (f"Section {title}.", f"{title}。"))
            pieces.append(latex_escape_text(zh if self.language == "zh" else en))
        return "\n".join(pieces) + "\n"
