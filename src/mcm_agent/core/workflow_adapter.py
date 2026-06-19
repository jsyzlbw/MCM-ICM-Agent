from __future__ import annotations

from pathlib import Path
import shutil

from mcm_agent.core.models import TaskInput
from mcm_agent.core.workspace_safety import WorkspaceSafety
from mcm_agent.workflows.mvp import run_mvp_workflow


class WorkspaceWorkflowAdapter:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def to_task_input(self) -> TaskInput:
        problem_files = sorted(path for path in (self.root / "input/problem").iterdir() if path.is_file())
        if not problem_files:
            raise FileNotFoundError("No problem file found in input/problem")
        attachments = []
        data_dir = self.root / "input/data"
        if data_dir.exists():
            attachments = sorted(path for path in data_dir.iterdir())
        layout_dir = self.root / "input/layout"
        template_dir = layout_dir if layout_dir.exists() and any(layout_dir.iterdir()) else None
        return TaskInput(
            problem_file=problem_files[0],
            attachments=attachments,
            template_dir=template_dir,
        )

    def run_default_workflow(self, *, auto_approve: bool = True) -> None:
        run_mvp_workflow(self.root, self.to_task_input(), auto_approve=auto_approve)
        self.sync_outputs()
        WorkspaceSafety(self.root).checkpoint("mag: run workflow")

    def sync_outputs(self) -> None:
        draft_dir = self.root / "output" / "draft"
        final_dir = self.root / "output" / "final"
        package_dir = self.root / "output" / "package"
        draft_dir.mkdir(parents=True, exist_ok=True)
        final_dir.mkdir(parents=True, exist_ok=True)
        package_dir.mkdir(parents=True, exist_ok=True)

        copies = [
            (self.root / "paper" / "main.tex", draft_dir / "main.tex"),
            (self.root / "paper" / "main.pdf", draft_dir / "main.pdf"),
            (self.root / "paper" / "main.tex", final_dir / "main.tex"),
            (self.root / "paper" / "main.pdf", final_dir / "main.pdf"),
            (
                self.root / "final_submission" / "submission_package.zip",
                package_dir / "submission_package.zip",
            ),
        ]
        for source, target in copies:
            if source.exists():
                shutil.copy2(source, target)
