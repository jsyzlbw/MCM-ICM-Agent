import json

from mcm_agent.config import Settings
from mcm_agent.providers.smoke import ProviderSmokeTester


def test_smoke_appends_history(tmp_path):
    history = tmp_path / "history.jsonl"
    tester = ProviderSmokeTester(Settings(), workspace_root=tmp_path, history_path=history)

    # No keys configured -> llm and embedding are deterministically skipped.
    tester.run(["llm", "embedding"])
    tester.run(["llm"])

    lines = history.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert "timestamp" in first
    assert first["counts"]["skipped"] >= 1
    assert any(r["provider"] == "llm" for r in first["results"])


def test_smoke_without_history_path_writes_nothing(tmp_path):
    tester = ProviderSmokeTester(Settings(), workspace_root=tmp_path)
    tester.run(["llm"])
    assert not (tmp_path / "provider_smoke_history.jsonl").exists()
