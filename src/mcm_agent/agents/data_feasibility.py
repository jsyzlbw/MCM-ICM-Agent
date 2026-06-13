from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.models import RetrievalLogEntry
from mcm_agent.core.stage_policy import DataAvailabilityDecision, route_data_availability
from mcm_agent.providers.search import SearchProvider, SearchResult
from mcm_agent.utils.json_io import append_jsonl, read_json, write_json


PRIVATE_DATA_MARKERS = [
    "salary",
    "salaries",
    "bonus",
    "bonuses",
    "contract",
    "compensation",
    "wage",
    "wages",
    "payroll",
]


class DataFeasibilityScoutAgent:
    def __init__(self, search_provider: SearchProvider) -> None:
        self.search_provider = search_provider

    def run(self, workspace_root: Path) -> None:
        problem_report = workspace_root / "reports" / "problem_understanding.md"
        if not problem_report.exists():
            raise FileNotFoundError("missing reports/problem_understanding.md")

        problem_text = problem_report.read_text(encoding="utf-8")
        target_dataset = self._target_dataset_from_discussion(workspace_root) or self._infer_target_dataset(
            problem_text
        )
        query = f"{target_dataset} public dataset official"
        results = self.search_provider.search(query, max_results=5)
        append_jsonl(
            workspace_root / "data" / "retrieval_log.jsonl",
            RetrievalLogEntry(
                time=datetime.now(UTC),
                provider=self.search_provider.__class__.__name__,
                query=query,
                top_urls=[result.url for result in results],
                decision="data_feasibility_probe",
            ).model_dump(mode="json"),
        )

        availability = self._classify_availability(problem_text, results, target_dataset)
        route = route_data_availability(availability)

        report_path = workspace_root / "reports" / "data_feasibility_report.md"
        report_path.write_text(
            self._build_report(availability, route.recommendation, results),
            encoding="utf-8",
        )
        write_json(
            workspace_root / "reports" / "data_feasibility_decision.json",
            {
                "availability": availability.model_dump(mode="json"),
                "route": route.model_dump(mode="json"),
                "top_results": [result.model_dump(mode="json") for result in results],
            },
        )

        event_type = (
            "data.feasibility.reframe_required"
            if route.next_stage == "research_reframing"
            else "data.feasibility.ready"
        )
        Coordinator(workspace_root).emit(
            event_type,
            payload={"next_stage": route.next_stage},
            source="DataFeasibilityScoutAgent",
        )

    def _infer_target_dataset(self, problem_text: str) -> str:
        lowered = problem_text.lower()
        if "football" in lowered and any(marker in lowered for marker in PRIVATE_DATA_MARKERS):
            return "football player salary and bonus contracts"
        if "climate" in lowered:
            return "public climate data"
        if "population" in lowered:
            return "public population data"
        return "problem-specific modeling data"

    def _target_dataset_from_discussion(self, workspace_root: Path) -> str | None:
        questions = read_json(workspace_root / "discussion" / "data_questions.json", [])
        if not questions:
            return None
        return str(questions[0])

    def _classify_availability(
        self,
        problem_text: str,
        results: list[SearchResult],
        target_dataset: str | None = None,
    ) -> DataAvailabilityDecision:
        target_dataset = target_dataset or self._infer_target_dataset(problem_text)
        lowered = f"{problem_text} {target_dataset}".lower()
        private_signal = any(marker in lowered for marker in PRIVATE_DATA_MARKERS)
        official_result = any(
            marker in result.url for result in results for marker in [".gov", "data.gov", ".edu"]
        )
        if private_signal and not official_result:
            return DataAvailabilityDecision(
                target_dataset=target_dataset,
                availability="private_or_unavailable",
                confidence=0.9,
                reason="The problem appears to require salary, bonus, contract, or compensation data.",
            )
        if official_result:
            return DataAvailabilityDecision(
                target_dataset=target_dataset,
                availability="available",
                confidence=0.75,
                reason="At least one official or institutional result was found in the early probe.",
            )
        return DataAvailabilityDecision(
            target_dataset=target_dataset,
            availability="unknown",
            confidence=0.55,
            reason="The early probe did not find an official source, but the data need is not clearly private.",
        )

    def _build_report(
        self,
        availability: DataAvailabilityDecision,
        recommendation: str,
        results: list[SearchResult],
    ) -> str:
        lines = [
            "# Data Feasibility Report",
            "",
            "## Target Dataset",
            availability.target_dataset,
            "",
            "## Availability",
            availability.availability,
            "",
            "## Reason",
            availability.reason,
            "",
            "## Recommendation",
            recommendation,
            "",
        ]
        if availability.availability == "private_or_unavailable":
            lines.extend(
                [
                    "## Proxy Variables",
                    "- Player performance statistics.",
                    "- Market value or transfer fee.",
                    "- Age, position, league strength, injury history, and playing time.",
                    "- Team revenue, ranking, attendance, or budget class.",
                    "",
                ]
            )
        lines.extend(["## Early Search Results", ""])
        if results:
            for result in results:
                lines.append(f"- {result.title}: {result.url}")
        else:
            lines.append("- No usable early search result.")
        return "\n".join(lines) + "\n"
