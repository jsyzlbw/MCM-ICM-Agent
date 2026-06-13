from __future__ import annotations

from pathlib import Path

import typer

from mcm_agent.config import load_settings
from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.workspace import create_workspace
from mcm_agent.workflows.mvp import run_demo_workflow

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


@app.command("provider-status")
def provider_status(env_file: str | None = None) -> None:
    """Print which providers will be used for the current configuration."""
    settings = load_settings(env_file)
    llm_status = (
        f"openai-compatible ({settings.openai_model})"
        if settings.openai_api_key
        else "fake"
    )
    search_status = "Tavily API" if settings.tavily_api_key else "disabled/fake"
    extract_status = "Firecrawl API" if settings.firecrawl_api_key else "disabled/fake"
    mineru_status = settings.mineru_mode
    humanizer_status = "UShallPass API" if settings.humanizer_api_key else "fake"

    typer.echo(f"LLM: {llm_status}")
    typer.echo(f"Search: {search_status}")
    typer.echo(f"Extract: {extract_status}")
    typer.echo(f"MinerU: {mineru_status}")
    typer.echo(f"Humanizer: {humanizer_status}")
