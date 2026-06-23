import json
from pathlib import Path

from mcm_agent.agents.mock_judge import DIMENSIONS, MockJudge, read_paper
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.base import ProviderResult


class _JudgeLLM:
    def generate(self, system: str, prompt: str) -> ProviderResult:
        payload = {
            "dimensions": {dim: 7 for dim in DIMENSIONS},
            "comments": {"writing": "clear and well-structured"},
            "revision_suggestions": ["Add a real sensitivity analysis."],
        }
        return ProviderResult(content="```json\n" + json.dumps(payload) + "\n```", metadata={})


def test_mock_judge_llm_scores_all_dimensions() -> None:
    score = MockJudge(_JudgeLLM()).score("paper text", figure_count=8, language="en")

    assert set(score.dimensions) == set(DIMENSIONS)
    assert all(0 <= v <= 10 for v in score.dimensions.values())
    assert score.total > 0
    assert score.revision_suggestions


def test_mock_judge_heuristic_rewards_richer_paper() -> None:
    rich = MockJudge(None).score(
        "\\section*{Abstract} a strong summary with results. "
        "\\section{Introduction} x \\section{Model} y \\section{Results} z "
        "\\begin{tabular}{ll}\\end{tabular} sensitivity analysis robustness " * 5,
        figure_count=10,
        language="en",
    )
    poor = MockJudge(None).score("\\section*{Abstract} short", figure_count=0, language="en")

    assert set(rich.dimensions) == set(DIMENSIONS)
    assert rich.total > poor.total


def test_read_paper_collects_sections_and_figure_count(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "w").root
    (root / "paper" / "sections").mkdir(parents=True, exist_ok=True)
    (root / "paper" / "sections" / "abstract.tex").write_text("\\section*{Abstract} hi", encoding="utf-8")
    (root / "figures").mkdir(exist_ok=True)
    (root / "figures" / "a.pdf").write_bytes(b"%PDF")
    (root / "figures" / "b.png").write_bytes(b"x")

    text, figure_count = read_paper(root)

    assert "Abstract" in text
    assert figure_count == 2


# ---------------------------------------------------------------------------
# score_consensus tests
# ---------------------------------------------------------------------------

class _CounterJudgeLLM:
    """Fake LLM that returns a different 'figures' dim per call (2, 4, 6 on calls 1-3).
    All other dims are constant at 5. Tracks call count."""

    def __init__(self) -> None:
        self.call_count = 0
        self._figures_seq = [2, 4, 6]

    def generate(self, system: str, prompt: str) -> "ProviderResult":
        figures_val = self._figures_seq[self.call_count % len(self._figures_seq)]
        self.call_count += 1
        dims = {dim: 5 for dim in DIMENSIONS}
        dims["figures"] = figures_val
        payload = {
            "dimensions": dims,
            "comments": {"figures": f"figure comment {self.call_count}"},
            "revision_suggestions": [f"suggestion {self.call_count}"],
        }
        from mcm_agent.providers.base import ProviderResult
        return ProviderResult(content="```json\n" + json.dumps(payload) + "\n```", metadata={})


def test_score_consensus_averages_dimensions() -> None:
    fake_llm = _CounterJudgeLLM()
    judge = MockJudge(fake_llm)
    result = judge.score_consensus("some paper text", samples=3)

    # figures values across 3 calls: [2, 4, 6] → mean = 4.0 → rounded int = 4
    assert result.dimensions["figures"] == 4
    # all other dims are constant 5 → mean = 5
    for dim in DIMENSIONS:
        if dim != "figures":
            assert result.dimensions[dim] == 5
    # fake LLM should be called exactly 3 times
    assert fake_llm.call_count == 3


def test_score_consensus_without_llm_equals_single() -> None:
    text = "\\section*{Abstract} some paper content with model and data"
    judge = MockJudge(None)
    single = judge.score(text)
    consensus = judge.score_consensus(text)

    assert consensus.dimensions == single.dimensions


def test_score_consensus_samples_less_than_1_treated_as_1() -> None:
    fake_llm = _CounterJudgeLLM()
    judge = MockJudge(fake_llm)
    result = judge.score_consensus("paper text", samples=0)

    # samples=0 → treated as 1 → only 1 call
    assert fake_llm.call_count == 1
    # figures value from call 1 = 2
    assert result.dimensions["figures"] == 2


def test_judge_prompt_demands_completeness_scaling() -> None:
    """The judge system prompt must contain an explicit completeness-gate directive
    so that a paper answering only 1-of-4 tasks cannot receive a high problem_coverage.

    We test *prompt construction* (not LLM output) because unit tests cannot drive
    a real model.  Key requirements:
    - Mentions "tasks" or "sub-questions" (the unit of completeness)
    - References proportional / A/T-style scaling
    - States that papers answering only SOME tasks MUST receive a lower score
    - Uses the word "problem_coverage" (ties the directive to the specific dimension)
    """
    system_text = MockJudge()._system()
    # The directive must name the dimension it governs
    assert "problem_coverage" in system_text
    # Must reference the concept of counting tasks/sub-questions
    assert any(kw in system_text for kw in ("tasks", "sub-question", "sub-tasks", "subtask"))
    # Must convey proportional scaling (A/T ratio or the word proportional)
    assert any(kw in system_text for kw in ("proportional", "A/T", "A / T"))
    # Must convey that answering only some tasks forces the score down
    assert any(kw in system_text for kw in ("only some", "MUST", "must"))


def test_judge_prompt_sees_later_sections_beyond_old_12k_cap() -> None:
    """Regression: the judge must read the WHOLE paper. A substantive paper's
    model/results/sensitivity sections sit beyond char 12000; the old cap made the
    judge blind to them (under-scoring + misrouting O6)."""
    from mcm_agent.agents.mock_judge import MockJudge, MAX_JUDGE_PAPER_CHARS
    assert MAX_JUDGE_PAPER_CHARS >= 40000
    paper = ("A" * 20000) + "\nSENSITIVITY_MARKER_BEYOND_12K\n" + ("B" * 5000)
    prompt = MockJudge()._prompt(paper, figure_count=4)
    assert "SENSITIVITY_MARKER_BEYOND_12K" in prompt


# ---------------------------------------------------------------------------
# Task J2: Anchored relative-scoring mode tests
# ---------------------------------------------------------------------------


class _RecordingLLM:
    """Fake LLM that captures the system + prompt and returns a fixed valid score."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> "ProviderResult":
        from mcm_agent.providers.base import ProviderResult
        self.calls.append((system, prompt))
        payload = {
            "dimensions": {dim: 8 for dim in DIMENSIONS},
            "comments": {"_mode": "anchored", "writing": "clear"},
            "revision_suggestions": [],
        }
        return ProviderResult(content="```json\n" + json.dumps(payload) + "\n```", metadata={})


def test_anchored_mode_uses_reference(tmp_path: Path, monkeypatch) -> None:
    """When kb_dir + problem_type are provided and build_reference_block returns non-empty,
    score() should use the anchored prompt (containing ref text, relative band wording,
    and evidence/cite requirement) and set comments['_mode'] == 'anchored'."""
    import mcm_agent.agents.mock_judge as mj_module

    ref_text = "REF: model=Bayesian; won for rigorous validation"
    monkeypatch.setattr(mj_module, "build_reference_block", lambda *a, **kw: ref_text)

    fake_llm = _RecordingLLM()
    judge = MockJudge(fake_llm, kb_dir=tmp_path, embedding=object())
    result = judge.score("candidate paper text", problem_type="data")

    assert fake_llm.calls, "LLM should have been called"
    system_text, prompt_text = fake_llm.calls[0]

    # Prompt must contain the reference block
    assert ref_text in prompt_text, "Prompt must include the reference block"

    # System must contain relative band wording (9-10 band)
    assert "9-10" in system_text or "9–10" in system_text, (
        "System prompt must mention the 9-10 relative scoring band"
    )

    # System must demand evidence / cite grounding
    assert any(kw in system_text.lower() for kw in ("evidence", "cite", "citing", "citation")), (
        "System prompt must require evidence-grounded scoring"
    )

    # Mode must be anchored
    assert result.comments.get("_mode") == "anchored", (
        f"Expected _mode='anchored', got {result.comments.get('_mode')!r}"
    )


def test_absolute_fallback_without_kb(monkeypatch) -> None:
    """When no kb_dir is provided, score() must use the absolute prompt and
    set comments['_mode'] containing 'absolute'."""
    import mcm_agent.agents.mock_judge as mj_module

    # Ensure build_reference_block is NOT called (if it were, the test would fail)
    called = []
    monkeypatch.setattr(mj_module, "build_reference_block", lambda *a, **kw: called.append(1) or "")

    fake_llm = _RecordingLLM()
    judge = MockJudge(fake_llm)  # no kb_dir
    result = judge.score("some paper text")

    assert fake_llm.calls, "LLM should have been called"
    assert not called, "build_reference_block should NOT be called when no kb_dir"

    mode = result.comments.get("_mode", "")
    assert "absolute" in mode, (
        f"Expected _mode to contain 'absolute', got {mode!r}"
    )


def test_anchored_falls_back_on_empty_reference(tmp_path: Path, monkeypatch) -> None:
    """When build_reference_block returns empty string, score() must fall back to
    absolute mode without crashing."""
    import mcm_agent.agents.mock_judge as mj_module

    monkeypatch.setattr(mj_module, "build_reference_block", lambda *a, **kw: "")

    fake_llm = _RecordingLLM()
    judge = MockJudge(fake_llm, kb_dir=tmp_path, embedding=object())
    result = judge.score("some paper text", problem_type="data")

    mode = result.comments.get("_mode", "")
    assert "absolute" in mode, (
        f"Expected fallback to absolute mode when ref is empty, got {mode!r}"
    )


def test_score_consensus_forwards_problem_type(tmp_path: Path, monkeypatch) -> None:
    """score_consensus must forward problem_type (and exclude_paper_id) to each score() call,
    so the anchored path is taken when ref is non-empty."""
    import mcm_agent.agents.mock_judge as mj_module

    ref_text = "REF: anchored reference for consensus test"
    monkeypatch.setattr(mj_module, "build_reference_block", lambda *a, **kw: ref_text)

    fake_llm = _RecordingLLM()
    judge = MockJudge(fake_llm, kb_dir=tmp_path, embedding=object())
    result = judge.score_consensus(
        "some paper text",
        samples=2,
        problem_type="data",
        exclude_paper_id="paper_001",
    )

    # All calls should have used the anchored path
    assert len(fake_llm.calls) == 2, f"Expected 2 calls, got {len(fake_llm.calls)}"
    for system_text, prompt_text in fake_llm.calls:
        assert ref_text in prompt_text, "Each consensus call must include the reference"

    # The representative sample's _mode should be 'anchored'
    assert result.comments.get("_mode") == "anchored", (
        f"Consensus result should carry _mode='anchored', got {result.comments.get('_mode')!r}"
    )
