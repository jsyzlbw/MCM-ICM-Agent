from __future__ import annotations

import time

import httpx


class FakeHumanizerProvider:
    def __init__(self, rewrites: dict[str, str]) -> None:
        self.rewrites = rewrites

    def humanize(self, text: str, *, language: str = "en") -> str:
        return self.rewrites.get(text, text)


class UShallPassHumanizerProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://leahloveswriting.xyz",
        *,
        poll_interval_seconds: float = 1,
        max_poll_attempts: int = 30,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.poll_interval_seconds = poll_interval_seconds
        self.max_poll_attempts = max_poll_attempts

    def humanize(self, text: str, *, language: str = "en") -> str:
        if not text.strip():
            raise ValueError("UShallPass text must not be empty")
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
        submit_payload = response.json()
        self._raise_if_unsuccessful(submit_payload)
        submit_data = self._data(submit_payload)
        task_id = submit_data.get("task_id") or submit_data.get("id") or submit_payload.get("task_id")
        if not task_id:
            raise ValueError("UShallPass response missing task_id")

        for _ in range(self.max_poll_attempts):
            poll = httpx.get(f"{self.base_url}{endpoint}/{task_id}", headers=headers, timeout=60)
            if poll.status_code < 200 or poll.status_code >= 300:
                raise RuntimeError(f"UShallPass poll failed: {poll.status_code}")
            poll_payload = poll.json()
            self._raise_if_unsuccessful(poll_payload)
            payload = self._data(poll_payload)
            status = payload.get("status")
            if status == "completed":
                return payload.get("result", text)
            if status == "failed":
                error = payload.get("error", {})
                code = error.get("code", "UNKNOWN") if isinstance(error, dict) else "UNKNOWN"
                message = error.get("message", "") if isinstance(error, dict) else str(error)
                raise RuntimeError(f"UShallPass failed: {code}: {message}".rstrip())
            time.sleep(self.poll_interval_seconds)
        raise TimeoutError(f"UShallPass timed out waiting for task_id={task_id}")

    @staticmethod
    def _data(payload: dict[str, object]) -> dict[str, object]:
        data = payload.get("data")
        return data if isinstance(data, dict) else payload

    @staticmethod
    def _raise_if_unsuccessful(payload: dict[str, object]) -> None:
        if payload.get("success") is not False:
            return
        error = payload.get("error", {})
        if isinstance(error, dict):
            code = error.get("code", "UNKNOWN")
            message = error.get("message", "")
            raise RuntimeError(f"UShallPass failed: {code}: {message}".rstrip())
        raise RuntimeError(f"UShallPass failed: {error}")
