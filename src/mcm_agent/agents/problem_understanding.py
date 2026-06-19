from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.models import ArtifactRecord, ArtifactStatus
from mcm_agent.core.registry import ArtifactRegistry
from mcm_agent.providers.base import TextGenerationProvider


REQUIRED_HEADINGS = [
    "# 题意理解报告",
    "## 题目背景",
    "## 子问题拆解",
    "## 输入与输出",
    "## 约束条件",
    "## 评价指标",
    "## 模糊表述与歧义",
    "## 隐含条件",
    "## 初步建模方向",
    "## 需要用户确认的问题",
]


def validate_required_headings(report: str) -> None:
    for heading in REQUIRED_HEADINGS:
        if heading not in report:
            raise ValueError(f"problem understanding report missing heading: {heading}")


class ProblemUnderstandingAgent:
    def __init__(self, llm_provider: TextGenerationProvider | None = None) -> None:
        self.llm_provider = llm_provider

    def run(self, workspace_root: Path) -> None:
        parsed_problem = workspace_root / "parsed" / "problem.md"
        if not parsed_problem.exists():
            raise FileNotFoundError("missing parsed/problem.md")

        problem_text = parsed_problem.read_text(encoding="utf-8").strip()
        report = self._build_report_with_llm(problem_text)
        validate_required_headings(report)

        output_path = workspace_root / "reports" / "problem_understanding.md"
        output_path.write_text(report, encoding="utf-8")

        registry = ArtifactRegistry(workspace_root / "artifact_registry.json")
        record = ArtifactRecord(
            artifact_id="problem_understanding_v1",
            type="problem_understanding_report",
            path="reports/problem_understanding.md",
            producer="ProblemUnderstandingAgent",
            depends_on=["parsed_problem_v1"],
            status=ArtifactStatus.REVIEW_REQUIRED,
            created_at=datetime.now(UTC),
            quality_checks=["required_headings_present"],
        )
        try:
            registry.add(record)
        except ValueError:
            registry.update_status("problem_understanding_v1", ArtifactStatus.REVIEW_REQUIRED)

        Coordinator(workspace_root).emit(
            "problem.understanding.ready",
            payload={"artifact_ids": ["problem_understanding_v1"]},
            source="ProblemUnderstandingAgent",
        )

    def _build_report_with_llm(self, problem_text: str) -> str:
        if self.llm_provider is None:
            return self._build_report(problem_text)

        prompt = "\n".join(
            [
                "problem_understanding",
                "",
                "Write a structured MCM/ICM problem understanding report in Chinese headings.",
                "Keep the following headings exactly and fill every section with concrete content:",
                *REQUIRED_HEADINGS,
                "",
                "Problem statement:",
                problem_text,
            ]
        )
        try:
            report = self.llm_provider.generate(
                "You are a senior mathematical modeling competition advisor.",
                prompt,
                temperature=0.2,
            ).content.strip()
            report = self._strip_preamble(report)
            validate_required_headings(report)
            return report
        except Exception as exc:
            fallback = self._build_report(problem_text)
            return fallback + f"\n<!-- LLM fallback reason: {type(exc).__name__} -->\n"

    @staticmethod
    def _strip_preamble(report: str) -> str:
        """Drop conversational preamble / code fences before the first markdown heading.

        LLMs often prefix reports with "好的，作为一名..." chatter that then pollutes the
        abstract/introduction summaries. Keep only from the first heading onward.
        """
        text = report.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else ""
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3].rstrip()
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if line.lstrip().startswith("#"):
                return "\n".join(lines[index:]).strip()
        return text.strip()

    def _build_report(self, problem_text: str) -> str:
        excerpt = problem_text[:800] if problem_text else "No parsed problem text available."
        return "\n".join(
            [
                "# 题意理解报告",
                "",
                "## 题目背景",
                excerpt,
                "",
                "## 子问题拆解",
                "- Identify the required modeling tasks from the problem statement.",
                "- Separate prediction, evaluation, and optimization objectives when present.",
                "",
                "## 输入与输出",
                "- Input: parsed problem statement and available attachments.",
                "- Output: model decisions, executable experiments, figures, and paper sections.",
                "",
                "## 约束条件",
                "- Respect contest formatting and data availability constraints.",
                "",
                "## 评价指标",
                "- Use task-specific predictive, optimization, or evaluation metrics.",
                "",
                "## 模糊表述与歧义",
                "- Confirm ambiguous targets, time ranges, and evaluation criteria with the user.",
                "",
                "## 隐含条件",
                "- Results must be reproducible and supported by registered evidence.",
                "",
                "## 初步建模方向",
                "- Start with interpretable baselines, then add complexity only when supported.",
                "",
                "## 需要用户确认的问题",
                "- Should the system prioritize explainability, accuracy, speed, or visual polish?",
                "",
            ]
        )
