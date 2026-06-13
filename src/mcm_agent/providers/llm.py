from __future__ import annotations

from mcm_agent.providers.base import ProviderResult


class FakeLLMProvider:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses

    def generate(self, system: str, prompt: str, *, temperature: float = 0.2) -> ProviderResult:
        key = prompt.splitlines()[0].strip() if prompt.strip() else "default"
        content = self.responses.get(key, self.responses.get("default", ""))
        return ProviderResult(content=content, metadata={"fake": True})
