from pathlib import Path


SOURCE = Path("ui_overlay_coordinator_2026.py").read_text(encoding="utf-8")
LAUNCHER = Path("studio_launcher.py").read_text(encoding="utf-8")


def test_secondary_overlays_replace_band_room_instead_of_stacking() -> None:
    assert "_close_band_if_needed(app)" in SOURCE
    assert 'if key != "band"' in SOURCE
    assert "if visible:" in SOURCE
    assert "if user_opened:" in SOURCE
    assert 'full_ui._hide_feature_overlay(app, "custom")' in SOURCE
    assert 'full_ui._hide_feature_overlay(app, "calibration")' in SOURCE


def test_user_opened_settings_survives_compact_configure_reflow() -> None:
    assert "_ux_settings_user_open" in SOURCE
    assert "_ux_settings_reflow_guard" in SOURCE
    assert "preserve_settings" in SOURCE
    assert "full_ui._refresh_settings_position(app)" in SOURCE
    assert "full_ui._responsive_root = responsive_root" in SOURCE


def test_topbar_reuses_original_library_button_as_single_songs_action() -> None:
    assert "_dedupe_songs_button" in SOURCE
    assert 'full_ui._find_button(app, "Library")' in SOURCE
    assert 'library.configure(text="Songs")' in SOURCE
    assert "songs.destroy()" in SOURCE
    assert "app._ux_songs_button = library" in SOURCE


def test_overlay_coordinator_installs_after_band_overlay_patch() -> None:
    assert "from ui_overlay_coordinator_2026 import install_overlay_coordinator" in LAUNCHER
    assert LAUNCHER.index("install_band_responsive_patch()") < LAUNCHER.index("install_overlay_coordinator()")
