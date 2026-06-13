from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FactLocks:
    numbers: tuple[str, ...]
    equations: tuple[str, ...]
    citations: tuple[str, ...]
    figure_refs: tuple[str, ...]
    table_refs: tuple[str, ...]


NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?%?")
INLINE_EQUATION_RE = re.compile(r"(\$[^$]+\$|\\\([^)]+\\\)|\\\[[^\]]+\\\])")
CITATION_RE = re.compile(r"\\cite[p,t]?\{[^}]+\}")
FIGURE_REF_RE = re.compile(r"Figure~\\ref\{[^}]+\}")
TABLE_REF_RE = re.compile(r"Table~\\ref\{[^}]+\}")


def extract_fact_locks(text: str) -> FactLocks:
    return FactLocks(
        numbers=tuple(NUMBER_RE.findall(text)),
        equations=tuple(INLINE_EQUATION_RE.findall(text)),
        citations=tuple(CITATION_RE.findall(text)),
        figure_refs=tuple(FIGURE_REF_RE.findall(text)),
        table_refs=tuple(TABLE_REF_RE.findall(text)),
    )
