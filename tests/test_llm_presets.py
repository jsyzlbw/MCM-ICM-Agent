from pathlib import Path

from mcm_agent.core.llm_presets import LLM_PRESETS, configure_llm_interactive
from mcm_agent.core.workspace import create_workspace


def _ask(answers):
    it = iter(answers)
    return lambda prompt="": next(it)


def test_configure_llm_preset_deepseek_openai(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "w").root
    msg = configure_llm_interactive(root, _ask(["1", "sk-deepseek", ""]))  # preset 1, key, default model
    env = (root / ".env").read_text(encoding="utf-8")
    assert "MAG_LLM_API_KEY=sk-deepseek" in env
    assert "MAG_LLM_BASE_URL=https://api.deepseek.com/v1" in env
    assert "MAG_LLM_MODEL=deepseek-chat" in env
    assert "MAG_LLM_PROTOCOL=openai" in env
    assert "已配置" in msg


def test_configure_llm_custom_anthropic(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "w").root
    custom = str(len(LLM_PRESETS) + 1)
    msg = configure_llm_interactive(
        root,
        _ask([custom, "https://api.deepseek.com/anthropic", "2", "sk-x", "deepseek-chat"]),
    )
    env = (root / ".env").read_text(encoding="utf-8")
    assert "MAG_LLM_BASE_URL=https://api.deepseek.com/anthropic" in env
    assert "MAG_LLM_PROTOCOL=anthropic" in env
    assert "MAG_LLM_MODEL=deepseek-chat" in env
    assert "已配置" in msg


def test_configure_llm_cancel_on_empty_key(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "w").root
    msg = configure_llm_interactive(root, _ask(["1", "", ""]))
    assert "取消" in msg
    assert "MAG_LLM_API_KEY=" not in (root / ".env").read_text(encoding="utf-8")
