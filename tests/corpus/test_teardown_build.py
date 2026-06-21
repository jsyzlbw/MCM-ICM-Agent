import json

from mcm_agent.corpus.ingest import CorpusKB
from mcm_agent.corpus.manifest import CorpusEntry
from mcm_agent.corpus.patterns import build_patterns
from mcm_agent.corpus.teardown import build_teardowns
from mcm_agent.providers.embedding import FakeEmbeddingProvider, FakeRerankProvider


def _entry(pid, ctrl):
    return CorpusEntry(
        paper_id=pid, year=2024, contest="MCM", problem="C", problem_type="data",
        control_number=ctrl, pdf_path="/x.pdf", source_repo="d",
    )


class _FakeLLM:
    def __init__(self, card):
        self._card = card

    def generate(self, system, prompt, *, temperature=0.2):
        class R:
            content = json.dumps(self._card)
        return R()


def _seed_markdown(kb, pid):
    d = kb / "markdown"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{pid}.md").write_text("# Summary\n\nA tennis momentum paper.", encoding="utf-8")


def test_build_teardowns_caches_indexes_and_patterns(tmp_path):
    kb = tmp_path / "kb"
    entries = [_entry("2024-100", "100"), _entry("2024-200", "200")]
    for e in entries:
        _seed_markdown(kb, e.paper_id)
    card = {
        "problem_summary": "Predict momentum.",
        "models_used": ["Markov chain", "Kalman filter"],
        "key_techniques": ["hypothesis testing"],
        "why_it_won": "Strong validation.",
        "section_highlights": "Clear assumptions.",
        "pitfalls_or_limitations": ["ignores health"],
        "reusable_patterns": ["state-space model"],
    }

    result = build_teardowns(
        entries, kb, llm=_FakeLLM(card),
        embedding_provider=FakeEmbeddingProvider(), embedding_model="fake",
        years={2024}, problems={"C"},
    )
    assert result["cards"] == 2 and result["indexed"] == 2
    # cards cached as JSON
    assert (kb / "teardowns" / "2024-100.json").exists()

    # teardown chunk is retrievable and tagged section_type=teardown
    hits = CorpusKB(kb).query(
        "which models did winning teams use", FakeEmbeddingProvider(), FakeRerankProvider(),
        where={"section_type": "teardown"}, top_k=2,
    )
    assert hits and all(h.metadata["section_type"] == "teardown" for h in hits)
    assert "Markov chain" in hits[0].content

    # second run is a cache hit (no LLM needed) — pass an LLM that would raise if called
    class _Boom:
        def generate(self, *a, **k):
            raise AssertionError("LLM should not be called on cache hit")

    again = build_teardowns(entries, kb, llm=_Boom(), embedding_provider=None, years={2024}, problems={"C"})
    assert again["cards"] == 2

    # pattern library aggregates by problem_type
    summary = build_patterns(kb)
    assert summary == {"data": 2}
    data = json.loads((kb / "patterns" / "data.json").read_text())
    assert data["paper_count"] == 2
    names = {m["name"] for m in data["common_models"]}
    assert "Markov chain" in names
    assert data["common_models"][0]["papers"] == 2  # both papers used it
