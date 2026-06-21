from __future__ import annotations

from pathlib import Path

from mcm_agent.corpus.ingest import CorpusHit, CorpusKB


def section_exemplars(
    kb_dir: Path,
    query: str,
    *,
    section: str,
    embedding_provider: object,
    reranker: object | None = None,
    problem_type: str | None = None,
    top_k: int = 5,
) -> list[CorpusHit]:
    """Retrieve strong examples of a given paper section, optionally scoped to a problem type."""
    where: dict = {"section_type": section}
    if problem_type:
        where = {"$and": [{"section_type": section}, {"problem_type": problem_type}]}
    return CorpusKB(kb_dir).query(query, embedding_provider, reranker, where=where, top_k=top_k)


def methods_for_problem_type(
    kb_dir: Path,
    problem_type: str,
    *,
    embedding_provider: object,
    reranker: object | None = None,
    top_k: int = 8,
) -> list[CorpusHit]:
    """Retrieve modeling/method passages from winning papers of a given problem type."""
    where = {"$and": [{"problem_type": problem_type}, {"section_type": "model"}]}
    return CorpusKB(kb_dir).query(
        "modeling approach and method", embedding_provider, reranker, where=where, top_k=top_k
    )
