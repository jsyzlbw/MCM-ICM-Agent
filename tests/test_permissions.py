from pathlib import Path

from mcm_agent.core.permissions import OperationRisk, PermissionPolicy
from mcm_agent.core.workspace import create_workspace


def test_permission_policy_requires_confirmation_for_env(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")

    decision = PermissionPolicy(workspace.root).evaluate(workspace.root / ".env", "delete")

    assert decision.risk == OperationRisk.HIGH
    assert decision.requires_confirmation is True


def test_permission_policy_requires_confirmation_for_input_delete(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")

    decision = PermissionPolicy(workspace.root).evaluate(
        workspace.root / "input/problem/problem.md",
        "delete",
    )

    assert decision.risk == OperationRisk.HIGH
    assert decision.requires_confirmation is True


def test_permission_policy_allows_generated_work_outputs(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")

    decision = PermissionPolicy(workspace.root).evaluate(
        workspace.root / "output/draft/main.tex",
        "write",
    )

    assert decision.risk == OperationRisk.LOW
    assert decision.requires_confirmation is False


def test_permission_policy_marks_unknown_overwrite_as_medium(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")

    decision = PermissionPolicy(workspace.root).evaluate(
        workspace.root / "notes.md",
        "overwrite",
    )

    assert decision.risk == OperationRisk.MEDIUM
    assert decision.requires_confirmation is True
