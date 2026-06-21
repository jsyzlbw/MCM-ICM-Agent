from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from mcm_agent.core.embedding_cache import EmbeddingCache
from mcm_agent.core.vector_index import VectorIndex
from mcm_agent.corpus.convert import convert_entry
from mcm_agent.corpus.manifest import CorpusEntry
from mcm_agent.corpus.sections import section_chunks
from mcm_agent.utils.json_io import write_json

_COLLECTION = "mcm_corpus"


class IngestSummary(BaseModel):
    papers_ingested: int
    chunks_indexed: int
    skipped: int


class CorpusHit(BaseModel):
    content: str
    metadata: dict
    rerank_score: float = 0.0


def _passes(entry: CorpusEntry, years: set[int] | None, problems: set[str] | None) -> bool:
    if years is not None and entry.year not in years:
        return False
    if problems is not None and entry.problem not in problems:
        return False
    return True


def ingest_corpus(
    entries: list[CorpusEntry],
    kb_dir: Path,
    *,
    mineru_provider: object,
    embedding_provider: object,
    embedding_model: str,
    years: set[int] | None = None,
    problems: set[str] | None = None,
) -> IngestSummary:
    kb_dir = Path(kb_dir)
    kb_dir.mkdir(parents=True, exist_ok=True)
    index = VectorIndex(persist_dir=kb_dir / "chroma", collection_name=_COLLECTION)
    cache = EmbeddingCache(kb_dir / "embedding_cache.db")

    selected = [e for e in entries if _passes(e, years, problems)]
    write_json(kb_dir / "manifest.json", [e.model_dump() for e in selected])

    papers = chunks_total = skipped = 0
    for entry in selected:
        try:
            result = convert_entry(entry.paper_id, Path(entry.pdf_path), kb_dir, mineru_provider)
        except Exception:
            skipped += 1
            continue
        markdown = Path(result.markdown_path).read_text(encoding="utf-8")
        pairs = section_chunks(markdown)
        if not pairs:
            skipped += 1
            continue
        ids, docs, metas, texts = [], [], [], []
        for i, (section_type, chunk) in enumerate(pairs, 1):
            cid = f"{entry.paper_id}#chunk-{i:03d}"
            ids.append(cid)
            docs.append(chunk)
            texts.append(chunk)
            metas.append(
                {
                    "paper_id": entry.paper_id,
                    "year": entry.year,
                    "contest": entry.contest,
                    "problem": entry.problem,
                    "problem_type": entry.problem_type,
                    "section_type": section_type,
                    "award": entry.award,
                    "source": entry.pdf_path,
                    "chunk_index": i,
                }
            )
        embeddings = cache.embed_with_cache(embedding_provider, embedding_model, texts)
        index.add_chunks(ids=ids, embeddings=embeddings, documents=docs, metadatas=metas)
        papers += 1
        chunks_total += len(ids)
    return IngestSummary(papers_ingested=papers, chunks_indexed=chunks_total, skipped=skipped)


class CorpusKB:
    def __init__(self, kb_dir: Path) -> None:
        self.kb_dir = Path(kb_dir)
        self.index = VectorIndex(persist_dir=self.kb_dir / "chroma", collection_name=_COLLECTION)

    def query(
        self,
        query: str,
        embedding_provider: object,
        reranker: object | None = None,
        *,
        where: dict | None = None,
        top_k: int = 5,
        candidate_n: int = 20,
    ) -> list[CorpusHit]:
        vector = embedding_provider.embed([query])[0]
        raw = self.index.query_where(vector, candidate_n, where=where)
        if not raw:
            return []
        if reranker is not None:
            ranked = reranker.rerank(query, [r["content"] for r in raw], top_k)
            return [
                CorpusHit(
                    content=raw[row["index"]]["content"],
                    metadata=raw[row["index"]]["metadata"],
                    rerank_score=float(row["score"]),
                )
                for row in ranked
            ]
        return [CorpusHit(content=r["content"], metadata=r["metadata"]) for r in raw[:top_k]]
