from pathlib import Path


SOURCE = Path("ui_compact_toolbar_2026.py").read_text(encoding="utf-8")
LAUNCHER = Path("studio_launcher.py").read_text(encoding="utf-8")


def test_toolbar_has_three_responsive_layout_modes() -> None:
    assert "_WIDE_AT = 920" in SOURCE
    assert "_STACK_AT = 650" in SOURCE
    assert 'mode = "wide" if width >= _WIDE_AT else "medium" if width >= _STACK_AT else "stacked"' in SOURCE
    assert 'actions.grid_configure(row=0, column=0' in SOURCE
    assert 'tempo.grid_configure(row=1, column=0' in SOURCE
    assert 'progress_frame.grid_configure(' in SOURCE
    assert 'row=2, column=0' in SOURCE


def test_toolbar_patch_is_installed_between_full_ui_and_band_patch() -> None:
    assert "from ui_compact_toolbar_2026 import install_compact_toolbar_patch" in LAUNCHER
    full = LAUNCHER.index("install_full_ui_overhaul(app)")
    toolbar = LAUNCHER.index("install_compact_toolbar_patch()")
    band = LAUNCHER.index("install_band_responsive_patch()")
    assert full < toolbar < band
