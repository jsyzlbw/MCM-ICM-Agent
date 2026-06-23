import json

from mcm_agent.corpus.manifest import CorpusEntry
from mcm_agent.corpus.teardown import (
    generate_teardown,
    parse_card,
    render_card_text,
)


def _entry():
    return CorpusEntry(
        paper_id="2024-100", year=2024, contest="MCM", problem="C",
        problem_type="data", control_number="100", pdf_path="/x.pdf", source_repo="d",
    )


CARD_JSON = {
    "problem_summary": "Predict tennis momentum.",
    "models_used": ["Markov chain", "Kalman filter"],
    "key_techniques": ["hypothesis testing", "feature weighting"],
    "why_it_won": "Rigorous definition of momentum and strong validation.",
    "section_highlights": "Clear assumptions table and a coach-facing memo.",
    "pitfalls_or_limitations": ["ignores player health"],
    "reusable_patterns": ["state-space model for time-varying advantage"],
}


class _FakeLLM:
    def __init__(self, content):
        self._content = content

    def generate(self, system, prompt, *, temperature=0.2):
        class R:
            content = self._content
        return R()


def test_parse_card_plain_json():
    card = parse_card(json.dumps(CARD_JSON), _entry())
    assert card.paper_id == "2024-100" and card.problem_type == "data"
    assert card.models_used == ["Markov chain", "Kalman filter"]
    assert card.why_it_won.startswith("Rigorous")


def test_parse_card_tolerates_fences_and_prose():
    text = "Sure, here is the analysis:\n```json\n" + json.dumps(CARD_JSON) + "\n```\nHope that helps!"
    card = parse_card(text, _entry())
    assert card.models_used == ["Markov chain", "Kalman filter"]
    assert card.pitfalls_or_limitations == ["ignores player health"]


def test_parse_card_handles_garbage_gracefully():
    card = parse_card("the model could not produce json", _entry())
    assert card.paper_id == "2024-100"  # still a valid card, just empty fields
    assert card.models_used == []


def test_generate_teardown_uses_llm():
    card = generate_teardown("# Summary\n\nTennis paper", _entry(), _FakeLLM(json.dumps(CARD_JSON)))
    assert card.key_techniques == ["hypothesis testing", "feature weighting"]


def test_render_card_text_is_searchable_and_skips_empty():
    card = parse_card(json.dumps(CARD_JSON), _entry())
    text = render_card_text(card)
    assert "Markov chain" in text and "Why it won:" in text
    # an empty-field card renders only the header line
    sparse = parse_card("{}", _entry())
    assert "Models used:" not in render_card_text(sparse)
