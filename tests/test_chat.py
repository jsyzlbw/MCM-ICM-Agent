from pathlib import Path

from mcm_agent.core.chat import generate_chat_reply
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.base import ProviderResult


class _EchoLLM:
    def __init__(self) -> None:
        self.last_prompt = ""

    def generate(self, system: str, prompt: str) -> ProviderResult:
        self.last_prompt = prompt
        return ProviderResult(content="讨论回复：建议先估计 fan votes。", metadata={})


class _EmptyLLM:
    def generate(self, system: str, prompt: str) -> ProviderResult:
        return ProviderResult(content="   ", metadata={})


def test_chat_reply_uses_llm_and_problem_context(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    (root / "input" / "problem").mkdir(parents=True, exist_ok=True)
    (root / "input" / "problem" / "p.md").write_text(
        "Estimate hidden fan votes for DWTS.", encoding="utf-8"
    )
    llm = _EchoLLM()

    reply = generate_chat_reply(root, "第一问怎么做？", llm, [])

    assert "fan votes" in reply
    assert "DWTS" in llm.last_prompt  # problem context injected


def test_chat_reply_without_llm_returns_guidance(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root

    reply = generate_chat_reply(root, "你好", None, [])

    assert "/start" in reply


def test_chat_reply_empty_llm_output_falls_back(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root

    reply = generate_chat_reply(root, "你好", _EmptyLLM(), [])

    assert reply.strip()  # never returns an empty reply
