"""PQ6 – Dedicated MCM summary sheet first page (O5 / summary_sheet dim).

The summary sheet is the judge-facing one-pager that appears as the FIRST page
of the paper.  It is DISTINCT from abstract.tex:
  - abstract.tex  -> \\section*{Abstract} technical abstract in the body
  - summary_sheet.tex -> styled first page: control number, problem title,
    one-page summary for judges (problem restatement, approach, key quantitative
    results, conclusion/recommendation)

Tests cover:
1. paper/summary_sheet.tex is created with a control-number placeholder.
2. The file contains real metric values (not generic placeholders).
3. The content is distinct from abstract.tex content.
4. main.tex inputs summary_sheet BEFORE abstract / body sections (via \\input).
5. Language-specific: zh workspace writes Chinese control-number label.
6. Language-specific: en workspace writes English control-number label.
7. Deterministic fallback works without an LLM (no crash, required fields present).
8. LLM path is used when a provider is given, but falls back if LLM output is bad.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcm_agent.agents.summary_sheet import SummarySheetAgent
from mcm_agent.agents.writer import PaperWriterAgent
from mcm_agent.core.model_spec import ModelSpec, SubproblemModel, write_model_spec
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.base import ProviderResult


# ---------------------------------------------------------------------------
# Fake LLM helpers
# ---------------------------------------------------------------------------


class _GoodLLM:
    """Returns a well-formed summary sheet body when called."""

    def generate(self, system: str, prompt: str) -> ProviderResult:
        return ProviderResult(
            content=(
                "This is the judge-facing summary.  "
                "The approach used constrained optimization.  "
                "Key result: accuracy = 0.92.  "
                "Recommendation: adopt the proposed model."
            ),
            metadata={},
        )


class _BadLLM:
    """Returns unusable content to exercise the fallback path."""

    def generate(self, system: str, prompt: str) -> ProviderResult:
        return ProviderResult(content="   ", metadata={})


class _RaisingLLM:
    """Raises an exception to exercise the error-fallback path."""

    def generate(self, system: str, prompt: str) -> ProviderResult:
        raise RuntimeError("network down")


# ---------------------------------------------------------------------------
# Workspace builders
# ---------------------------------------------------------------------------


def _make_en_workspace(tmp_path: Path, metrics: dict | None = None) -> Path:
    root = create_workspace(tmp_path / "ws_en").root
    # direction_lock → language = en
    (root / "discussion").mkdir(parents=True, exist_ok=True)
    (root / "discussion" / "direction_lock.json").write_text(
        json.dumps({"language": "en", "selected_route": "regression"}),
        encoding="utf-8",
    )
    # ModelSpec
    spec = ModelSpec(
        version=1,
        problem_restatement="Optimise wildfire suppression coverage.",
        subproblems=[
            SubproblemModel(
                subproblem_id="SP1",
                title="Coverage Allocation",
                approach="constrained linear programming",
                variables=[],
                assumptions=["Homogeneous terrain"],
                equations=[],
                algorithm_steps=["Step 1: solve LP"],
                metrics=["coverage_rate"],
            )
        ],
    )
    write_model_spec(root, spec)
    # Metrics
    m = metrics or {"coverage_rate": 0.87, "response_time_s": 42.0}
    (root / "results").mkdir(parents=True, exist_ok=True)
    (root / "results" / "model_metrics.json").write_text(
        json.dumps(m), encoding="utf-8"
    )
    # Minimal paper dir
    paper_dir = root / "paper"
    paper_dir.mkdir(parents=True, exist_ok=True)
    section_dir = paper_dir / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    (section_dir / "abstract.tex").write_text(
        "\\section*{Abstract}\nTechnical abstract content here.\n", encoding="utf-8"
    )
    return root


def _make_zh_workspace(tmp_path: Path) -> Path:
    root = create_workspace(tmp_path / "ws_zh").root
    (root / "discussion").mkdir(parents=True, exist_ok=True)
    (root / "discussion" / "direction_lock.json").write_text(
        json.dumps({"language": "zh", "selected_route": "regression"}),
        encoding="utf-8",
    )
    spec = ModelSpec(
        version=1,
        problem_restatement="优化野火扑救覆盖率。",
        subproblems=[
            SubproblemModel(
                subproblem_id="SP1",
                title="资源分配",
                approach="约束线性规划",
                variables=[],
                assumptions=["地形均匀"],
                equations=[],
                algorithm_steps=["步骤1：求解LP"],
                metrics=["覆盖率"],
            )
        ],
    )
    write_model_spec(root, spec)
    (root / "results").mkdir(parents=True, exist_ok=True)
    (root / "results" / "model_metrics.json").write_text(
        json.dumps({"coverage_rate": 0.91}), encoding="utf-8"
    )
    paper_dir = root / "paper"
    paper_dir.mkdir(parents=True, exist_ok=True)
    section_dir = paper_dir / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    (section_dir / "abstract.tex").write_text(
        "\\section*{摘要}\n技术摘要内容。\n", encoding="utf-8"
    )
    return root


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_summary_sheet_creates_file(tmp_path: Path) -> None:
    """SummarySheetAgent.run() must produce paper/summary_sheet.tex."""
    root = _make_en_workspace(tmp_path)
    SummarySheetAgent().run(root)
    assert (root / "paper" / "summary_sheet.tex").exists(), (
        "paper/summary_sheet.tex was not created"
    )


def test_summary_sheet_contains_control_number_placeholder_en(tmp_path: Path) -> None:
    """EN summary sheet must include a control-number placeholder line."""
    root = _make_en_workspace(tmp_path)
    SummarySheetAgent().run(root)
    content = (root / "paper" / "summary_sheet.tex").read_text(encoding="utf-8")
    assert "XXXXXXX" in content, (
        "Expected control-number placeholder 'XXXXXXX' in summary_sheet.tex\n"
        f"Got:\n{content}"
    )


def test_summary_sheet_contains_control_number_label_en(tmp_path: Path) -> None:
    """EN summary sheet must have an English label for the control number."""
    root = _make_en_workspace(tmp_path)
    SummarySheetAgent().run(root)
    content = (root / "paper" / "summary_sheet.tex").read_text(encoding="utf-8")
    # Accept any reasonable English label (case-insensitive)
    lower = content.lower()
    assert "control" in lower and ("number" in lower or "team" in lower), (
        "Expected English control-number label in summary_sheet.tex\n"
        f"Got:\n{content}"
    )


def test_summary_sheet_contains_real_metric_value(tmp_path: Path) -> None:
    """Summary sheet must embed at least one real metric value from model_metrics.json."""
    root = _make_en_workspace(tmp_path, metrics={"accuracy": 0.92, "rmse": 0.04})
    SummarySheetAgent().run(root)
    content = (root / "paper" / "summary_sheet.tex").read_text(encoding="utf-8")
    # At least one metric value must appear literally
    assert "0.92" in content or "0.04" in content, (
        "Expected real metric value (0.92 or 0.04) in summary_sheet.tex\n"
        f"Got:\n{content}"
    )


def test_summary_sheet_distinct_from_abstract(tmp_path: Path) -> None:
    """Summary sheet content must differ from abstract.tex content."""
    root = _make_en_workspace(tmp_path)
    SummarySheetAgent().run(root)
    abstract = (root / "paper" / "sections" / "abstract.tex").read_text(encoding="utf-8")
    summary = (root / "paper" / "summary_sheet.tex").read_text(encoding="utf-8")
    # They should not be identical
    assert summary.strip() != abstract.strip(), (
        "summary_sheet.tex must be distinct from abstract.tex"
    )
    # The summary sheet must NOT just copy the abstract section command
    assert "\\section*{Abstract}" not in summary, (
        "summary_sheet.tex must not simply re-use the abstract section header"
    )


def test_summary_sheet_zh_label(tmp_path: Path) -> None:
    """ZH summary sheet must use a Chinese label for the control number."""
    root = _make_zh_workspace(tmp_path)
    SummarySheetAgent().run(root)
    content = (root / "paper" / "summary_sheet.tex").read_text(encoding="utf-8")
    # Must contain Chinese text (CJK range)
    has_cjk = any("一" <= ch <= "鿿" for ch in content)
    assert has_cjk, (
        "ZH summary_sheet.tex must contain Chinese text\n"
        f"Got:\n{content}"
    )
    assert "XXXXXXX" in content, (
        "ZH summary sheet still needs the XXXXXXX control-number placeholder"
    )


def test_summary_sheet_zh_metric_value(tmp_path: Path) -> None:
    """ZH workspace: metric value must appear in the summary sheet."""
    root = _make_zh_workspace(tmp_path)
    SummarySheetAgent().run(root)
    content = (root / "paper" / "summary_sheet.tex").read_text(encoding="utf-8")
    assert "0.91" in content, (
        "ZH summary_sheet.tex must include real metric value 0.91\n"
        f"Got:\n{content}"
    )


def test_summary_sheet_with_good_llm(tmp_path: Path) -> None:
    """When a working LLM is provided, its output is included in the file."""
    root = _make_en_workspace(tmp_path)
    SummarySheetAgent(llm_provider=_GoodLLM()).run(root)
    content = (root / "paper" / "summary_sheet.tex").read_text(encoding="utf-8")
    # LLM output mentions "constrained optimization" (echoed in our fake LLM response)
    assert "constrained optimization" in content, (
        "Expected LLM-generated text in summary_sheet.tex\n"
        f"Got:\n{content}"
    )


def test_summary_sheet_fallback_on_bad_llm(tmp_path: Path) -> None:
    """When LLM returns blank, the deterministic fallback is used (no crash, file exists)."""
    root = _make_en_workspace(tmp_path, metrics={"coverage_rate": 0.87})
    SummarySheetAgent(llm_provider=_BadLLM()).run(root)
    content = (root / "paper" / "summary_sheet.tex").read_text(encoding="utf-8")
    # Must still have XXXXXXX and a metric value
    assert "XXXXXXX" in content
    assert "0.87" in content


def test_summary_sheet_fallback_on_raising_llm(tmp_path: Path) -> None:
    """When LLM raises an exception, the deterministic fallback is used (no crash)."""
    root = _make_en_workspace(tmp_path, metrics={"coverage_rate": 0.87})
    SummarySheetAgent(llm_provider=_RaisingLLM()).run(root)
    content = (root / "paper" / "summary_sheet.tex").read_text(encoding="utf-8")
    assert "XXXXXXX" in content
    assert "0.87" in content


def test_main_tex_inputs_summary_sheet_first(tmp_path: Path) -> None:
    """main.tex must \\input summary_sheet before the other body sections."""
    root = _make_en_workspace(tmp_path)
    # Populate minimal sections
    section_dir = root / "paper" / "sections"
    for name in ["introduction", "assumptions", "model", "results", "sensitivity", "conclusion"]:
        (section_dir / f"{name}.tex").write_text(
            f"\\section{{{name}}}\nPlaceholder.\n", encoding="utf-8"
        )
    # The production flow runs SummarySheetAgent first, then _write_main_files.
    SummarySheetAgent().run(root)
    PaperWriterAgent()._write_main_files(root / "paper")
    main = (root / "paper" / "main.tex").read_text(encoding="utf-8")
    assert "\\input{summary_sheet}" in main or "\\input{sections/summary_sheet}" in main, (
        "main.tex must \\input summary_sheet\n"
        f"Got:\n{main}"
    )
    # summary_sheet must appear BEFORE abstract and body sections
    ss_pos = main.find("summary_sheet")
    abstract_pos = main.find("abstract")
    assert ss_pos != -1, "summary_sheet not found in main.tex"
    assert abstract_pos != -1, "abstract not found in main.tex"
    assert ss_pos < abstract_pos, (
        f"summary_sheet (pos {ss_pos}) must appear before abstract (pos {abstract_pos}) in main.tex"
    )


def test_summary_sheet_no_crash_without_model_spec(tmp_path: Path) -> None:
    """Without a ModelSpec the agent must not crash and must still write the file."""
    root = create_workspace(tmp_path / "ws_nospec").root
    (root / "discussion").mkdir(parents=True, exist_ok=True)
    (root / "discussion" / "direction_lock.json").write_text(
        json.dumps({"language": "en"}), encoding="utf-8"
    )
    (root / "results").mkdir(parents=True, exist_ok=True)
    (root / "results" / "model_metrics.json").write_text(
        json.dumps({"score": 0.75}), encoding="utf-8"
    )
    (root / "paper").mkdir(parents=True, exist_ok=True)
    SummarySheetAgent().run(root)
    content = (root / "paper" / "summary_sheet.tex").read_text(encoding="utf-8")
    assert "XXXXXXX" in content


def test_summary_sheet_no_bare_linebreak_in_prose(tmp_path: Path) -> None:
    """Summary sheet prose body must not contain bare \\\\ line breaks (compile safety).

    Bare \\\\ outside tabular/align/center is unsafe in LaTeX. Instead use \\par.
    This test uses a working LLM so _render_tex wraps plain prose and appends
    the metrics block. That metrics block should NOT have bare \\\\.
    """
    root = _make_en_workspace(tmp_path, metrics={"accuracy": 0.92})
    agent = SummarySheetAgent(llm_provider=_GoodLLM())
    agent.run(root)
    content = (root / "paper" / "summary_sheet.tex").read_text(encoding="utf-8")
    # When LLM prose is wrapped, _render_tex appends metrics block.
    # Lines 297-305 in source currently have: }\\\\ which is bare \\\\ after }
    # We want to catch that pattern in the generated prose output.
    # Look for the problematic pattern: }\\\\  (closing brace followed by bare newline-break)
    # The actual line is: \\textbf{...}\\\\  which is the error
    if "\\textbf{Key Quantitative Results:}" in content:
        # Check that it's not followed by bare \\\\
        assert "\\textbf{Key Quantitative Results:}\\\\\n" not in content, (
            "Bare \\\\\\\\ found after metric label. Use \\\\par instead.\n"
            f"Content excerpt:\n{content}"
        )
