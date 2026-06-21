from mcm_agent.corpus.ingest import ingest_corpus
from mcm_agent.corpus.manifest import CorpusEntry
from mcm_agent.corpus.retrieve import methods_for_problem_type, section_exemplars
from mcm_agent.providers.embedding import FakeEmbeddingProvider, FakeRerankProvider
from mcm_agent.providers.mineru import FakeMinerUProvider


def _ingest(tmp_path):
    md = tmp_path / "2024-1.md"
    md.write_text(
        "# Summary\n\nx\n\n## Model Development\n\nWe use a Markov chain.\n\n"
        "## Sensitivity Analysis\n\nWe perturb the demand parameter.",
        encoding="utf-8",
    )
    e = CorpusEntry(
        paper_id="2024-1",
        year=2024,
        contest="MCM",
        problem="C",
        problem_type="data",
        control_number="1",
        pdf_path=str(md),
        source_repo="d",
    )
    kb = tmp_path / "kb"
    ingest_corpus(
        [e],
        kb,
        mineru_provider=FakeMinerUProvider(),
        embedding_provider=FakeEmbeddingProvider(),
        embedding_model="fake",
    )
    return kb


def test_section_exemplars_filters_by_section_and_type(tmp_path):
    kb = _ingest(tmp_path)
    hits = section_exemplars(
        kb,
        "how to vary parameters",
        section="sensitivity",
        problem_type="data",
        embedding_provider=FakeEmbeddingProvider(),
        reranker=FakeRerankProvider(),
        top_k=3,
    )
    assert hits and all(h.metadata["section_type"] == "sensitivity" for h in hits)


def test_methods_for_problem_type_returns_model_sections(tmp_path):
    kb = _ingest(tmp_path)
    hits = methods_for_problem_type(
        kb,
        "data",
        embedding_provider=FakeEmbeddingProvider(),
        reranker=FakeRerankProvider(),
    )
    assert hits and all(h.metadata["section_type"] == "model" for h in hits)
