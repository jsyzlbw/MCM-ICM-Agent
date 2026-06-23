"""Tests for core/repair_directive.py::read_repair_directive.

TDD: these tests are written BEFORE the implementation.
"""
from __future__ import annotations

import json
from pathlib import Path



def test_read_repair_directive_returns_dict_when_present(tmp_path: Path) -> None:
    """read_repair_directive returns the dict when the JSON file is valid."""
    from mcm_agent.core.repair_directive import read_repair_directive

    directive = {
        "target_stage": "solver_coder",
        "weak_dimension": "data_solution",
        "score": 4,
        "critique": "The data analysis is too shallow.",
        "suggestions": ["Add regression", "Include error bounds"],
        "iteration": 1,
    }
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    (review_dir / "repair_directive.json").write_text(
        json.dumps(directive), encoding="utf-8"
    )

    result = read_repair_directive(tmp_path)

    assert result == directive


def test_read_repair_directive_returns_none_when_absent(tmp_path: Path) -> None:
    """read_repair_directive returns None when the file does not exist."""
    from mcm_agent.core.repair_directive import read_repair_directive

    result = read_repair_directive(tmp_path)

    assert result is None


def test_read_repair_directive_returns_none_on_malformed_json(tmp_path: Path) -> None:
    """read_repair_directive returns None when the file contains malformed JSON."""
    from mcm_agent.core.repair_directive import read_repair_directive

    review_dir = tmp_path / "review"
    review_dir.mkdir()
    (review_dir / "repair_directive.json").write_text(
        "{ invalid json !!!", encoding="utf-8"
    )

    result = read_repair_directive(tmp_path)

    assert result is None


def test_read_repair_directive_returns_none_when_json_is_list(tmp_path: Path) -> None:
    """read_repair_directive returns None when JSON root is not a dict."""
    from mcm_agent.core.repair_directive import read_repair_directive

    review_dir = tmp_path / "review"
    review_dir.mkdir()
    (review_dir / "repair_directive.json").write_text(
        json.dumps(["not", "a", "dict"]), encoding="utf-8"
    )

    result = read_repair_directive(tmp_path)

    assert result is None
