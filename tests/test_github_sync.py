from pathlib import Path

from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workspace import create_workspace
from mcm_agent.core.workspace_safety import WorkspaceSafety
from mcm_agent.providers.github import GitPushResult


class FakePushAdapter:
    def __init__(self, success: bool = True):
        self.success = success
        self.calls: list[tuple[Path, str, str | None]] = []

    def push(self, root: Path, remote: str = "origin", branch: str | None = None) -> GitPushResult:
        self.calls.append((root, remote, branch))
        return GitPushResult(success=self.success, message="pushed" if self.success else "failed")


def test_auto_push_is_disabled_by_default(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")

    assert WorkspaceSafety(workspace.root).auto_push_enabled() is False
    assert "Auto push: disabled" in InteractiveSession(workspace.root).run_once("/git").message


def test_checkpoint_calls_push_adapter_when_auto_push_enabled(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    config = workspace.root / ".mag/config.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace("auto_push = false", "auto_push = true"),
        encoding="utf-8",
    )
    (workspace.root / "output/draft/main.md").write_text("draft", encoding="utf-8")
    adapter = FakePushAdapter(success=True)

    WorkspaceSafety(workspace.root, push_adapter=adapter).checkpoint("mag: draft")

    assert adapter.calls
    assert (workspace.root / ".mag/logs/git_push_history.jsonl").exists()


def test_push_failure_is_recorded_and_does_not_block_checkpoint(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    config = workspace.root / ".mag/config.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace("auto_push = false", "auto_push = true"),
        encoding="utf-8",
    )
    (workspace.root / "output/draft/main.md").write_text("draft", encoding="utf-8")

    WorkspaceSafety(workspace.root, push_adapter=FakePushAdapter(success=False)).checkpoint(
        "mag: draft"
    )

    history = (workspace.root / ".mag/logs/git_push_history.jsonl").read_text(encoding="utf-8")
    assert '"success": false' in history
    assert "failed" in history


def test_git_command_shows_auto_push_enabled(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    config = workspace.root / ".mag/config.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace("auto_push = false", "auto_push = true"),
        encoding="utf-8",
    )

    result = InteractiveSession(workspace.root).run_once("/git")

    assert "Auto push: enabled" in result.message
