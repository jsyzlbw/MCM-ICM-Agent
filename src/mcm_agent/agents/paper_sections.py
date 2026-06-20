from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from mcm_agent.agents.paper_context import PaperContext
from mcm_agent.core.citations import CitationContext
from mcm_agent.core.models import PaperClaimPlanItem


SECTION_TITLES = {
    "abstract.tex": "\\section*{Abstract}",
    "introduction.tex": "\\section{Introduction}",
    "assumptions.tex": "\\section{Assumptions}",
    "model.tex": "\\section{Model}",
    "results.tex": "\\section{Results}",
    "sensitivity.tex": "\\section{Sensitivity Analysis}",
    "conclusion.tex": "\\section{Conclusion}",
}


def render_claim_plan_sections(
    claim_plan: list[PaperClaimPlanItem],
    context: PaperContext,
    citation_context: CitationContext | None = None,
) -> dict[str, str]:
    grouped: dict[str, list[PaperClaimPlanItem]] = defaultdict(list)
    for claim in claim_plan:
        grouped[Path(claim.section).name].append(claim)
    sections = {
        "abstract.tex": _render_abstract(context, claim_plan),
        "introduction.tex": _render_introduction(context),
    }
    for filename in [
        "assumptions.tex",
        "model.tex",
        "results.tex",
        "sensitivity.tex",
        "conclusion.tex",
    ]:
        sections[filename] = _render_claim_section(
            filename,
            grouped.get(filename, []),
            context,
            citation_context,
        )
    return sections


def render_claim_paragraph(
    claim: PaperClaimPlanItem,
    citation_context: CitationContext | None = None,
) -> str:
    evidence_id = claim.evidence_ids[0] if claim.evidence_ids else "missing"
    figure_id = claim.figure_ids[0] if claim.figure_ids else "missing"
    source_id = claim.source_ids[0] if claim.source_ids else "missing"
    trace = (
        f"% claim_id={claim.claim_id} "
        f"evidence_id={evidence_id} "
        f"figure_id={figure_id} "
        f"source_id={source_id}"
    )
    if claim.status == "unresolved":
        body = (
            "The planned claim "
            + _texttt(claim.claim_id)
            + " remains unresolved: "
            + _latex_escape(claim.unresolved_reason)
            + "."
        )
    else:
        cite = citation_context.cite_command(claim.source_ids) if citation_context else ""
        body = _latex_escape(claim.claim_text) + (f" {cite}" if cite else "")
    return body + "\n" + trace


def _render_abstract(
    context: PaperContext,
    claim_plan: list[PaperClaimPlanItem],
) -> str:
    critical = [
        claim.claim_text
        for claim in claim_plan
        if claim.priority == "critical" and claim.status != "unresolved"
    ]
    routes = [route for route in context.selected_routes if route and route != "llm_generated"]
    zh = context.language == "zh"
    method_phrase = ", ".join(routes) or ("题目专属模型" if zh else "a problem-specific model")
    problem = _latex_escape(_first_sentence(context.problem_summary, 240))
    method = _latex_escape(method_phrase)
    approach = _latex_escape(_first_sentence(" ".join(critical[:2]), 240))
    if zh:
        lead = f"本文采用{method}求解该数学建模问题。" + (f" {problem}" if problem else "")
    else:
        lead = (
            f"This paper develops {method} for the contest problem."
            + (f" {problem}" if problem else "")
        )
    return "\n".join(
        [
            SECTION_TITLES["abstract.tex"],
            lead,
            approach,
            "",
        ]
    )


def _first_sentence(text: str, max_chars: int) -> str:
    text = " ".join(text.split())
    if not text:
        return ""
    sentence = re.split(r"(?<=[。.!?！？])\s*", text)[0]
    return (sentence or text)[:max_chars]


# Language-keyed fallback sentences for _render_introduction.
# Tuple: (English, Chinese)
_INTRO_FALLBACKS = {
    "problem": (
        "The problem is decomposed into data, model, and validation tasks.",
        "本文将问题拆解为数据采集、建模与验证三个环节。",
    ),
    "direction": (
        "The confirmed direction emphasizes interpretable and reproducible modeling.",
        "确认的方向强调可解释且可复现的建模方法。",
    ),
    "remainder": (
        "The remainder of the paper follows the planned claim chain from assumptions to validated results.",
        "本文其余部分沿计划声明链从假设逐步推进至验证结论。",
    ),
}


def _render_introduction(context: PaperContext) -> str:
    zh = context.language == "zh"

    def _fb(key: str) -> str:
        en, zh_text = _INTRO_FALLBACKS[key]
        return zh_text if zh else en

    return "\n".join(
        [
            SECTION_TITLES["introduction.tex"],
            _latex_escape(context.problem_summary or _fb("problem")),
            _latex_escape(context.direction_summary or _fb("direction")),
            _fb("remainder"),
            "",
        ]
    )


def _render_claim_section(
    filename: str,
    claims: list[PaperClaimPlanItem],
    context: PaperContext,
    citation_context: CitationContext | None = None,
) -> str:
    title = SECTION_TITLES.get(filename, "\\section{Planned Claims}")
    paragraphs = [
        render_claim_paragraph(claim, citation_context)
        for claim in claims
    ]
    if filename == "model.tex" and context.model_decision_summary:
        paragraphs.insert(0, _latex_escape(context.model_decision_summary))
    if filename == "sensitivity.tex" and context.validation_summary:
        paragraphs.append(_latex_escape("Validation context: " + context.validation_summary))
    return "\n\n".join(
        [
            title,
            *(paragraphs or ["No planned claims were available for this section."]),
            "",
        ]
    )


def _latex_escape(value: str) -> str:
    return value.replace("_", "\\_")


def _texttt(value: str) -> str:
    return "\\texttt{" + _latex_escape(value) + "}"
