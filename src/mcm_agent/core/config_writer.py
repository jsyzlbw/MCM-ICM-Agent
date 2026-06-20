from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def import_env_file(root: Path, source_path: str) -> tuple[bool, str]:
    """Copy an existing .env file into the workspace (replacing workspace/.env).

    Mode 1 of API configuration: the user points at a .env they already have and we
    copy it verbatim into this workspace so secrets live in workspace/.env.
    """
    src = Path(str(source_path).strip().strip('"').strip("'")).expanduser()
    if not src.exists() or not src.is_file():
        return False, f"未找到 .env 文件: {src}"
    content = src.read_text(encoding="utf-8")
    if not content.endswith("\n"):
        content += "\n"
    (Path(root) / ".env").write_text(content, encoding="utf-8")
    has_llm = any(
        line.startswith("MAG_LLM_API_KEY=") and line.split("=", 1)[1].strip()
        for line in content.splitlines()
    )
    note = "" if has_llm else "（注意：该 .env 未包含 MAG_LLM_API_KEY）"
    return True, f"已从 {src} 复制 .env 到当前 workspace。{note}"


def set_env_var(root: Path, key: str, value: str) -> None:
    """Upsert ``KEY=value`` in the workspace ``.env`` (secrets live here)."""
    env = Path(root) / ".env"
    lines = []
    if env.exists():
        lines = [
            line
            for line in env.read_text(encoding="utf-8").splitlines()
            if not line.startswith(f"{key}=")
        ]
    lines.append(f"{key}={value}")
    env.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def set_toml_value(root: Path, section: str, key: str, value: Any) -> None:
    """Upsert ``[section] key = value`` in ``.mag/config.toml`` (non-secret config)."""
    path = Path(root) / ".mag" / "config.toml"
    data: dict[str, Any] = {}
    if path.exists():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    section_table = data.setdefault(section, {})
    if isinstance(section_table, dict):
        section_table[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump_toml(data), encoding="utf-8")


def _dump_toml(data: dict[str, Any]) -> str:
    out: list[str] = []
    for section, table in data.items():
        if not isinstance(table, dict):
            continue
        out.append(f"[{section}]")
        for key, value in table.items():
            out.append(f"{key} = {_fmt(value)}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_fmt(item) for item in value) + "]"
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'
