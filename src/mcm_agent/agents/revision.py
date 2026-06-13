from __future__ import annotations

from pathlib import Path

from mcm_agent.core.registry import ArtifactRegistry


class RevisionAgent:
    def apply_revision_request(self, workspace_root: Path, user_request: str) -> None:
        review_dir = workspace_root / "review"
        review_dir.mkdir(parents=True, exist_ok=True)
        (review_dir / "revision_requests.md").write_text(
            "# Revision Requests\n\n" + user_request + "\n",
            encoding="utf-8",
        )

        request_lower = user_request.lower()
        rerun_keywords = ["result", "model", "data", "figure", "rerun"]
        stale: list[str] = []
        if any(keyword in request_lower for keyword in rerun_keywords):
            registry = ArtifactRegistry(workspace_root / "artifact_registry.json")
            stale.extend(registry.mark_dependents_stale("model_decision_v1"))

        (review_dir / "revision_summary.md").write_text(
            "\n".join(
                [
                    "# Revision Summary",
                    "",
                    f"- Request: {user_request}",
                    f"- Stale artifacts: {', '.join(stale) if stale else 'none'}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
