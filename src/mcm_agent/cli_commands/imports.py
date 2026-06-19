from __future__ import annotations

from pathlib import Path

from mcm_agent.cli_commands.base import CommandContext, CommandResult
from mcm_agent.core.imports import copy_resource, record_import
from mcm_agent.core.workspace import load_workspace_state, save_workspace_state
from mcm_agent.core.workspace_safety import WorkspaceSafety
from mcm_agent.utils.json_io import append_jsonl


class ImportCommand:
    def __init__(self, name: str, summary: str, target: str, resource_type: str):
        self.name = name
        self.summary = summary
        self.target = target
        self.resource_type = resource_type

    def run(self, args: list[str], context: CommandContext) -> CommandResult:
        if not args:
            return CommandResult(f"Usage: /{self.name} <file-or-directory-path>")
        root = Path(context.workspace_root)
        resource = copy_resource(
            Path(" ".join(args)),
            root / self.target,
            self.resource_type,
        )
        record_import(root, resource)
        state = load_workspace_state(root)
        state.resources.append(resource)
        if self.resource_type == "problem":
            state.problem = str(Path(resource.workspace_path).relative_to(root))
            state.init.problem_imported = True
        elif self.resource_type == "data":
            state.init.data_files += 1
        elif self.resource_type == "layout":
            state.init.layout_imported = True
        save_workspace_state(root, state)
        WorkspaceSafety(root).checkpoint(f"mag: import {self.resource_type}")
        return CommandResult(f"Imported {self.resource_type}: {resource.workspace_path}")


class RagCommand:
    name = "rag"
    summary = "导入 RAG 文档。"

    _targets = {
        "papers": "knowledge/papers",
        "methods": "knowledge/methods",
        "rules": "knowledge/rules",
        "cases": "knowledge/cases",
    }

    def run(self, args: list[str], context: CommandContext) -> CommandResult:
        if len(args) < 2 or args[0] not in self._targets:
            return CommandResult("Usage: /rag <papers|methods|rules|cases> <file-path>")
        category = args[0]
        source = Path(" ".join(args[1:]))
        root = Path(context.workspace_root)
        resource = copy_resource(
            source,
            root / self._targets[category],
            "rag",
            metadata={"category": category},
        )
        record_import(root, resource)
        append_jsonl(
            root / ".mag" / "rag_index.jsonl",
            {
                "document_id": resource.resource_id,
                "category": category,
                "workspace_path": resource.workspace_path,
                "indexed": True,
                "index_type": "metadata",
            },
        )
        state = load_workspace_state(root)
        state.resources.append(resource)
        state.init.rag_documents += 1
        save_workspace_state(root, state)
        WorkspaceSafety(root).checkpoint("mag: import rag document")
        return CommandResult(f"Imported rag/{category}: {resource.workspace_path}")


def build_import_commands() -> list[object]:
    return [
        ImportCommand("question", "导入数学建模题目。", "input/problem", "problem"),
        ImportCommand("data", "导入题目数据。", "input/data", "data"),
        ImportCommand("layout", "导入论文模板。", "input/layout", "layout"),
        RagCommand(),
    ]
