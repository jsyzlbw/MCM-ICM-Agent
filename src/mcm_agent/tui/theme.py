from __future__ import annotations

from rich.theme import Theme

# 建模青 (teal) signature palette — see spec §13.1. Deliberately NOT Claude's coral.
ACCENT = "#1D9E75"         # teal-400: brand, panel border, prompt, highlight
ACCENT_BRIGHT = "#5DCAA5"  # teal-200: emphasis text on dark terminals
SUCCESS = "#639922"        # yellow-green: distinct from the teal accent
WARNING = "#EF9F27"
ERROR = "#E24B4A"

MAG_THEME = Theme(
    {
        "accent": ACCENT,
        "accent.bright": ACCENT_BRIGHT,
        "success": SUCCESS,
        "warning": WARNING,
        "error": ERROR,
    }
)

BOTTOM_HINT = "/help 命令 · / 菜单 · ! shell · @ 文件 · ? 快捷键"
