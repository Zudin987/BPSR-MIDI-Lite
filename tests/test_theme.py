from theme import theme_colors


def test_dark_theme_has_light_text_on_dark_surfaces() -> None:
    colors = theme_colors(True)
    assert colors.background.startswith("#")
    assert colors.foreground.lower() == "#f3f3f3"
    assert colors.background != colors.field


def test_light_and_dark_palettes_are_distinct() -> None:
    light = theme_colors(False)
    dark = theme_colors(True)
    assert light.background != dark.background
    assert light.foreground != dark.foreground
    assert light.selection.startswith("#")
    assert dark.selection.startswith("#")
