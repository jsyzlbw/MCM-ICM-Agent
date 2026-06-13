from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.utils.json_io import write_json


class IntakeAgent:
    def run(
        self,
        workspace_root: Path,
        problem_file: Path,
        attachments: list[Path],
        user_idea: Path | None,
        template_dir: Path | None,
    ) -> None:
        input_dir = workspace_root / "input"
        input_dir.mkdir(parents=True, exist_ok=True)

        problem_target = input_dir / f"problem{problem_file.suffix}"
        shutil.copy2(problem_file, problem_target)

        attachment_records: list[str] = []
        attachment_dir = input_dir / "attachments"
        attachment_dir.mkdir(parents=True, exist_ok=True)
        for attachment in attachments:
            target = attachment_dir / attachment.name
            shutil.copy2(attachment, target)
            attachment_records.append(str(target.relative_to(workspace_root)))

        user_idea_path: str | None = None
        if user_idea is not None:
            target = input_dir / "user_idea.md"
            shutil.copy2(user_idea, target)
            user_idea_path = str(target.relative_to(workspace_root))

        template_path: str | None = None
        if template_dir is not None:
            target_dir = input_dir / "template"
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(template_dir, target_dir)
            template_path = str(target_dir.relative_to(workspace_root))

        manifest = {
            "problem_file": str(problem_target.relative_to(workspace_root)),
            "attachments": attachment_records,
            "user_idea": user_idea_path,
            "template_dir": template_path,
            "created_at": datetime.now(UTC).isoformat(),
        }
        write_json(workspace_root / "input_manifest.json", manifest)

        inventory = ["# Attachment Inventory", ""]
        for attachment in attachment_records:
            inventory.append(f"- `{attachment}`")
        (workspace_root / "reports" / "attachment_inventory.md").write_text(
            "\n".join(inventory) + "\n",
            encoding="utf-8",
        )

        Coordinator(workspace_root).emit("input.received", source="IntakeAgent")
