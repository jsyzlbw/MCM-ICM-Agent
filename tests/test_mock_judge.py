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
