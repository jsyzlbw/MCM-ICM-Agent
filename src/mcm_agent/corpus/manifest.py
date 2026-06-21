from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from mcm_agent.corpus.taxonomy import problem_type
from mcm_agent.utils.json_io import write_json

_LETTER_DIR_RE = re.compile(r"^[A-F]$")
_LETTER_PREFIX_RE = re.compile(r"^([A-F])[-_ ]")
_LETTER_TI_RE = re.compile(r"^([A-F])题")
_LETTER_CONTEST_RE = re.compile(r"(?:MCM|ICM)\d{4}([A-F])")

# Files/dirs that are NOT outstanding-paper PDFs: bundled problems/results, and
# non-Outstanding award folders (其他奖项 = "other awards", S奖 = Successful, etc.).
_SKIP_TOKENS = (
    "problem",
    "result",
    "triage",
    "commentary",
    "addendum",
    "其他奖项",
    "s奖",
    "成功参赛",
)


def _control_from(stem: str) -> str | None:
    runs = re.findall(r"\d{3,}", stem)
    if runs:
        return max(runs, key=len)  # control number is the longest digit run
    slug = re.sub(r"[^0-9A-Za-z]+", "-", stem).strip("-")  # title-named files -> slug
    return slug or None


class CorpusEntry(BaseModel):
    paper_id: str  # f"{year}-{control_number}"
    year: int
    contest: str  # MCM or ICM
    problem: str  # A-F (or "?")
    problem_type: str
    control_number: str
    award: str = "Outstanding"  # refined in Plan 2 via results PDFs
    pdf_path: str  # absolute path
    source_repo: str  # top folder under outstanding_papers/


_YEAR_PREFIX_RE = re.compile(r"^(19|20)\d{2}")


def _year_from_parts(parts: tuple[str, ...]) -> int | None:
    # Prefer a path component that STARTS with a 4-digit year, e.g. a folder
    # named "2024" or "2010美赛特等奖". Skip parts[0]: it is the cloned-repo dir
    # whose name often carries a year RANGE ("dick20_2004-2025") that would
    # otherwise mis-date every paper under it.
    for part in (parts[1:] if len(parts) > 1 else parts):
        m = _YEAR_PREFIX_RE.match(part)
        if m:
            return int(m.group(0))
    # Fallback: repo dir naming exactly one distinct year (e.g. "catcat-lee_2025_icm_e").
    repo_years = sorted({int(y) for y in re.findall(r"(?:19|20)\d{2}", parts[0])}) if parts else []
    if len(repo_years) == 1:
        return repo_years[0]
    return None


def _letter_from(parts: tuple[str, ...], filename: str) -> str:
    for part in reversed(parts):
        if _LETTER_DIR_RE.match(part):  # folder "A".."F"
            return part
        m = _LETTER_TI_RE.match(part)  # folder "D题6篇"
        if m:
            return m.group(1)
        m = _LETTER_CONTEST_RE.search(part)  # folder "MCM2019A" / "ICM2019D"
        if m:
            return m.group(1)
    m = _LETTER_PREFIX_RE.match(filename)  # file "A-1034-Outstanding.pdf"
    return m.group(1) if m else "?"


def build_manifest(corpus_root: Path) -> list[CorpusEntry]:
    papers_root = Path(corpus_root) / "outstanding_papers"
    seen: dict[tuple[int, str], CorpusEntry] = {}
    for pdf in sorted(papers_root.rglob("*.pdf")):
        rel = pdf.relative_to(papers_root)
        parts = rel.parts
        low = pdf.as_posix().lower()
        if any(tok in low for tok in _SKIP_TOKENS):
            continue  # skip bundled problem/results/aux + non-Outstanding award PDFs
        year = _year_from_parts(parts)
        if year is None:
            continue
        control = _control_from(pdf.stem)
        if control is None:
            continue
        if (year, control) in seen:
            continue
        letter = _letter_from(parts, pdf.name)
        is_icm = letter in {"D", "E", "F"} or (year < 2016 and letter == "C")
        contest = "ICM" if is_icm else "MCM"
        seen[(year, control)] = CorpusEntry(
            paper_id=f"{year}-{control}",
            year=year,
            contest=contest,
            problem=letter,
            problem_type=problem_type(year, letter),
            control_number=control,
            pdf_path=str(pdf.resolve()),
            source_repo=parts[0],
        )
    return list(seen.values())


def write_manifest(entries: list[CorpusEntry], out_path: Path) -> None:
    write_json(out_path, [e.model_dump() for e in entries])
