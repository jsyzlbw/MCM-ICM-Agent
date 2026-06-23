"""TDD tests for mcm_agent.corpus.reference.build_reference_block (Task J1)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcm_agent.corpus.reference import build_reference_block


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_teardown(directory: Path, filename: str, data: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(json.dumps(data), encoding="utf-8")


def _make_teardown_dir(tmp_path: Path) -> Path:
    td = tmp_path / "teardowns"
    _write_teardown(
        td,
        "2020-1.json",
        {
            "paper_id": "2020-1",
            "year": 2020,
            "problem_type": "data",
            "models_used": ["regression", "neural net"],
            "why_it_won": "rigorous validation",
            "pitfalls_or_limitations": ["small sample"],
            "reusable_patterns": ["cross-validation"],
        },
    )
    _write_teardown(
        td,
        "2020-2.json",
        {
            "paper_id": "2020-2",
            "year": 2020,
            "problem_type": "data",
            "models_used": ["random forest"],
            "why_it_won": "feature engineering",
            "pitfalls_or_limitations": [],
            "reusable_patterns": ["ensemble methods"],
        },
    )
    _write_teardown(
        td,
        "2019-x.json",
        {
            "paper_id": "2019-x",
            "year": 2019,
            "problem_type": "continuous",
            "models_used": ["ODE"],
            "why_it_won": "elegant differential equations",
            "pitfalls_or_limitations": [],
            "reusable_patterns": [],
        },
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildReferenceBlockTeardowns:
    def test_contains_matching_why_it_won(self, tmp_path):
        kb = _make_teardown_dir(tmp_path)
        result = build_reference_block(kb, "data")
        assert "rigorous validation" in result

    def test_contains_second_data_card(self, tmp_path):
        kb = _make_teardown_dir(tmp_path)
        result = build_reference_block(kb, "data")
        assert "feature engineering" in result

    def test_excludes_continuous_card(self, tmp_path):
        kb = _make_teardown_dir(tmp_path)
        result = build_reference_block(kb, "data")
        assert "elegant differential equations" not in result

    def test_exclude_paper_id_removes_card(self, tmp_path):
        kb = _make_teardown_dir(tmp_path)
        result = build_reference_block(kb, "data", exclude_paper_id="2020-1")
        assert "rigorous validation" not in result
        # Second data card still present
        assert "feature engineering" in result

    def test_header_present(self, tmp_path):
        kb = _make_teardown_dir(tmp_path)
        result = build_reference_block(kb, "data")
        assert "REFERENCE" in result
        assert "data" in result

    def test_teardown_subsection_label(self, tmp_path):
        kb = _make_teardown_dir(tmp_path)
        result = build_reference_block(kb, "data")
        assert "[Teardown cards]" in result

    def test_max_teardowns_limits_results(self, tmp_path):
        kb = _make_teardown_dir(tmp_path)
        # Add a third data card
        td = tmp_path / "teardowns"
        _write_teardown(
            td,
            "2021-3.json",
            {
                "paper_id": "2021-3",
                "year": 2021,
                "problem_type": "data",
                "models_used": [],
                "why_it_won": "third card wins",
                "pitfalls_or_limitations": [],
                "reusable_patterns": [],
            },
        )
        # max_teardowns=2 means at most 2 cards
        result = build_reference_block(kb, "data", max_teardowns=2)
        # "third card wins" must NOT appear (only first 2 picked, sorted alphabetically)
        assert "third card wins" not in result


class TestBuildReferenceBlockNoEmbedding:
    def test_no_embedding_returns_teardown_only(self, tmp_path):
        kb = _make_teardown_dir(tmp_path)
        result = build_reference_block(kb, "data", embedding=None)
        assert "rigorous validation" in result
        # No excerpt section when embedding=None
        assert "[Real section excerpts]" not in result

    def test_no_embedding_does_not_raise(self, tmp_path):
        kb = _make_teardown_dir(tmp_path)
        # Should never raise regardless of inputs
        result = build_reference_block(kb, "data", embedding=None)
        assert isinstance(result, str)


class TestBuildReferenceBlockEmptyKb:
    def test_empty_kb_returns_empty_string(self, tmp_path):
        # tmp_path exists but has no teardowns/ subdir
        result = build_reference_block(tmp_path, "data", embedding=None)
        assert result == ""

    def test_none_kb_dir_returns_empty_string(self):
        result = build_reference_block(None, "data", embedding=None)
        assert result == ""


class TestBuildReferenceBlockWithEmbeddingExcerpts:
    def test_excerpt_content_appears_in_output(self, tmp_path, monkeypatch):
        from mcm_agent.corpus.ingest import CorpusHit

        fake_hit = CorpusHit(
            content="EXEMPLAR MODEL TEXT",
            metadata={"paper_id": "2018-z", "section_type": "model"},
        )

        def fake_section_exemplars(*args, **kwargs):
            return [fake_hit]

        monkeypatch.setattr(
            "mcm_agent.corpus.reference.section_exemplars", fake_section_exemplars
        )

        kb = _make_teardown_dir(tmp_path)
        result = build_reference_block(kb, "data", embedding="fake-embed")
        assert "EXEMPLAR MODEL TEXT" in result

    def test_excerpt_subsection_label_appears(self, tmp_path, monkeypatch):
        from mcm_agent.corpus.ingest import CorpusHit

        fake_hit = CorpusHit(
            content="SOME EXCERPT",
            metadata={"paper_id": "2017-y", "section_type": "model"},
        )

        def fake_section_exemplars(*args, **kwargs):
            return [fake_hit]

        monkeypatch.setattr(
            "mcm_agent.corpus.reference.section_exemplars", fake_section_exemplars
        )

        kb = _make_teardown_dir(tmp_path)
        result = build_reference_block(kb, "data", embedding="fake-embed")
        assert "[Real section excerpts]" in result

    def test_excerpt_excludes_exclude_paper_id(self, tmp_path, monkeypatch):
        from mcm_agent.corpus.ingest import CorpusHit

        fake_hit = CorpusHit(
            content="SHOULD BE EXCLUDED",
            metadata={"paper_id": "2020-1", "section_type": "model"},
        )

        def fake_section_exemplars(*args, **kwargs):
            return [fake_hit]

        monkeypatch.setattr(
            "mcm_agent.corpus.reference.section_exemplars", fake_section_exemplars
        )

        kb = _make_teardown_dir(tmp_path)
        result = build_reference_block(
            kb, "data", embedding="fake-embed", exclude_paper_id="2020-1"
        )
        assert "SHOULD BE EXCLUDED" not in result

    def test_section_exemplars_error_returns_teardown_part(self, tmp_path, monkeypatch):
        """If section_exemplars raises, return teardown part without crashing."""

        def bad_exemplars(*args, **kwargs):
            raise RuntimeError("Voyage is down")

        monkeypatch.setattr(
            "mcm_agent.corpus.reference.section_exemplars", bad_exemplars
        )

        kb = _make_teardown_dir(tmp_path)
        result = build_reference_block(kb, "data", embedding="fake-embed")
        # Still has teardown content
        assert "rigorous validation" in result
        # No excerpt section label
        assert "[Real section excerpts]" not in result
