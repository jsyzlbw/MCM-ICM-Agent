from __future__ import annotations

from dataclasses import dataclass

from mcm_agent.core.workspace_models import WorkspaceState


@dataclass(frozen=True)
class DialogueGuardResult:
    allowed: bool
    message: str


class DialogueGuard:
    @staticmethod
    def evaluate(state: WorkspaceState, message: str) -> DialogueGuardResult:
        if not state.init.llm_configured:
            return DialogueGuardResult(
                allowed=False,
                message="LLM API 尚未配置。请先运行 /api 或 /init。",
            )
        if not state.init.problem_imported:
            return DialogueGuardResult(
                allowed=False,
                message="题目尚未导入。请先运行 /question。",
            )
        if not state.init.completed:
            return DialogueGuardResult(
                allowed=True,
                message="可以继续讨论。提醒：/init 尚未完全完成，RAG/data/layout 可以稍后补充。",
            )
        return DialogueGuardResult(allowed=True, message="")
