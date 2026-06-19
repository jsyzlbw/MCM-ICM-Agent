from __future__ import annotations

import httpx

from mcm_agent.providers.base import ProviderResult


class FakeLLMProvider:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses

    def generate(self, system: str, prompt: str, *, temperature: float = 0.2) -> ProviderResult:
        key = prompt.splitlines()[0].strip() if prompt.strip() else "default"
        content = self.responses.get(key, self.responses.get("default", ""))
        return ProviderResult(content=content, metadata={"fake": True})


class OpenAICompatibleLLMProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: int = 60,
        max_retries: int = 2,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI-compatible provider requires api_key")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/") or "https://api.openai.com/v1"
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def generate(self, system: str, prompt: str, *, temperature: float = 0.2) -> ProviderResult:
        last_error = "unknown error"
        for _attempt in range(self.max_retries + 1):
            try:
                response = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": temperature,
                    },
                    timeout=self.timeout_seconds,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                continue  # transient network error: retry
            # Retry transient server errors / rate limits; fail fast on other 4xx.
            if response.status_code == 429 or 500 <= response.status_code < 600:
                last_error = f"{response.status_code} {response.text[:200]}"
                continue
            if response.status_code < 200 or response.status_code >= 300:
                raise RuntimeError(f"LLM request failed: {response.status_code} {response.text}")

            payload = response.json()
            choices = payload.get("choices", [])
            if not choices:
                raise RuntimeError("LLM response missing choices")
            content = choices[0].get("message", {}).get("content", "")
            return ProviderResult(
                content=content,
                metadata={
                    "provider": "openai_compatible",
                    "model": self.model,
                    "id": payload.get("id"),
                    "total_tokens": payload.get("usage", {}).get("total_tokens"),
                },
            )
        raise RuntimeError(
            f"LLM request failed after {self.max_retries + 1} attempts: {last_error}"
        )
