from mcm_agent.corpus.sections import section_chunks, segment_sections

SAMPLE = (
    """# Summary
We model tennis momentum.

## 1. Introduction and Restatement
Background here.

## 2. Assumptions and Justifications
- Assume players are independent.

## 3. Model Development
We build a Markov chain. (long body) """
    + ("x " * 2000)
    + """

## 4. Sensitivity Analysis
We vary alpha.

## 5. Strengths and Weaknesses
Strengths: robust.

## References
[1] Foo.
"""
)


def test_segment_classifies_canonical_sections():
    secs = segment_sections(SAMPLE)
    kinds = {s.section_type for s in secs}
    assert "summary" in kinds
    assert "assumptions" in kinds
    assert "model" in kinds
    assert "sensitivity" in kinds
    assert "strengths_weaknesses" in kinds
    assert "references" in kinds


def test_section_chunks_carry_type_and_split_long_bodies():
    chunks = section_chunks(SAMPLE)
    model_chunks = [c for c in chunks if c[0] == "model"]
    assert len(model_chunks) >= 2  # long model body split into multiple chunks
    assert all(isinstance(c[1], str) and c[1].strip() for c in chunks)


def test_no_headings_falls_back_to_other():
    secs = segment_sections("Just a blob of text with no headings at all.")
    assert len(secs) == 1 and secs[0].section_type == "other"
