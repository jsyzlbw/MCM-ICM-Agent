from mcm_agent.corpus.ingest import CorpusKB, ingest_corpus
from mcm_agent.corpus.manifest import CorpusEntry
from mcm_agent.providers.embedding import FakeEmbeddingProvider, FakeRerankProvider
from mcm_agent.providers.mineru import FakeMinerUProvider


def _entry(tmp_path, pid, year, letter, ptype, body):
    p = tmp_path / f"{pid}.md"  # Fake MinerU echoes .md content through
    p.write_text(body, encoding="utf-8")
    return CorpusEntry(
        paper_id=pid,
        year=year,
        contest="MCM",
        problem=letter,
        problem_type=ptype,
        control_number=pid.split("-")[1],
        pdf_path=str(p),
        source_repo="demo",
    )


def test_ingest_builds_filtered_kb_with_metadata(tmp_path):
    kb_dir = tmp_path / "kb"
    entries = [
        _entry(
            tmp_path,
            "2024-100",
            2024,
            "C",
            "data",
            "# Summary\n\nData model.\n\n## Sensitivity Analysis\n\nVary k.",
        ),
        _entry(tmp_path, "2014-200", 2014, "A", "continuous", "# Summary\n\nOld continuous paper."),
    ]
    summary = ingest_corpus(
        entries,
        kb_dir,
        mineru_provider=FakeMinerUProvider(),
        embedding_provider=FakeEmbeddingProvider(),
        embedding_model="fake",
        years={2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025},  # excludes 2014
    )
    assert summary.papers_ingested == 1
    assert summary.chunks_indexed >= 2

    kb = CorpusKB(kb_dir)
    hits = kb.query(
        "sensitivity",
        FakeEmbeddingProvider(),
        FakeRerankProvider(),
        where={"section_type": "sensitivity"},
        top_k=3,
    )
    assert hits and hits[0].metadata["paper_id"] == "2024-100"
    assert hits[0].metadata["problem_type"] == "data"
