from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from mcm_agent.core.models import TaskState
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
    "data/source_registry.json",
    "results/evidence_registry.json",
    "figures/figure_plan.json",
    "figures/figure_registry.json",
]

EMPTY_TEXT_FILES = {
    "event_log.jsonl": "",
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
