from pathlib import Path


def test_readme_links_workflow_documentation() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "docs/WORKFLOW.md" in readme
    assert "mcm-agent inspect" in readme
    assert "scripts/run_demo_task.py" in readme


def test_workflow_doc_covers_operational_topics() -> None:
    workflow = Path("docs/WORKFLOW.md")
    assert workflow.exists()
    text = workflow.read_text(encoding="utf-8")

    required = [
        "# Workflow Guide",
        "## Command Reference",
        "## Workspace Structure",
        "## Agent Stages",
        "## Gate Repair Flow",
        "## Common Failure Modes",
    ]
    for heading in required:
        assert heading in text
    for command in ["mcm-agent run", "mcm-agent inspect", "mcm-agent resume"]:
        assert command in text
