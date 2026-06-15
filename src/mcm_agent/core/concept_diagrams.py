from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from mcm_agent.utils.json_io import read_json


class ConceptDiagramNode(BaseModel):
    node_id: str
    label: str
    kind: Literal["input", "process", "model", "evidence", "claim", "output"]


class ConceptDiagramEdge(BaseModel):
    source: str
    target: str
    label: str = ""


class ConceptDiagramSpec(BaseModel):
    diagram_id: str
    title: str
    target_section: str
    caption_intent: str
    claim_supported: str
    nodes: list[ConceptDiagramNode]
    edges: list[ConceptDiagramEdge]
    evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


def build_concept_diagram_specs(workspace_root: Path) -> list[ConceptDiagramSpec]:
    route_summary = read_json(workspace_root / "results" / "model_route_summary.json", {})
    claim_plan = read_json(workspace_root / "paper" / "claim_plan.json", [])
    evidence = read_json(workspace_root / "results" / "evidence_registry.json", [])
    sources = read_json(workspace_root / "data" / "source_registry.json", [])

    selected_routes = _selected_routes(route_summary)
    route_metric_names = _route_metric_names(route_summary)
    claims = _claim_rows(claim_plan)
    evidence_ids = _ids(evidence, "evidence_id")
    source_ids = _ids(sources, "source_id")
    claim_evidence_ids = _unique(
        evidence_id
        for claim in claims
        for evidence_id in _string_list(claim.get("evidence_ids"))
    )
    claim_source_ids = _unique(
        source_id
        for claim in claims
        for source_id in _string_list(claim.get("source_ids"))
    )

    return [
        _method_overview_spec(
            selected_routes=selected_routes,
            route_metric_names=route_metric_names,
            evidence_ids=claim_evidence_ids or evidence_ids,
            source_ids=claim_source_ids or source_ids,
        ),
        _claim_evidence_spec(
            claims=claims,
            evidence_ids=claim_evidence_ids or evidence_ids,
            source_ids=claim_source_ids or source_ids,
        ),
    ]


def _method_overview_spec(
    *,
    selected_routes: list[str],
    route_metric_names: list[str],
    evidence_ids: list[str],
    source_ids: list[str],
) -> ConceptDiagramSpec:
    routes = selected_routes or ["balanced_contest_route"]
    nodes = [
        ConceptDiagramNode(
            node_id="problem_context",
            label="Problem and data context",
            kind="input",
        ),
        ConceptDiagramNode(
            node_id="modeling_council",
            label="Modeling diagnosis",
            kind="process",
        ),
    ]
    edges = [
        ConceptDiagramEdge(
            source="problem_context",
            target="modeling_council",
            label="decompose",
        )
    ]
    previous = "modeling_council"
    for route in routes:
        node_id = _safe_id("route_" + route)
        nodes.append(ConceptDiagramNode(node_id=node_id, label=route, kind="model"))
        edges.append(ConceptDiagramEdge(source=previous, target=node_id, label="select"))
        previous = node_id

    evidence_label = (
        "Evidence: " + ", ".join(route_metric_names[:3])
        if route_metric_names
        else "Registered model evidence"
    )
    nodes.extend(
        [
            ConceptDiagramNode(
                node_id="solver_evidence",
                label=evidence_label,
                kind="evidence",
            ),
            ConceptDiagramNode(
                node_id="validation",
                label="Validation and figure QA",
                kind="process",
            ),
            ConceptDiagramNode(
                node_id="paper_claims",
                label="Claim-aware paper sections",
                kind="output",
            ),
        ]
    )
    edges.extend(
        [
            ConceptDiagramEdge(source=previous, target="solver_evidence", label="execute"),
            ConceptDiagramEdge(source="solver_evidence", target="validation", label="verify"),
            ConceptDiagramEdge(source="validation", target="paper_claims", label="write"),
        ]
    )
    return ConceptDiagramSpec(
        diagram_id="fig_method_overview",
        title="Method Overview",
        target_section="paper/sections/model.tex",
        caption_intent="Route-aware overview of the modeling workflow.",
        claim_supported="The method follows a reproducible route-to-evidence workflow.",
        nodes=nodes,
        edges=edges,
        evidence_ids=evidence_ids,
        source_ids=source_ids,
    )


def _claim_evidence_spec(
    *,
    claims: list[dict[str, object]],
    evidence_ids: list[str],
    source_ids: list[str],
) -> ConceptDiagramSpec:
    important_claims = claims[:4] or [
        {
            "claim_id": "claim_model_route",
            "section": "paper/sections/model.tex",
            "evidence_ids": evidence_ids[:2],
            "source_ids": source_ids[:2],
        }
    ]
    nodes = [
        ConceptDiagramNode(
            node_id="paper_claims",
            label="Planned paper claims",
            kind="claim",
        )
    ]
    edges: list[ConceptDiagramEdge] = []
    for index, claim in enumerate(important_claims, start=1):
        claim_id = str(claim.get("claim_id") or f"claim_{index}")
        claim_node = _safe_id("claim_" + claim_id)
        section = str(claim.get("section") or "paper/sections/model.tex")
        nodes.append(
            ConceptDiagramNode(
                node_id=claim_node,
                label=claim_id,
                kind="claim",
            )
        )
        nodes.append(
            ConceptDiagramNode(
                node_id=_safe_id("section_" + section),
                label=section,
                kind="output",
            )
        )
        edges.append(ConceptDiagramEdge(source="paper_claims", target=claim_node, label="plan"))
        edges.append(
            ConceptDiagramEdge(
                source=claim_node,
                target=_safe_id("section_" + section),
                label="write in",
            )
        )
        for evidence_id in _string_list(claim.get("evidence_ids"))[:2]:
            evidence_node = _safe_id("evidence_" + evidence_id)
            nodes.append(
                ConceptDiagramNode(
                    node_id=evidence_node,
                    label=evidence_id,
                    kind="evidence",
                )
            )
            edges.append(
                ConceptDiagramEdge(source=evidence_node, target=claim_node, label="supports")
            )
        for source_id in _string_list(claim.get("source_ids"))[:2]:
            source_node = _safe_id("source_" + source_id)
            nodes.append(
                ConceptDiagramNode(
                    node_id=source_node,
                    label=source_id,
                    kind="input",
                )
            )
            edges.append(ConceptDiagramEdge(source=source_node, target=claim_node, label="grounds"))

    return ConceptDiagramSpec(
        diagram_id="fig_claim_evidence_map",
        title="Claim Evidence Map",
        target_section="paper/sections/model.tex",
        caption_intent="Map from major paper claims to registered evidence and sources.",
        claim_supported="Important paper claims are traceable to registered support.",
        nodes=_dedupe_nodes(nodes),
        edges=edges,
        evidence_ids=evidence_ids,
        source_ids=source_ids,
    )


def _selected_routes(route_summary: object) -> list[str]:
    if not isinstance(route_summary, dict):
        return []
    selected = route_summary.get("selected_routes", [])
    if not isinstance(selected, list):
        return []
    return [str(route) for route in selected if str(route).strip()]


def _route_metric_names(route_summary: object) -> list[str]:
    if not isinstance(route_summary, dict):
        return []
    metrics = route_summary.get("route_metrics", {})
    if not isinstance(metrics, dict):
        return []
    return [str(key) for key in metrics]


def _claim_rows(claim_plan: object) -> list[dict[str, object]]:
    if not isinstance(claim_plan, list):
        return []
    rows = [item for item in claim_plan if isinstance(item, dict)]
    return [
        item
        for item in rows
        if str(item.get("priority", "")) in {"critical", "major"} or not item.get("priority")
    ]


def _ids(rows: object, key: str) -> list[str]:
    if not isinstance(rows, list):
        return []
    return _unique(
        str(row.get(key))
        for row in rows
        if isinstance(row, dict) and row.get(key)
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _unique(values: object) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def _dedupe_nodes(nodes: list[ConceptDiagramNode]) -> list[ConceptDiagramNode]:
    result: list[ConceptDiagramNode] = []
    seen: set[str] = set()
    for node in nodes:
        if node.node_id in seen:
            continue
        result.append(node)
        seen.add(node.node_id)
    return result


def _safe_id(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip())
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        return "node"
    if text[0].isdigit():
        return "node_" + text
    return text
