from pathlib import Path

import pytest
import respx
from httpx import Response

from mcm_agent.agents.compliance import ComplianceOriginalityAgent
from mcm_agent.providers.humanizer import FakeHumanizerProvider, UShallPassHumanizerProvider
from mcm_agent.utils.text_locks import extract_fact_locks


def test_extract_fact_locks_captures_numbers_citations_and_refs() -> None:
    locks = extract_fact_locks(
        "RMSE is 2.31 in Figure~\\ref{fig:q1} with \\cite{smith2024} and $y=x+1$."
    )

    assert "2.31" in locks.numbers
    assert "\\cite{smith2024}" in locks.citations
    assert "Figure~\\ref{fig:q1}" in locks.figure_refs
    assert "$y=x+1$" in locks.equations


def test_compliance_agent_rejects_humanized_paragraph_when_number_changes(tmp_path: Path) -> None:
    section_dir = tmp_path / "paper" / "sections"
    section_dir.mkdir(parents=True)
    (section_dir / "results.tex").write_text(
        "The model achieves RMSE 2.31 on the validation set.\n",
        encoding="utf-8",
    )
    (tmp_path / "review").mkdir()
    (tmp_path / "unresolved_issues.md").write_text("# Unresolved Issues\n", encoding="utf-8")

    provider = FakeHumanizerProvider(
        {"The model achieves RMSE 2.31 on the validation set.": "The model reaches RMSE 2.13 on validation."}
    )
    ComplianceOriginalityAgent(provider).run(tmp_path)

    content = (section_dir / "results.tex").read_text(encoding="utf-8")
    report = (tmp_path / "review" / "fact_regression_report.md").read_text(encoding="utf-8")
    assert "2.31" in content
    assert "critical" in report


def test_compliance_agent_accepts_safe_humanized_paragraph(tmp_path: Path) -> None:
    section_dir = tmp_path / "paper" / "sections"
    section_dir.mkdir(parents=True)
    (section_dir / "results.tex").write_text(
        "The model gives a stable qualitative pattern.\n",
        encoding="utf-8",
    )
    (tmp_path / "review").mkdir()
    (tmp_path / "unresolved_issues.md").write_text("# Unresolved Issues\n", encoding="utf-8")

    provider = FakeHumanizerProvider(
        {"The model gives a stable qualitative pattern.": "The model shows a stable qualitative pattern."}
    )
    ComplianceOriginalityAgent(provider).run(tmp_path)

    content = (section_dir / "results.tex").read_text(encoding="utf-8")
    assert "shows a stable" in content


@respx.mock
def test_ushallpass_provider_polls_nested_data_status() -> None:
    respx.post("https://leahloveswriting.xyz/api_v2/rewrite/english/jobs").mock(
        return_value=Response(200, json={"success": True, "data": {"task_id": "job_1"}})
    )
    respx.get("https://leahloveswriting.xyz/api_v2/rewrite/english/jobs/job_1").mock(
        return_value=Response(
            200,
            json={"success": True, "data": {"status": "completed", "result": "Human text."}},
        )
    )

    result = UShallPassHumanizerProvider(
        "key",
        poll_interval_seconds=0,
        max_poll_attempts=2,
    ).humanize("AI text.", language="en")

    assert result == "Human text."


@respx.mock
def test_ushallpass_provider_surfaces_failed_error_message() -> None:
    respx.post("https://leahloveswriting.xyz/api_v2/rewrite/chinese/jobs").mock(
        return_value=Response(200, json={"success": True, "data": {"task_id": "job_2"}})
    )
    respx.get("https://leahloveswriting.xyz/api_v2/rewrite/chinese/jobs/job_2").mock(
        return_value=Response(
            200,
            json={
                "success": True,
                "data": {
                    "status": "failed",
                    "error": {"code": "INVALID_PARAMETER", "message": "empty text"},
                },
            },
        )
    )

    with pytest.raises(RuntimeError, match="INVALID_PARAMETER: empty text"):
        UShallPassHumanizerProvider(
            "key",
            poll_interval_seconds=0,
            max_poll_attempts=2,
        ).humanize("文本", language="zh")
