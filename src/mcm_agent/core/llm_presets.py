from __future__ import annotations

from pathlib import Path

from mcm_agent.core.config_writer import set_env_var

# Common LLM providers. Each preset fixes base_url + wire protocol so the user only
# needs to paste an API key (and optionally tweak the model).
LLM_PRESETS = [
    {
        "label": "DeepSeek 官方（OpenAI 兼容）",
        "base_url": "https://api.deepseek.com/v1",
        "protocol": "openai",
        "model": "deepseek-chat",
    },
    {
        "label": "DeepSeek 官方（Anthropic 兼容）",
        "base_url": "https://api.deepseek.com/anthropic",
        "protocol": "anthropic",
        "model": "deepseek-chat",
    },
    {
        "label": "OpenAI 官方",
        "base_url": "https://api.openai.com/v1",
        "protocol": "openai",
        "model": "gpt-4.1",
    },
    {
        "label": "Anthropic 官方",
        "base_url": "https://api.anthropic.com",
        "protocol": "anthropic",
        "model": "claude-3-5-sonnet-latest",
    },
    {
        "label": "硅基流动 SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "protocol": "openai",
        "model": "deepseek-ai/DeepSeek-V3",
    },
]


def configure_llm_interactive(root: Path, ask) -> str:
    """Guided LLM configuration: pick a preset (or custom protocol), enter key/model;
    writes MAG_LLM_* to workspace/.env. Returns a one-line result message."""
    listing = "\n".join(f"  {i + 1}) {p['label']}" for i, p in enumerate(LLM_PRESETS))
    custom_idx = len(LLM_PRESETS) + 1
    raw = (ask(f"选择 LLM 提供方：\n{listing}\n  {custom_idx}) 自定义\n编号: ") or "").strip()
    if not raw.isdigit():
        return "无效编号，已取消。"
    idx = int(raw)
    if idx == custom_idx:
        base_url = (ask("Base URL: ") or "").strip()
        if not base_url:
            return "Base URL 不能为空，已取消。"
        proto = (ask("协议 [1]OpenAI 兼容 [2]Anthropic 兼容: ") or "1").strip()
        protocol = "anthropic" if proto == "2" else "openai"
        label, default_model = "自定义", ""
    elif 1 <= idx <= len(LLM_PRESETS):
        preset = LLM_PRESETS[idx - 1]
        base_url, protocol = preset["base_url"], preset["protocol"]
        label, default_model = preset["label"], preset["model"]
    else:
        return "无效编号，已取消。"

    key = (ask(f"{label} API key: ") or "").strip()
    if not key:
        return "未输入 key，已取消。"
    model_prompt = f"Model（回车用 {default_model}）: " if default_model else "Model: "
    model = (ask(model_prompt) or "").strip() or default_model
    if not model:
        return "未输入 Model，已取消。"

    set_env_var(root, "MAG_LLM_API_KEY", key)
    set_env_var(root, "MAG_LLM_BASE_URL", base_url)
    set_env_var(root, "MAG_LLM_MODEL", model)
    set_env_var(root, "MAG_LLM_PROTOCOL", protocol)
    return f"✓ 已配置 {label}（{model}，{protocol} 协议）。"
