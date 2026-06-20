from pathlib import Path

from mcm_agent.core.api_console import check_provider, provider_status, set_provider
from mcm_agent.core.workspace import create_workspace


def test_provider_status_reflects_unconfigured_then_configured(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "w").root
    before = {row["key"]: row for row in provider_status(root)}
    assert before["llm"]["configured"] is False
    assert before["llm"]["required"] is True

    set_provider(root, "llm", {"api_key": "k", "base_url": "https://x/v1", "model": "deepseek-v4-flash"})

    after = {row["key"]: row for row in provider_status(root)}
    assert after["llm"]["configured"] is True
    assert after["llm"]["detail"] == "deepseek-v4-flash"


def test_set_provider_writes_secret_to_env(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "w").root
    set_provider(root, "brave", {"api_key": "brave-secret"})

    env = (root / ".env").read_text(encoding="utf-8")
    assert "MAG_BRAVE_API_KEY=brave-secret" in env
    assert provider_status(root)[0]  # smoke: status callable


class _FakeTester:
    def __init__(self, status: str, detail: str) -> None:
        self._status = status
        self._detail = detail

    def check(self, provider: str):
        return type("R", (), {"status": self._status, "detail": self._detail})()


def test_check_provider_uses_injected_tester(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "w").root
    ok = check_provider(root, "llm", tester=_FakeTester("passed", "model responded"))
    bad = check_provider(root, "tavily", tester=_FakeTester("failed", "401 unauthorized"))

    assert ok == {"status": "passed", "detail": "model responded"}
    assert bad["status"] == "failed"
