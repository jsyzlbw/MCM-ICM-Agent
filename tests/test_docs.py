from pathlib import Path


def test_readme_links_workflow_documentation() -> None:
    readme = Path("README.zh-CN.md").read_text(encoding="utf-8")

    assert "design.md" in readme
    assert "docs/00-overview.md" in readme
    assert "docs/dev/architecture.md" in readme


def test_design_doc_system_covers_required_topics() -> None:
    required_files = [
        Path("design.md"),
        Path("docs/00-overview.md"),
        Path("docs/01-cli-product-design.md"),
        Path("docs/02-workspace-design.md"),
        Path("docs/03-agent-workflow-design.md"),
        Path("docs/04-provider-design.md"),
        Path("docs/05-rag-design.md"),
        Path("docs/06-paper-generation-design.md"),
        Path("docs/07-review-and-revision-design.md"),
        Path("docs/dev/architecture.md"),
        Path("docs/dev/module-map.md"),
        Path("docs/dev/testing-guide.md"),
        Path("docs/dev/contribution-guide.md"),
        Path("docs/dev/roadmap.md"),
        Path("docs/dev/implementation-plan.md"),
        Path("docs/dev/adr/0004-git-safety-net.md"),
    ]
    for path in required_files:
        assert path.exists(), path

    design = Path("design.md").read_text(encoding="utf-8")
    for topic in ["/api", "/rag", "/question", "/data", "/layout", "/init", "/start"]:
        assert topic in design
    assert "LLM API 是唯一" in design
    assert "数据可得性" in design


def test_design_doc_system_covers_git_safety_net() -> None:
    workspace_doc = Path("docs/02-workspace-design.md").read_text(encoding="utf-8")
    cli_doc = Path("docs/01-cli-product-design.md").read_text(encoding="utf-8")
    provider_doc = Path("docs/04-provider-design.md").read_text(encoding="utf-8")

    assert "Git 安全网" in workspace_doc
    assert "git init" in workspace_doc
    assert "checkpoint commit" in workspace_doc
    assert "GitHub 自动 push" in provider_doc
    assert "/git" in cli_doc


def test_design_doc_system_includes_agent_collaboration_diagram() -> None:
    design = Path("design.md").read_text(encoding="utf-8")
    workflow_doc = Path("docs/03-agent-workflow-design.md").read_text(encoding="utf-8")

    for text in [design, workflow_doc]:
        assert "Agent 协作图" in text
        assert "```mermaid" in text
        assert "flowchart TD" in text
        assert "Coordinator" in text
        assert "Gate Controller" in text
        assert "Workspace Safety" in text


def test_implementation_plan_covers_full_cli_design() -> None:
    plan = Path("docs/dev/implementation-plan.md").read_text(encoding="utf-8")

    for topic in [
        "KamaClaude",
        "OpenCode",
        "Aider",
        "/init",
        "/start",
        "GitHub 自动 push",
        "Workspace Safety",
        "research script",
        "workflow_adapter.py",
        "pytest -q",
    ]:
        assert topic in plan
