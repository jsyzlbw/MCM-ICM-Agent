"""Tests for mcm_agent.core.problem_type.resolve_problem_type (KB0)."""
from __future__ import annotations

import json
from pathlib import Path


from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.base import ProviderResult


# ---------------------------------------------------------------------------
# Fake LLM helpers
# ---------------------------------------------------------------------------

class _FakeLLM:
    """LLM that always returns a fixed response string."""

    def __init__(self, response: str) -> None:
        self._response = response

    def generate(self, system: str, prompt: str) -> ProviderResult:
        return ProviderResult(content=self._response, metadata={})


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _workspace(tmp_path: Path) -> Path:
    """Create a mag workspace and return its root Path."""
    return create_workspace(tmp_path / "w").root


def _reports(root: Path) -> Path:
    d = root / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_resolve_from_taxonomy(tmp_path: Path) -> None:
    """problem_meta.json with year/letter → taxonomy lookup, no LLM needed."""
    root = _workspace(tmp_path)
    (_reports(root) / "problem_meta.json").write_text(
        json.dumps({"year": 2026, "letter": "C"}), encoding="utf-8"
    )

    from mcm_agent.core.problem_type import resolve_problem_type

    result = resolve_problem_type(root)
    assert result == "data"


def test_resolve_via_llm_fallback(tmp_path: Path) -> None:
    """No problem_meta, but problem_understanding.md + fake LLM → label written and returned."""
    root = _workspace(tmp_path)
    (_reports(root) / "problem_understanding.md").write_text(
        "This problem involves water resource sustainability and policy decisions.",
        encoding="utf-8",
    )

    from mcm_agent.core.problem_type import resolve_problem_type

    result = resolve_problem_type(root, llm=_FakeLLM("sustainability"))
    assert result == "sustainability"

    # should also write the cache file
    cache_path = root / "reports" / "problem_type.json"
    assert cache_path.exists()
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    assert data["problem_type"] == "sustainability"
    assert data["source"] == "llm"


def test_resolve_llm_invalid_label_returns_none(tmp_path: Path) -> None:
    """LLM returns a label not in the allowed set → None, no crash."""
    root = _workspace(tmp_path)
    (_reports(root) / "problem_understanding.md").write_text(
        "Some problem text.", encoding="utf-8"
    )

    from mcm_agent.core.problem_type import resolve_problem_type

    result = resolve_problem_type(root, llm=_FakeLLM("garbage"))
    assert result is None
    # cache file must NOT be written
    assert not (root / "reports" / "problem_type.json").exists()


def test_resolve_none_when_no_info(tmp_path: Path) -> None:
    """Empty workspace, no LLM → None, no crash."""
    root = _workspace(tmp_path)

    from mcm_agent.core.problem_type import resolve_problem_type

    result = resolve_problem_type(root, llm=None)
    assert result is None


def test_resolve_uses_cache(tmp_path: Path) -> None:
    """Pre-existing problem_type.json with valid label → returned directly, ignores meta/llm."""
    root = _workspace(tmp_path)
    (_reports(root) / "problem_type.json").write_text(
        json.dumps({"problem_type": "discrete", "source": "llm"}), encoding="utf-8"
    )

    from mcm_agent.core.problem_type import resolve_problem_type

    # Pass no meta, no LLM — cache should be used
    result = resolve_problem_type(root)
    assert result == "discrete"
