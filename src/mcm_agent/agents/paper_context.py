from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from mcm_agent.utils.json_io import read_json


class PaperContext(BaseModel):
    problem_summary: str = ""
    direction_summary: str = ""
    model_decision_summary: str = ""
    validation_summary: str = ""
    selected_routes: list[str] = Field(default_factory=list)
    route_metric_names: list[str] = Field(default_factory=list)
    primary_evidence_ids: list[str] = Field(default_factory=list)
    primary_figure_ids: list[str] = Field(default_factory=list)
    primary_source_ids: list[str] = Field(default_factory=list)
    methodology_notes: list[str] = Field(default_factory=list)


def build_paper_context(workspace_root: Path) -> PaperContext:
    route_summary = read_json(workspace_root / "results" / "model_route_summary.json", {})
    evidence_rows = _rows(read_json(workspace_root / "results" / "evidence_registry.json", []))
    figure_rows = _rows(read_json(workspace_root / "figures" / "figure_registry.json", []))
    source_rows = _rows(read_json(workspace_root / "data" / "source_registry.json", []))
    rag_rows = _rows(read_json(workspace_root / "rag" / "methodology_hits.json", []))
    routes = route_summary.get("selected_routes", []) if isinstance(route_summary, dict) else []
    metrics = route_summary.get("route_metrics", {}) if isinstance(route_summary, dict) else {}
    return PaperContext(
        problem_summary=_summarize_problem(
            workspace_root / "reports" / "problem_understanding.md"
        ),
        direction_summary=_summarize_markdown(
            workspace_root / "discussion" / "confirmed_direction.md"
        ),
        model_decision_summary=_summarize_markdown(
            workspace_root / "reports" / "model_decision.md"
        ),
        validation_summary=_summarize_markdown(
            workspace_root / "reports" / "validation_report.md"
        ),
        selected_routes=[str(item) for item in routes] if isinstance(routes, list) else [],
        route_metric_names=[str(key) for key in metrics.keys()] if isinstance(metrics, dict) else [],
        primary_evidence_ids=_ids(evidence_rows, "evidence_id", limit=3),
        primary_figure_ids=_ids(figure_rows, "figure_id", limit=3),
        primary_source_ids=_ids(source_rows, "source_id", limit=3),
        methodology_notes=_methodology_notes(rag_rows, limit=5),
    )


def _summarize_problem(path: Path, *, max_chars: int = 200) -> str:
    """First sentence of the problem background — NOT a raw dump of the report.

    Prefers the paragraph under a "背景"/"background" heading; otherwise the first
    non-heading paragraph. Truncated to one sentence / ``max_chars``.
    """
    if not path.exists():
        return ""
    paragraph: list[str] = []
    in_background = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if paragraph:
                break
            heading = stripped.lstrip("# ").strip().lower()
            in_background = ("背景" in stripped) or ("background" in heading)
            continue
        if not stripped:
            if paragraph:
                break
            continue
        if in_background or not paragraph:
            paragraph.append(stripped)
    text = " ".join(paragraph).strip()
    if not text:
        return ""
    sentence = re.split(r"(?<=[。.!?！？])\s*", text)[0]
    return (sentence or text)[:max_chars]


def _summarize_markdown(path: Path, *, max_chars: int = 500) -> str:
    if not path.exists():
        return ""
    text = " ".join(
        line.strip("# ").strip() for line in path.read_text(encoding="utf-8").splitlines()
    )
    return " ".join(text.split())[:max_chars]


def _rows(value: object) -> list[dict[str, object]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _ids(rows: list[dict[str, object]], key: str, *, limit: int) -> list[str]:
    return [str(row[key]) for row in rows if row.get(key)][:limit]


def _methodology_notes(rows: list[dict[str, object]], *, limit: int) -> list[str]:
    notes: list[str] = []
    for row in rows[:limit]:
        title = str(row.get("title", "Methodology note"))
        content = str(row.get("content", "")).strip()
        if content:
            notes.append(f"{title}: {content[:240]}")
    return notes
