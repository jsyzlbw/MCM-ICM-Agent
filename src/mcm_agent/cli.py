from __future__ import annotations

import json
from pathlib import Path

import typer

from mcm_agent.config import load_settings
from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.models import TaskInput
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.factory import build_provider_bundle
from mcm_agent.utils.json_io import read_json
from mcm_agent.workflows.mvp import resume_mvp_workflow, run_demo_workflow, run_mvp_workflow

app = typer.Typer(help="MCM/ICM math modeling agent CLI.")


@app.callback()
def main() -> None:
    """MCM/ICM math modeling agent CLI."""


@app.command()
def version() -> None:
    """Print package version."""
    typer.echo("mcm-agent 0.1.0")


@app.command("init-workspace")
def init_workspace(workspace: str) -> None:
    """Initialize a task workspace."""
    created = create_workspace(Path(workspace))
    typer.echo(f"Workspace initialized: {created.root}")


@app.command()
def status(workspace: str) -> None:
    """Print workspace status."""
    summary = Coordinator(Path(workspace)).status_summary()
    typer.echo(f"Phase: {summary.current_phase}")
    typer.echo(f"Unresolved issues: {summary.unresolved_issue_count}")
    typer.echo(f"Pending checkpoints: {summary.pending_checkpoints}")


@app.command("inspect")
def inspect_workspace(workspace: str) -> None:
    """Inspect a workspace's stage, gate, and unresolved issue status."""
    workspace_path = Path(workspace)
    state = read_json(workspace_path / "task_state.json", {})
    current_phase = state.get("current_phase", "unknown") if isinstance(state, dict) else "unknown"
    typer.echo(f"Current phase: {current_phase}")
    if isinstance(state, dict) and state.get("blocked_reason"):
        typer.echo(f"Blocked reason: {state['blocked_reason']}")
        if state.get("blocked_repair_stage"):
            typer.echo(f"Blocked repair stage: {state['blocked_repair_stage']}")

    gate = _latest_failed_gate(workspace_path)
    if gate:
        typer.echo(f"Failed gate: {gate.get('gate_id')}")
        typer.echo(f"Failure reason: {gate.get('failure_reason')}")
        typer.echo(f"Repair stage: {gate.get('repair_stage')}")
        findings = gate.get("blocking_findings") or []
        if findings:
            typer.echo("Blocking findings:")
            for finding in findings[:5]:
                typer.echo(f"- {finding}")

    unresolved = workspace_path / "unresolved_issues.md"
    if unresolved.exists() and "[[UNRESOLVED:" in unresolved.read_text(encoding="utf-8"):
        typer.echo("Unresolved issues: present")
    else:
        typer.echo("Unresolved issues: none")

    recent = _recent_stage_runs(workspace_path, limit=5)
    typer.echo("Recent stages:")
    for record in recent:
        typer.echo(
            f"- {record.get('stage_id')} [{record.get('status')}] -> {record.get('next_stage')}"
        )


@app.command()
def emit(workspace: str, event_type: str) -> None:
    """Emit a workflow event."""
    checkpoint_id = Coordinator(Path(workspace)).emit(event_type)
    typer.echo(f"Event emitted: {event_type}")
    if checkpoint_id:
        typer.echo(f"Checkpoint created: {checkpoint_id}")


@app.command("approve-checkpoint")
def approve_checkpoint(workspace: str, checkpoint_id: str) -> None:
    """Approve a pending checkpoint."""
    Coordinator(Path(workspace)).approve_checkpoint(checkpoint_id)
    typer.echo(f"Checkpoint approved: {checkpoint_id}")


@app.command("run-demo")
def run_demo(workspace: str, auto_approve: bool = True) -> None:
    """Run the deterministic demo workflow."""
    run_demo_workflow(Path(workspace), auto_approve=auto_approve)
    typer.echo(f"Demo workflow completed: {Path(workspace).resolve()}")


@app.command("run")
def run_workflow(
    workspace: str,
    problem_file: Path = typer.Option(..., "--problem-file", "-p"),
    attachment: list[Path] = typer.Option([], "--attachment", "-a"),
    user_idea_file: Path | None = typer.Option(None, "--user-idea-file"),
    template_dir: Path | None = typer.Option(None, "--template-dir"),
    supervisor_skills_dir: Path | None = typer.Option(None, "--supervisor-skills-dir"),
    env_file: str | None = typer.Option(None, "--env-file"),
    auto_approve: bool = typer.Option(False, "--auto-approve/--no-auto-approve"),
) -> None:
    """Run the MVP workflow on real task inputs using configured providers."""
    workspace_path = Path(workspace)
    settings = load_settings(env_file)
    providers = build_provider_bundle(settings, workspace_root=workspace_path)
    run_mvp_workflow(
        workspace_path,
        TaskInput(
            problem_file=problem_file,
            attachments=attachment,
            user_idea_file=user_idea_file,
            template_dir=template_dir,
        ),
        providers=providers,
        supervisor_skills_dir=supervisor_skills_dir,
        auto_approve=auto_approve,
    )
    typer.echo(f"Workflow completed: {workspace_path.resolve()}")


@app.command("resume")
def resume_workflow(
    workspace: str,
    problem_file: Path = typer.Option(..., "--problem-file", "-p"),
    attachment: list[Path] = typer.Option([], "--attachment", "-a"),
    user_idea_file: Path | None = typer.Option(None, "--user-idea-file"),
    template_dir: Path | None = typer.Option(None, "--template-dir"),
    supervisor_skills_dir: Path | None = typer.Option(None, "--supervisor-skills-dir"),
    env_file: str | None = typer.Option(None, "--env-file"),
    from_stage: str | None = typer.Option(None, "--from-stage"),
    until_stage: str | None = typer.Option(None, "--until-stage"),
    auto_approve: bool = typer.Option(False, "--auto-approve/--no-auto-approve"),
) -> None:
    """Resume an existing workspace from a stage or from task_state."""
    workspace_path = Path(workspace)
    settings = load_settings(env_file)
    providers = build_provider_bundle(settings, workspace_root=workspace_path)
    resume_mvp_workflow(
        workspace_path,
        TaskInput(
            problem_file=problem_file,
            attachments=attachment,
            user_idea_file=user_idea_file,
            template_dir=template_dir,
        ),
        providers=providers,
        supervisor_skills_dir=supervisor_skills_dir,
        auto_approve=auto_approve,
        from_stage=from_stage,
        until_stage=until_stage,
    )
    typer.echo(f"Resumed workflow: {workspace_path.resolve()}")


@app.command("provider-status")
def provider_status(env_file: str | None = None) -> None:
    """Print which providers will be used for the current configuration."""
    settings = load_settings(env_file)
    llm_status = (
        f"openai-compatible ({settings.openai_model})"
        if settings.openai_api_key
        else "fake"
    )
    search_stack = []
    if settings.tavily_api_key:
        search_stack.append("Tavily API")
    if settings.brave_search_api_key:
        search_stack.append("Brave API")
    if settings.exa_api_key:
        search_stack.append("Exa API")
    search_status = " + ".join(search_stack) if search_stack else "disabled/fake"
    extract_status = "Firecrawl API" if settings.firecrawl_api_key else "disabled/fake"
    mineru_status = settings.mineru_mode
    humanizer_status = "UShallPass API" if settings.humanizer_api_key else "fake"

    typer.echo(f"LLM: {llm_status}")
    typer.echo(f"Search: {search_status}")
    typer.echo(f"Extract: {extract_status}")
    typer.echo(f"MinerU: {mineru_status}")
    typer.echo(f"Humanizer: {humanizer_status}")


def _latest_failed_gate(workspace_path: Path) -> dict[str, object] | None:
    for relative_path in [
        "review/final_gate.json",
        "review/figure_gate.json",
        "review/validation_gate.json",
        "review/source_gate.json",
        "review/extraction_gate.json",
    ]:
        payload = read_json(workspace_path / relative_path, {})
        if isinstance(payload, dict) and payload.get("status") == "fail":
            return payload
    return None


def _recent_stage_runs(workspace_path: Path, *, limit: int) -> list[dict[str, object]]:
    path = workspace_path / "stage_runs.jsonl"
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records[-limit:]
