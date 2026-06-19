from pathlib import Path

from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workflow_adapter import WorkspaceWorkflowAdapter
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.llm import FakeLLMProvider, OpenAICompatibleLLMProvider


def _workspace_with_inputs(tmp_path: Path) -> Path:
    workspace = create_workspace(tmp_path / "workspace")
    problem = tmp_path / "problem.md"
    data = tmp_path / "data.csv"
    problem.write_text("# Problem\n\nBuild a model.", encoding="utf-8")
    data.write_text("x,y\n1,2\n2,3\n", encoding="utf-8")
    session = InteractiveSession(workspace.root)
    session.run_once(f"/question {problem}")
    session.run_once(f"/data {data}")
    session.run_once("/init --llm-key test-key")
    return workspace.root


def test_workflow_adapter_builds_task_input_from_v2_workspace(tmp_path: Path) -> None:
    root = _workspace_with_inputs(tmp_path)

    task_input = WorkspaceWorkflowAdapter(root).to_task_input()

    assert task_input.problem_file.name == "problem.md"
    assert [path.name for path in task_input.attachments] == ["data.csv"]


def test_workflow_adapter_syncs_outputs(tmp_path: Path) -> None:
    root = _workspace_with_inputs(tmp_path)
    (root / "paper").mkdir(exist_ok=True)
    (root / "paper/main.tex").write_text("tex", encoding="utf-8")
    (root / "paper/main.pdf").write_bytes(b"%PDF")
    (root / "final_submission").mkdir(exist_ok=True)
    (root / "final_submission/submission_package.zip").write_bytes(b"zip")

    WorkspaceWorkflowAdapter(root).sync_outputs()

    assert (root / "output/draft/main.tex").exists()
    assert (root / "output/draft/main.pdf").exists()
    assert (root / "output/package/submission_package.zip").exists()


def test_adapter_builds_real_llm_from_workspace_config(tmp_path: Path) -> None:
    root = _workspace_with_inputs(tmp_path)
    (root / ".env").write_text(
        "MAG_LLM_API_KEY=sk-x\n"
        "MAG_LLM_BASE_URL=https://api.deepseek.com/v1\n"
        "MAG_LLM_MODEL=deepseek-v4-flash\n",
        encoding="utf-8",
    )

    settings, bundle = WorkspaceWorkflowAdapter(root).build_providers()

    assert isinstance(bundle.llm, OpenAICompatibleLLMProvider)
    assert bundle.llm.base_url == "https://api.deepseek.com/v1"
    assert settings.openai_model == "deepseek-v4-flash"


def test_adapter_falls_back_to_fake_without_key(tmp_path: Path) -> None:
    root = _workspace_with_inputs(tmp_path)
    (root / ".env").write_text("", encoding="utf-8")

    _settings, bundle = WorkspaceWorkflowAdapter(root).build_providers()

    assert isinstance(bundle.llm, FakeLLMProvider)


def test_start_lock_run_executes_fake_workflow(tmp_path: Path) -> None:
    root = _workspace_with_inputs(tmp_path)
    # Force the fake LLM provider so the workflow stays offline in tests.
    env = root / ".env"
    env.write_text(env.read_text(encoding="utf-8") + "MAG_LLM_PROVIDER=fake\n", encoding="utf-8")
    session = InteractiveSession(root)

    result = session.run_once("/start --lock --run")

    assert "workflow completed" in result.message
    assert (root / "output/draft/main.tex").exists()
    assert (root / "output/package/submission_package.zip").exists()
