from __future__ import annotations

from pathlib import Path

from mcm_agent.core.chat import stream_chat_reply
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.base import ProviderResult


class _StreamLLM:
    def __init__(self):
        self.last_prompt = ""

    def generate(self, system, prompt):
        return ProviderResult(content="x", metadata={})

    def generate_stream(self, system, prompt):
        self.last_prompt = prompt
        for chunk in ["建议", "先估计", "票数"]:
            yield chunk


def test_stream_chat_reply_yields_chunks_and_injects_context(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    (root / "input" / "problem").mkdir(parents=True, exist_ok=True)
    (root / "input" / "problem" / "p.md").write_text("DWTS fan votes.", encoding="utf-8")
    llm = _StreamLLM()

    out = "".join(stream_chat_reply(root, "第一问？", llm, [], attachments=[("d.csv", "a,b")]))

    assert out == "建议先估计票数"
    assert "DWTS" in llm.last_prompt
    assert "d.csv" in llm.last_prompt
