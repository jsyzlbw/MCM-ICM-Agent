from pathlib import Path
import subprocess

from mcm_agent.core.workspace import create_workspace
from mcm_agent.core.workspace_safety import WorkspaceSafety


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def test_create_workspace_initializes_git_repository(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "task")

    assert (workspace.root / ".git").exists()
    assert _git(workspace.root, "log", "--oneline")
    assert "mag workspace initialized" in _git(workspace.root, "log", "--oneline")


def test_gitignore_excludes_secrets_and_sensitive_cache(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "task")

    gitignore = (workspace.root / ".gitignore").read_text(encoding="utf-8")

    for expected in [
        ".env",
        ".mag/cache/",
        ".mag/logs/*.debug.json",
        ".mag/logs/*raw*",
        ".DS_Store",
    ]:
        assert expected in gitignore


def test_env_file_is_not_committed(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "task")

    tracked_files = _git(workspace.root, "ls-files").splitlines()

    assert ".env" not in tracked_files


def test_workspace_safety_checkpoint_skips_empty_commit(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "task")
    safety = WorkspaceSafety(workspace.root)
    before = _git(workspace.root, "rev-list", "--count", "HEAD")

    safety.checkpoint("mag empty checkpoint")

    after = _git(workspace.root, "rev-list", "--count", "HEAD")
    assert after == before


def test_workspace_safety_checkpoint_commits_changes(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "task")
    (workspace.root / "input/problem/problem.md").write_text("problem", encoding="utf-8")

    commit = WorkspaceSafety(workspace.root).checkpoint("mag: import problem statement")

    assert commit
    assert "mag: import problem statement" in _git(workspace.root, "log", "--oneline")
    assert WorkspaceSafety(workspace.root).status().clean is True
