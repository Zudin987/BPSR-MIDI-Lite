from pathlib import Path


SOURCE = Path("ui_band_responsive_2026.py").read_text(encoding="utf-8")
LAUNCHER = Path("studio_launcher.py").read_text(encoding="utf-8")


def test_band_extensions_are_reserved_below_base_status_rows() -> None:
    assert "_BASE_EXTENSION_ROW = 8" in SOURCE
    assert 'row is not None and row >= 6' in SOURCE
    assert "_BASE_EXTENSION_ROW + index" in SOURCE
    assert "_ux_band_grid" in SOURCE


def test_lineup_and_room_midi_have_compact_reflow() -> None:
    assert "_reflow_lineup" in SOURCE
    assert "divmod(index, 2)" in SOURCE
    assert "_reflow_room_midi" in SOURCE
    assert 'checkbox.grid_configure(row=1' in SOURCE
    assert 'download.grid_configure(row=2' in SOURCE


def test_band_room_is_secondary_scrollable_overlay_with_reopen_button() -> None:
    assert 'full_ui._show_feature_overlay(' in SOURCE
    assert '"band",' in SOURCE
    assert 'text="Band room…"' in SOURCE
    assert "band_ui._set_band_frame_visible = _set_band_frame_visible" in SOURCE
    assert 'full_ui._refresh_feature_overlay(app, "band")' in SOURCE
    assert '_band_overlay_visible(app)' in SOURCE


def test_studio_installs_patch_after_full_overhaul() -> None:
    assert "from ui_band_responsive_2026 import install_band_responsive_patch" in LAUNCHER
    assert LAUNCHER.index("install_full_ui_overhaul(app)") < LAUNCHER.index("install_band_responsive_patch()")
