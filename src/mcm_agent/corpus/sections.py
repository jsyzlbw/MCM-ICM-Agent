from __future__ import annotations

import re

from pydantic import BaseModel

from mcm_agent.agents.rag import chunk_text  # reuse existing paragraph chunker

_HEADING_RE = re.compile(r"^#{1,4}\s+(.*\S)\s*$", re.MULTILINE)

# Ordered: first matching keyword wins. Lowercased substring match on heading text.
_SECTION_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("summary", ("summary", "abstract")),
    ("restatement", ("restatement", "introduction", "background", "problem statement")),
    ("assumptions", ("assumption", "justification")),
    ("notation", ("notation", "symbol", "variables", "glossary")),
    ("sensitivity", ("sensitivity", "robustness", "stability analysis")),
    ("strengths_weaknesses", ("strength", "weakness", "limitation")),
    ("conclusion", ("conclusion", "discussion", "future work")),
    ("references", ("reference", "bibliography")),
    ("model", ("model", "method", "approach", "formulation", "solution", "results", "analysis")),
]


class Section(BaseModel):
    section_type: str
    heading: str
    body: str


def _classify(heading: str) -> str:
    low = heading.lower()
    for section_type, keywords in _SECTION_RULES:
        if any(kw in low for kw in keywords):
            return section_type
    return "other"


def segment_sections(markdown: str) -> list[Section]:
    matches = list(_HEADING_RE.finditer(markdown))
    if not matches:
        return [Section(section_type="other", heading="(body)", body=markdown.strip())]
    sections: list[Section] = []
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()
        sections.append(Section(section_type=_classify(heading), heading=heading, body=body))
    return sections


def section_chunks(markdown: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for section in segment_sections(markdown):
        for chunk in chunk_text(section.body):
            out.append((section.section_type, chunk))
    return out
