from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from mcm_agent.core.models import TaskState
from mcm_agent.core.workflow_graph import build_default_workflow_graph
from mcm_agent.utils.json_io import write_json


@dataclass(frozen=True)
class Workspace:
    root: Path


DIRECTORIES = [
    "input/attachments",
    "input/template",
    "parsed/tables",
    "parsed/images",
    "discussion",
    "rag/review_checklists",
    "reports",
    "data/raw",
    "data/external",
    "data/processed",
    "code",
    "results",
    "figures/source",
    "paper/sections",
    "review",
    "final_submission",
]

EMPTY_JSON_LIST_FILES = [
    "artifact_registry.json",
    "discussion/data_questions.json",
    "data/source_registry.json",
    "data/data_lineage.json",
    "data/citation_candidates.json",
    "results/evidence_registry.json",
    "figures/figure_plan.json",
    "figures/figure_registry.json",
    "review/gate_decisions.json",
]

EMPTY_TEXT_FILES = {
    "event_log.jsonl": "",
    "stage_runs.jsonl": "",
    "data/retrieval_log.jsonl": "",
    "unresolved_issues.md": "# Unresolved Issues\n\n",
    "review/methodology_checklist_report.md": "# Methodology Checklist Report\n\n",
    "review/humanization_diff.md": "# Humanization Diff\n\n",
    "review/fact_regression_report.md": "# Fact Regression Report\n\n",
}


def create_workspace(root: Path) -> Workspace:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)

    for directory in DIRECTORIES:
        (root / directory).mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC)
    state = TaskState(
        workspace_id=root.name,
        current_phase="initialized",
        created_at=now,
        updated_at=now,
    )
    write_json(root / "task_state.json", state.model_dump(mode="json"))
    graph = build_default_workflow_graph()
    write_json(
        root / "workflow_topology.json",
        {
            "nodes": {key: node.__dict__ for key, node in graph.nodes.items()},
            "edges": [edge.__dict__ for edge in graph.edges],
            "failure_routes": [
                {"from_node": key[0], "failure_reason": key[1], "to_node": value}
                for key, value in graph.failure_routes.items()
            ],
        },
    )

    for relative_path in EMPTY_JSON_LIST_FILES:
        path = root / relative_path
        if not path.exists():
            write_json(path, [])

    for relative_path, content in EMPTY_TEXT_FILES.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")

    return Workspace(root=root)
