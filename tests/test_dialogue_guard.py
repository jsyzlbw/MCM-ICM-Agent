from mcm_agent.core.dialogue_guard import DialogueGuard
from mcm_agent.core.workspace_models import WorkspaceState


def test_dialogue_guard_requires_llm() -> None:
    result = DialogueGuard.evaluate(WorkspaceState(), "帮我分析题目")

    assert not result.allowed
    assert "LLM API 尚未配置" in result.message


def test_dialogue_guard_requires_problem_after_llm() -> None:
    state = WorkspaceState()
    state.init.llm_configured = True

    result = DialogueGuard.evaluate(state, "帮我分析题目")

    assert not result.allowed
    assert "题目尚未导入" in result.message


def test_dialogue_guard_allows_discussion_when_minimum_ready() -> None:
    state = WorkspaceState()
    state.init.llm_configured = True
    state.init.problem_imported = True

    result = DialogueGuard.evaluate(state, "我想用优化模型")

    assert result.allowed
    assert "/init 尚未完全完成" in result.message


def test_dialogue_guard_is_quiet_when_init_complete() -> None:
    state = WorkspaceState()
    state.init.llm_configured = True
    state.init.problem_imported = True
    state.init.completed = True

    result = DialogueGuard.evaluate(state, "我想用优化模型")

    assert result.allowed
    assert result.message == ""
