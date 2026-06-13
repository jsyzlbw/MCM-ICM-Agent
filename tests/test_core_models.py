from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from mcm_agent.core.models import (
    ArtifactRecord,
    ArtifactStatus,
    EvidenceItem,
    FigurePlanItem,
    HandoffPacket,
    RetrievalLogEntry,
    TaskInput,
)


NOW = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)


def test_artifact_record_accepts_dependencies() -> None:
    record = ArtifactRecord(
        artifact_id="problem_understanding_v1",
        type="problem_understanding_report",
        path="reports/problem_understanding.md",
        producer="ProblemUnderstandingAgent",
        depends_on=["parsed_problem_v1"],
        status=ArtifactStatus.REVIEW_REQUIRED,
        created_at=NOW,
    )

    assert record.depends_on == ["parsed_problem_v1"]
    assert record.status == ArtifactStatus.REVIEW_REQUIRED


def test_task_input_defaults_to_english_unknown_competition(tmp_path: Path) -> None:
    task_input = TaskInput(problem_file=tmp_path / "problem.pdf")

    assert task_input.language == "en"
    assert task_input.competition == "unknown"
    assert task_input.attachments == []


def test_handoff_packet_requires_acceptance_criteria() -> None:
    with pytest.raises(ValidationError):
        HandoffPacket(
            handoff_id="handoff_001",
            from_agent="ModelJudge",
            to_agent="SolverCoderAgent",
            task="implement_problem_1",
            input_artifacts=["reports/model_decision.md"],
            expected_outputs=["code/problem1.py"],
            acceptance_criteria=[],
            created_at=NOW,
        )


def test_retrieval_log_requires_query_or_url() -> None:
    with pytest.raises(ValidationError):
        RetrievalLogEntry(
            time=NOW,
            provider="tavily",
            decision="missing query and url",
        )


def test_evidence_item_records_verified_code_output() -> None:
    item = EvidenceItem(
        evidence_id="q1_rmse_001",
        claim="The model achieves RMSE = 2.31.",
        value=2.31,
        source_type="code_output",
        source_path="results/problem1_metrics.json",
        generated_by="code/problem1.py",
        used_in=["paper/sections/results.tex"],
        verified=True,
    )

    assert item.verified is True


def test_figure_plan_item_rejects_raster_only_data_plot() -> None:
    with pytest.raises(ValidationError):
        FigurePlanItem(
            figure_id="fig_q1_prediction",
            purpose="show prediction performance",
            figure_type="data_plot",
            source_data=["results/problem1_predictions.csv"],
            generation_script="code/plot_problem1.py",
            output_formats=["png"],
            target_section="paper/sections/results.tex",
            caption_intent="Prediction performance comparison.",
        )
