from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from mcm_agent.core.models import TaskState
from mcm_agent.core.workspace_models import WorkspaceMetadata, WorkspaceState
from mcm_agent.core.workspace_safety import WorkspaceSafety
from mcm_agent.core.workflow_graph import build_default_workflow_graph
from mcm_agent.utils.json_io import read_json, write_json

MAG_VERSION = "0.1.0"


@dataclass(frozen=True)
class Workspace:
    root: Path


DIRECTORIES = [
    ".mag/chat/sessions",
    ".mag/logs",
    ".mag/cache",
    "input/problem",
    "input/data",
    "input/layout",
    "input/notes",
    "knowledge/papers",
    "knowledge/methods",
    "knowledge/rules",
    "knowledge/cases",
    "work/parsed",
    "work/reports",
    "work/discussion",
    "work/data",
    "work/results",
    "work/figures",
    "work/paper",
    "work/review",
    "output/draft",
    "output/final",
    "output/package",
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
    ".env": "",
    ".mag/chat/messages.jsonl": "",
    ".mag/events.jsonl": "",
    "event_log.jsonl": "",
    "stage_runs.jsonl": "",
    "data/retrieval_log.jsonl": "",
    "results/experiment_runs.jsonl": "",
    "unresolved_issues.md": "# Unresolved Issues\n\n",
    "review/methodology_checklist_report.md": "# Methodology Checklist Report\n\n",
    "review/humanization_diff.md": "# Humanization Diff\n\n",
    "review/fact_regression_report.md": "# Fact Regression Report\n\n",
}


def is_mag_workspace(root: Path) -> bool:
    root = root.resolve()
    return (root / ".mag" / "workspace.json").exists() and (
        root / ".mag" / "state.json"
    ).exists()


def load_workspace_state(root: Path) -> WorkspaceState:
    payload = read_json(root.resolve() / ".mag" / "state.json", {})
    return WorkspaceState.model_validate(payload)


def save_workspace_state(root: Path, state: WorkspaceState) -> None:
    write_json(root.resolve() / ".mag" / "state.json", state.model_dump(mode="json"))


def create_workspace(root: Path) -> Workspace:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)

    for directory in DIRECTORIES:
        (root / directory).mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC)
    metadata_path = root / ".mag" / "workspace.json"
    state_path = root / ".mag" / "state.json"
    if not metadata_path.exists():
        write_json(
            metadata_path,
            WorkspaceMetadata(
                workspace_id=root.name,
                created_at=now,
                updated_at=now,
                mag_version=MAG_VERSION,
            ).model_dump(mode="json"),
        )
    if not state_path.exists():
        write_json(state_path, WorkspaceState().model_dump(mode="json"))
    config_path = root / ".mag" / "config.toml"
    if not config_path.exists():
        config_path.write_text(
            "\n".join(
                [
                    "[llm]",
                    'provider = "openai_compatible"',
                    'base_url = "https://api.openai.com/v1"',
                    'model = "gpt-4.1"',
                    "enabled = false",
                    "",
                    "[search]",
                    "enabled = false",
                    "",
                    "[git]",
                    "enabled = true",
                    "checkpoint = true",
                    "auto_push = false",
                    'remote = "origin"',
                    'branch = "main"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
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

    safety = WorkspaceSafety(root)
    safety.ensure_git_repo()
    safety.ensure_gitignore()
    safety.checkpoint("mag workspace initialized")

    return Workspace(root=root)
