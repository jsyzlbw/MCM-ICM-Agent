def test_theme_uses_teal_accent_not_coral() -> None:
    from mcm_agent.tui.theme import ACCENT, MAG_THEME

    assert ACCENT == "#1D9E75"  # teal, not Claude coral
    assert "accent" in MAG_THEME.styles


def test_bottom_hint_lists_modes() -> None:
    from mcm_agent.tui.theme import BOTTOM_HINT

    for token in ("/help", "/ 菜单", "! shell", "@ 文件"):
        assert token in BOTTOM_HINT
