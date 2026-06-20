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


class _FailingLLM:
    def generate(self, system: str, prompt: str) -> ProviderResult:
        raise RuntimeError("Connection timed out")


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


def test_chat_reply_surfaces_call_error_not_misleading_guidance(tmp_path: Path) -> None:
    """A configured LLM that fails at call time must report the failure honestly,
    NOT the 'please configure LLM / run /start' guidance (which sends the user to
    reconfigure an already-configured LLM — the root cause of '配好了却用不了')."""
    root = create_workspace(tmp_path / "ws").root

    reply = generate_chat_reply(root, "你打算怎么写？", _FailingLLM(), [])

    assert "Connection timed out" in reply  # the real reason is shown
    assert "失败" in reply
    assert "/start" not in reply  # NOT the misleading "run /start" guidance
    assert "请运行 /api" not in reply or "测连通" in reply  # if /api mentioned, it's the live test


def test_chat_reply_includes_attachment_content(tmp_path) -> None:
    from pathlib import Path
    from mcm_agent.core.workspace import create_workspace

    root = create_workspace(Path(tmp_path) / "ws").root
    llm = _EchoLLM()

    generate_chat_reply(root, "看看 @data.csv", llm, [], attachments=[("data.csv", "a,b\n1,2")])

    assert "data.csv" in llm.last_prompt
    assert "a,b" in llm.last_prompt
