from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import BaseModel, Field

from mcm_agent.core.embedding_cache import EmbeddingCache
from mcm_agent.core.vector_index import VectorIndex
from mcm_agent.corpus.manifest import CorpusEntry
from mcm_agent.utils.json_io import read_json, write_json

# How much of a paper to feed the LLM. Papers average ~19k tokens; deepseek handles
# this comfortably. Truncate defensively for the rare very long paper.
_MAX_PAPER_CHARS = 60000

TEARDOWN_SYSTEM = (
    "You are an experienced MCM/ICM judge and mathematical-modeling coach. You analyze an "
    "Outstanding (O-award) contest paper and produce a structured 'teardown' that a paper-writing "
    "agent can learn from. Be concrete and specific to THIS paper. Respond with ONLY a single JSON "
    "object, no prose, no markdown fences."
)

_CARD_KEYS = (
    "problem_summary",
    "models_used",
    "key_techniques",
    "why_it_won",
    "section_highlights",
    "pitfalls_or_limitations",
    "reusable_patterns",
)


class TeardownCard(BaseModel):
    paper_id: str
    year: int
    problem: str
    problem_type: str
    problem_summary: str = ""
    models_used: list[str] = Field(default_factory=list)
    key_techniques: list[str] = Field(default_factory=list)
    why_it_won: str = ""
    section_highlights: str = ""
    pitfalls_or_limitations: list[str] = Field(default_factory=list)
    reusable_patterns: list[str] = Field(default_factory=list)


def build_prompt(markdown: str, entry: CorpusEntry) -> str:
    body = markdown[:_MAX_PAPER_CHARS]
    return (
        f"Analyze this {entry.year} MCM/ICM Problem {entry.problem} "
        f"({entry.problem_type}) Outstanding paper.\n\n"
        "Return ONLY a JSON object with exactly these keys:\n"
        '- "problem_summary": 1-2 sentences on what the problem asked.\n'
        '- "models_used": array of the concrete models/algorithms used (e.g. "Markov chain", '
        '"XGBoost", "ARIMA").\n'
        '- "key_techniques": array of notable techniques (feature engineering, validation, '
        "optimization, etc.).\n"
        '- "why_it_won": 2-3 sentences from a judge\'s perspective on why this paper scored high.\n'
        '- "section_highlights": 2-3 sentences on what made the WRITING/structure strong.\n'
        '- "pitfalls_or_limitations": array of weaknesses or limitations the paper itself notes.\n'
        '- "reusable_patterns": array of concrete approaches a future team could reuse.\n\n'
        f"PAPER:\n{body}\n"
    )


def _extract_json(text: str) -> dict:
    """Tolerantly pull the JSON object out of an LLM response (handles ``` fences / stray prose)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start, end = text.find("{"), text.rfind("}")
        candidate = text[start : end + 1] if start != -1 and end > start else "{}"
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def parse_card(text: str, entry: CorpusEntry) -> TeardownCard:
    data = _extract_json(text)
    return TeardownCard(
        paper_id=entry.paper_id,
        year=entry.year,
        problem=entry.problem,
        problem_type=entry.problem_type,
        problem_summary=str(data.get("problem_summary", "")).strip(),
        models_used=_as_list(data.get("models_used")),
        key_techniques=_as_list(data.get("key_techniques")),
        why_it_won=str(data.get("why_it_won", "")).strip(),
        section_highlights=str(data.get("section_highlights", "")).strip(),
        pitfalls_or_limitations=_as_list(data.get("pitfalls_or_limitations")),
        reusable_patterns=_as_list(data.get("reusable_patterns")),
    )


def generate_teardown(markdown: str, entry: CorpusEntry, llm: object) -> TeardownCard:
    result = llm.generate(TEARDOWN_SYSTEM, build_prompt(markdown, entry))
    content = getattr(result, "content", result)
    return parse_card(str(content), entry)


def render_card_text(card: TeardownCard) -> str:
    """Flatten a card into a searchable text blob for indexing into the vector store."""
    parts = [
        f"Teardown of {card.year} MCM/ICM Problem {card.problem} ({card.problem_type}) "
        f"Outstanding paper {card.paper_id}.",
        f"Problem: {card.problem_summary}",
        f"Models used: {', '.join(card.models_used)}",
        f"Key techniques: {', '.join(card.key_techniques)}",
        f"Why it won: {card.why_it_won}",
        f"Writing highlights: {card.section_highlights}",
        f"Pitfalls/limitations: {'; '.join(card.pitfalls_or_limitations)}",
        f"Reusable patterns: {'; '.join(card.reusable_patterns)}",
    ]
    return "\n".join(p for p in parts if p.rsplit(": ", 1)[-1].strip())


def load_or_generate_card(entry: CorpusEntry, kb_dir: Path, llm: object) -> TeardownCard | None:
    """Return a cached card if present, else generate one from the paper's markdown and cache it."""
    td_dir = Path(kb_dir) / "teardowns"
    td_dir.mkdir(parents=True, exist_ok=True)
    dest = td_dir / f"{entry.paper_id}.json"
    if dest.exists():
        return TeardownCard(**read_json(dest, {}))
    md_path = Path(kb_dir) / "markdown" / f"{entry.paper_id}.md"
    if not md_path.exists():
        return None
    card = generate_teardown(md_path.read_text(encoding="utf-8"), entry, llm)
    write_json(dest, card.model_dump())
    return card


def build_teardowns(
    entries: list[CorpusEntry],
    kb_dir: Path,
    *,
    llm: object,
    embedding_provider: object | None = None,
    embedding_model: str = "voyage-3-large",
    years: set[int] | None = None,
    problems: set[str] | None = None,
    max_workers: int = 8,
) -> dict:
    kb_dir = Path(kb_dir)
    selected = [
        e for e in entries
        if (years is None or e.year in years)
        and (problems is None or e.problem in problems)
        and (kb_dir / "markdown" / f"{e.paper_id}.md").exists()  # only converted papers
    ]
    cards: list[TeardownCard] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for card in pool.map(lambda e: load_or_generate_card(e, kb_dir, llm), selected):
            if card is not None:
                cards.append(card)

    indexed = 0
    if embedding_provider is not None and cards:
        index = VectorIndex(persist_dir=kb_dir / "chroma", collection_name="mcm_corpus")
        cache = EmbeddingCache(kb_dir / "embedding_cache.db")
        ids, docs, metas, texts = [], [], [], []
        for c in cards:
            text = render_card_text(c)
            ids.append(f"{c.paper_id}#teardown")
            docs.append(text)
            texts.append(text)
            metas.append(
                {
                    "paper_id": c.paper_id,
                    "year": c.year,
                    "problem": c.problem,
                    "problem_type": c.problem_type,
                    "section_type": "teardown",
                    "award": "Outstanding",
                    "source": "teardown_card",
                    "chunk_index": 0,
                }
            )
        embeddings = cache.embed_with_cache(embedding_provider, embedding_model, texts)
        index.add_chunks(ids=ids, embeddings=embeddings, documents=docs, metadatas=metas)
        indexed = len(ids)
    return {"cards": len(cards), "indexed": indexed}
