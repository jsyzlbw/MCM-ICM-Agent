"""Reference block builder for the anchored judge (Task J1).

Assembles a block of real Outstanding-paper material for a given problem_type:
  1. Teardown cards (no embedding needed) — filtered by problem_type.
  2. Real section excerpts (Voyage embedding, optional).

Usage::

    block = build_reference_block(kb_dir, "data", query="...", embedding=provider)

The function is fully robust: each part is wrapped in try/except; if both
parts fail or return nothing, "" is returned (never raises).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcm_agent.corpus.retrieve import section_exemplars

# Maximum characters to show per teardown field before truncation
_FIELD_MAX = 300
# Maximum characters per excerpt
_EXCERPT_MAX = 800


def _truncate(value: Any, max_chars: int = _FIELD_MAX) -> str:
    """Safely convert *value* to str and truncate if needed."""
    if isinstance(value, list):
        text = "; ".join(str(v) for v in value)
    else:
        text = str(value) if value is not None else ""
    if len(text) > max_chars:
        return text[:max_chars] + "…"
    return text


def _format_teardown_card(card: dict) -> str:
    """Format a single teardown card into a compact text block."""
    lines = [f"[paper_id={card.get('paper_id', '?')}]"]
    models = _truncate(card.get("models_used", []))
    if models:
        lines.append(f"  models_used: {models}")
    why = _truncate(card.get("why_it_won", ""))
    if why:
        lines.append(f"  why_it_won: {why}")
    pitfalls = _truncate(card.get("pitfalls_or_limitations", []))
    if pitfalls:
        lines.append(f"  pitfalls: {pitfalls}")
    patterns = _truncate(card.get("reusable_patterns", []))
    if patterns:
        lines.append(f"  reusable_patterns: {patterns}")
    return "\n".join(lines)


def build_reference_block(
    kb_dir: Path | None,
    problem_type: str,
    *,
    query: str = "",
    embedding: object | None = None,
    reranker: object | None = None,
    exclude_paper_id: str | None = None,
    max_teardowns: int = 2,
    max_excerpts: int = 2,
) -> str:
    """Build a reference block of real Outstanding-paper material.

    Parameters
    ----------
    kb_dir:
        Root of the corpus KB (contains a ``teardowns/`` sub-directory and the
        Chroma vector store).  May be *None* — returns "" in that case.
    problem_type:
        MCM/ICM problem-type tag (e.g. ``"data"``, ``"continuous"``).
    query:
        Free-text query for the section-excerpt retrieval.  Defaults to a
        generic "modeling approach and results" string when empty.
    embedding:
        Embedding provider for :func:`section_exemplars`.  When *None*, the
        excerpt part is skipped entirely.
    reranker:
        Optional reranker passed through to :func:`section_exemplars`.
    exclude_paper_id:
        Paper ID to exclude from *both* teardown cards and excerpts (prevents
        a paper from being its own reference).
    max_teardowns:
        Maximum number of teardown cards to include.
    max_excerpts:
        Maximum number of section excerpts to include.

    Returns
    -------
    str
        A formatted reference block, or ``""`` if nothing is available.
    """
    if kb_dir is None:
        return ""

    kb_dir = Path(kb_dir)
    teardown_dir = kb_dir / "teardowns"

    teardown_text = ""
    try:
        if teardown_dir.exists():
            cards = []
            for path in sorted(teardown_dir.glob("*.json")):
                if len(cards) >= max_teardowns:
                    break
                try:
                    card = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if card.get("problem_type") != problem_type:
                    continue
                if exclude_paper_id and card.get("paper_id") == exclude_paper_id:
                    continue
                cards.append(card)

            if cards:
                formatted = "\n\n".join(_format_teardown_card(c) for c in cards)
                teardown_text = f"[Teardown cards]\n{formatted}"
    except Exception:
        teardown_text = ""

    excerpt_text = ""
    if embedding is not None:
        try:
            effective_query = query or "modeling approach and results"
            hits = section_exemplars(
                kb_dir,
                effective_query,
                section="model",
                embedding_provider=embedding,
                reranker=reranker,
                problem_type=problem_type,
                top_k=max_excerpts,
            )
            # Filter out the excluded paper
            if exclude_paper_id:
                hits = [
                    h for h in hits
                    if h.metadata.get("paper_id") != exclude_paper_id
                ]
            hits = hits[:max_excerpts]

            if hits:
                excerpts = []
                for hit in hits:
                    content = hit.content
                    if len(content) > _EXCERPT_MAX:
                        content = content[:_EXCERPT_MAX] + "…"
                    pid = hit.metadata.get("paper_id", "?")
                    excerpts.append(f"[paper_id={pid}]\n{content}")
                excerpt_text = "[Real section excerpts]\n" + "\n\n".join(excerpts)
        except Exception:
            excerpt_text = ""

    # Assemble
    parts = [p for p in (teardown_text, excerpt_text) if p]
    if not parts:
        return ""

    header = (
        f"=== REFERENCE: real Outstanding work for problem type '{problem_type}' ==="
    )
    body = "\n\n".join(parts)
    return f"{header}\n\n{body}"
