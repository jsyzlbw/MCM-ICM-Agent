from __future__ import annotations

import time

import httpx


class FakeHumanizerProvider:
    def __init__(self, rewrites: dict[str, str]) -> None:
        self.rewrites = rewrites

    def humanize(self, text: str, *, language: str = "en") -> str:
        return self.rewrites.get(text, text)


class UShallPassHumanizerProvider:
    def __init__(self, api_key: str, base_url: str = "https://leahloveswriting.xyz") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def humanize(self, text: str, *, language: str = "en") -> str:
        endpoint = (
            "/api_v2/rewrite/english/jobs"
            if language == "en"
            else "/api_v2/rewrite/chinese/jobs"
        )
        body = {"text": text} if language == "en" else {"text": text, "mode": "light"}
        headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        response = httpx.post(f"{self.base_url}{endpoint}", headers=headers, json=body, timeout=60)
        if response.status_code == 401:
            raise RuntimeError("UShallPass authentication failed")
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"UShallPass submit failed: {response.status_code}")
        task_id = response.json().get("task_id") or response.json().get("id")
        if not task_id:
            raise ValueError("UShallPass response missing task_id")

        for _ in range(30):
            poll = httpx.get(f"{self.base_url}{endpoint}/{task_id}", headers=headers, timeout=60)
            payload = poll.json()
            status = payload.get("status")
            if status == "completed":
                return payload.get("result", text)
            if status == "failed":
                error = payload.get("error", {})
                raise RuntimeError(f"UShallPass failed: {error.get('code', 'UNKNOWN')}")
            time.sleep(1)
        return text
