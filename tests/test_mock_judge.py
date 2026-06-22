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


def test_judge_prompt_sees_later_sections_beyond_old_12k_cap() -> None:
    """Regression: the judge must read the WHOLE paper. A substantive paper's
    model/results/sensitivity sections sit beyond char 12000; the old cap made the
    judge blind to them (under-scoring + misrouting O6)."""
    from mcm_agent.agents.mock_judge import MockJudge, MAX_JUDGE_PAPER_CHARS
    assert MAX_JUDGE_PAPER_CHARS >= 40000
    paper = ("A" * 20000) + "\nSENSITIVITY_MARKER_BEYOND_12K\n" + ("B" * 5000)
    prompt = MockJudge()._prompt(paper, figure_count=4)
    assert "SENSITIVITY_MARKER_BEYOND_12K" in prompt
