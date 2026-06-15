from __future__ import annotations

import re
from pathlib import Path

from mcm_agent.agents.paper_context import PaperContext, build_paper_context
from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.models import PaperClaimPlanItem
from mcm_agent.utils.json_io import read_json, write_json


class ClaimPlanningAgent:
    def run(self, workspace_root: Path) -> None:
        route_summary = read_json(workspace_root / "results" / "model_route_summary.json", {})
        evidence = self._verified_evidence(
            read_json(workspace_root / "results" / "evidence_registry.json", [])
        )
        figures = self._approved_figures(
            read_json(workspace_root / "figures" / "figure_registry.json", [])
        )
        sources = self._rows(read_json(workspace_root / "data" / "source_registry.json", []))
        validation_text = self._read_text(workspace_root / "reports" / "validation_report.md")
        context = build_paper_context(workspace_root)

        claims: list[PaperClaimPlanItem] = []
        claims.extend(self._assumption_claims(context, evidence, sources))
        claims.extend(self._model_claims(route_summary, evidence, figures, sources, context))
        claims.extend(self._metric_claims(evidence, figures, sources))
        claims.extend(self._figure_claims(figures))
        claims.extend(self._sensitivity_claims(evidence, figures, sources, context))
        claims.extend(self._limitation_claims(validation_text, evidence, sources, context))
        claims.append(self._conclusion_claim(evidence, figures, sources, context))

        deduped = self._dedupe_claims(claims)
        write_json(
            workspace_root / "paper" / "claim_plan.json",
            [item.model_dump() for item in deduped],
        )
        self._write_report(workspace_root, deduped)
        Coordinator(workspace_root).emit(
            "paper.claim_plan.ready",
            payload={"artifact_ids": ["paper_claim_plan_v1"]},
            source="ClaimPlanningAgent",
        )

    def _assumption_claims(
        self,
        context: PaperContext,
        evidence: list[dict[str, object]],
        sources: list[dict[str, object]],
    ) -> list[PaperClaimPlanItem]:
        evidence_ids = self._ids(evidence[:1], "evidence_id")
        source_ids = self._ids(sources[:1], "source_id")
        if not (evidence_ids or source_ids):
            return []
        context_text = (
            context.problem_summary
            or "The model uses explicit assumptions to connect problem conditions to computable variables."
        )
        return [
            PaperClaimPlanItem(
                claim_id="claim_assumption_problem_context",
                section="paper/sections/assumptions.tex",
                claim_text=(
                    "The modeling assumptions are grounded in the problem context: "
                    + context_text
                ),
                claim_type="assumption",
                evidence_ids=evidence_ids,
                source_ids=source_ids,
                priority="major",
            )
        ]

    def _model_claims(
        self,
        route_summary: object,
        evidence: list[dict[str, object]],
        figures: list[dict[str, object]],
        sources: list[dict[str, object]],
        context: PaperContext,
    ) -> list[PaperClaimPlanItem]:
        if not isinstance(route_summary, dict):
            return []
        routes = route_summary.get("selected_routes", [])
        if not isinstance(routes, list) or not routes:
            return []
        route_text = " + ".join(str(route) for route in routes)
        evidence_ids = self._ids(evidence[:1], "evidence_id")
        figure_ids = self._ids(figures[:1], "figure_id")
        source_ids = self._ids(sources[:1], "source_id")
        decision_text = (
            f" The model decision context is: {context.model_decision_summary}"
            if context.model_decision_summary
            else ""
        )
        if evidence_ids or figure_ids or source_ids:
            return [
                PaperClaimPlanItem(
                    claim_id="claim_model_route",
                    section="paper/sections/model.tex",
                    claim_text=f"The selected model route is {route_text}.{decision_text}",
                    claim_type="model_choice",
                    evidence_ids=evidence_ids,
                    figure_ids=figure_ids,
                    source_ids=source_ids,
                    priority="critical",
                )
            ]
        return [
                PaperClaimPlanItem(
                    claim_id="claim_model_route",
                    section="paper/sections/model.tex",
                    claim_text=f"The selected model route is {route_text}.{decision_text}",
                    claim_type="model_choice",
                    priority="critical",
                    status="unresolved",
                unresolved_reason=(
                    "Missing verified evidence, figure, or source for the selected model route."
                ),
            )
        ]

    def _metric_claims(
        self,
        evidence: list[dict[str, object]],
        figures: list[dict[str, object]],
        sources: list[dict[str, object]],
    ) -> list[PaperClaimPlanItem]:
        claims = []
        fallback_figure_ids = self._ids(figures[:1], "figure_id")
        fallback_source_ids = self._ids(sources[:1], "source_id")
        for item in evidence:
            evidence_id = str(item.get("evidence_id", ""))
            if not evidence_id:
                continue
            claims.append(
                PaperClaimPlanItem(
                    claim_id="claim_" + self._safe_id(evidence_id),
                    section="paper/sections/results.tex",
                    claim_text=str(
                        item.get(
                            "claim",
                            f"Evidence {evidence_id} supports a reported result.",
                        )
                    ),
                    claim_type="metric_result",
                    evidence_ids=[evidence_id],
                    figure_ids=(
                        self._figure_ids_for_evidence(figures, evidence_id)
                        or fallback_figure_ids
                    ),
                    source_ids=(
                        self._source_ids_for_evidence(figures, evidence_id)
                        or fallback_source_ids
                    ),
                    priority="major",
                )
            )
        return claims

    def _figure_claims(self, figures: list[dict[str, object]]) -> list[PaperClaimPlanItem]:
        claims = []
        for item in figures:
            figure_id = str(item.get("figure_id", ""))
            claim_supported = str(item.get("claim_supported", "")).strip()
            if not figure_id or not claim_supported:
                continue
            used_in = item.get("used_in")
            section = (
                str(used_in[0])
                if isinstance(used_in, list) and used_in
                else "paper/sections/results.tex"
            )
            claims.append(
                PaperClaimPlanItem(
                    claim_id="claim_" + self._safe_id(figure_id),
                    section=section,
                    claim_text=claim_supported,
                    claim_type="metric_result",
                    evidence_ids=self._list_values(item.get("evidence_ids")),
                    figure_ids=[figure_id],
                    source_ids=self._list_values(item.get("source_ids")),
                    priority="supporting",
                )
            )
        return claims

    def _sensitivity_claims(
        self,
        evidence: list[dict[str, object]],
        figures: list[dict[str, object]],
        sources: list[dict[str, object]],
        context: PaperContext,
    ) -> list[PaperClaimPlanItem]:
        evidence_ids = self._ids(evidence[:1], "evidence_id")
        if not evidence_ids:
            return []
        route_metrics = ", ".join(context.route_metric_names[:3])
        metric_phrase = (
            f" for route metrics {route_metrics}"
            if route_metrics
            else ""
        )
        return [
            PaperClaimPlanItem(
                claim_id="claim_sensitivity_baseline",
                section="paper/sections/sensitivity.tex",
                claim_text=(
                    "Sensitivity analysis uses registered evidence as the baseline "
                    f"for robustness interpretation{metric_phrase}."
                ),
                claim_type="sensitivity",
                evidence_ids=evidence_ids,
                figure_ids=self._ids(figures[:1], "figure_id"),
                source_ids=self._ids(sources[:1], "source_id"),
                priority="major",
            )
        ]

    def _limitation_claims(
        self,
        validation_text: str,
        evidence: list[dict[str, object]],
        sources: list[dict[str, object]],
        context: PaperContext,
    ) -> list[PaperClaimPlanItem]:
        limitation_text = context.validation_summary or validation_text
        lowered = limitation_text.lower()
        if not any(token in lowered for token in ("unresolved", "limitation", "missing", "weak")):
            return []
        return [
            PaperClaimPlanItem(
                claim_id="claim_validation_limitation",
                section="paper/sections/sensitivity.tex",
                claim_text=(
                    "The validation stage records remaining limitations that constrain "
                    f"interpretation: {limitation_text}"
                ),
                claim_type="limitation",
                evidence_ids=self._ids(evidence[:1], "evidence_id"),
                source_ids=self._ids(sources[:1], "source_id"),
                priority="major",
                status="unresolved",
                unresolved_reason=(
                    "Validation report contains limitation language that requires explicit discussion."
                ),
            )
        ]

    def _conclusion_claim(
        self,
        evidence: list[dict[str, object]],
        figures: list[dict[str, object]],
        sources: list[dict[str, object]],
        context: PaperContext,
    ) -> PaperClaimPlanItem:
        evidence_ids = self._ids(evidence[:1], "evidence_id")
        figure_ids = self._ids(figures[:1], "figure_id")
        source_ids = self._ids(sources[:1], "source_id")
        route_phrase = (
            " for " + " + ".join(context.selected_routes)
            if context.selected_routes
            else ""
        )
        if evidence_ids or figure_ids or source_ids:
            return PaperClaimPlanItem(
                claim_id="claim_conclusion_traceability",
                section="paper/sections/conclusion.tex",
                claim_text=(
                    f"The final recommendation{route_phrase} is traceable to registered evidence, "
                    "figures, and sources."
                ),
                claim_type="conclusion",
                evidence_ids=evidence_ids,
                figure_ids=figure_ids,
                source_ids=source_ids,
                priority="critical",
            )
        return PaperClaimPlanItem(
            claim_id="claim_conclusion_traceability",
            section="paper/sections/conclusion.tex",
            claim_text=(
                f"The final recommendation{route_phrase} is traceable to registered evidence, "
                "figures, and sources."
            ),
            claim_type="conclusion",
            priority="critical",
            status="unresolved",
            unresolved_reason=(
                "Missing verified evidence, approved figure, or registered source for final conclusion."
            ),
        )

    def _verified_evidence(self, rows: object) -> list[dict[str, object]]:
        return [
            row
            for row in self._rows(rows)
            if row.get("evidence_id") and row.get("verified", True) is not False
        ]

    def _approved_figures(self, rows: object) -> list[dict[str, object]]:
        return [
            row
            for row in self._rows(rows)
            if row.get("figure_id") and str(row.get("status", "approved")) != "rejected"
        ]

    def _rows(self, rows: object) -> list[dict[str, object]]:
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    def _ids(self, rows: list[dict[str, object]], key: str) -> list[str]:
        return [str(row[key]) for row in rows if row.get(key)]

    def _figure_ids_for_evidence(
        self,
        figures: list[dict[str, object]],
        evidence_id: str,
    ) -> list[str]:
        return [
            str(figure["figure_id"])
            for figure in figures
            if evidence_id in self._list_values(figure.get("evidence_ids"))
            and figure.get("figure_id")
        ]

    def _source_ids_for_evidence(
        self,
        figures: list[dict[str, object]],
        evidence_id: str,
    ) -> list[str]:
        source_ids: list[str] = []
        for figure in figures:
            if evidence_id in self._list_values(figure.get("evidence_ids")):
                source_ids.extend(self._list_values(figure.get("source_ids")))
        return list(dict.fromkeys(source_ids))

    def _list_values(self, value: object) -> list[str]:
        return [str(item) for item in value if item] if isinstance(value, list) else []

    def _safe_id(self, value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")

    def _read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _dedupe_claims(self, claims: list[PaperClaimPlanItem]) -> list[PaperClaimPlanItem]:
        deduped: dict[str, PaperClaimPlanItem] = {}
        for claim in claims:
            deduped.setdefault(claim.claim_id, claim)
        return list(deduped.values())

    def _write_report(self, workspace_root: Path, claims: list[PaperClaimPlanItem]) -> None:
        unresolved = [claim for claim in claims if claim.status == "unresolved"]
        lines = [
            "# Claim Plan Report",
            "",
            f"Planned claims: {len(claims)}",
            f"Unresolved claims: {len(unresolved)}",
            "",
            "## Claims",
        ]
        for claim in claims:
            lines.append(
                f"- `{claim.claim_id}` ({claim.priority}, {claim.status}) -> `{claim.section}`"
            )
            lines.append(f"  - {claim.claim_text}")
            if claim.unresolved_reason:
                lines.append(f"  - unresolved_reason: {claim.unresolved_reason}")
        (workspace_root / "review" / "claim_plan_report.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
