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


def test_hidden_custom_and_calibration_panels_are_physically_unmapped() -> None:
    assert "def _force_unmap(panel" in SOURCE
    assert 'for method_name in ("grid_remove", "pack_forget", "place_forget")' in SOURCE
    assert "original_custom_show = advanced_ui._show_custom_panel" in SOURCE
    assert "original_calibration_show = calibration_ui._show_panel" in SOURCE
    assert '_force_unmap(getattr(app, "custom_settings_frame", None))' in SOURCE
    assert "_force_unmap(panel)" in SOURCE
    assert "advanced_ui._show_custom_panel = show_custom_panel" in SOURCE
    assert "calibration_ui._show_panel = show_calibration_panel" in SOURCE


def test_calibration_form_stacks_before_seven_column_layout_can_clip() -> None:
    assert "def _reflow_calibration_panel(app" in SOURCE
    assert "compact = width < 700" in SOURCE
    assert 'test_combo.grid_configure(row=1, column=1, columnspan=3, sticky="ew"' in SOURCE
    assert 'value_spin.grid_configure(row=2, column=1' in SOURCE
    assert 'poly_label.grid_configure(row=3, column=0, columnspan=2' in SOURCE
    assert 'button.grid_configure(\n                row=5,' in SOURCE
    assert 'summary.grid_configure(row=6, column=0, columnspan=4' in SOURCE
    assert 'hint.grid_configure(row=7, column=0, columnspan=4' in SOURCE
    assert "_ux_calibration_reflow_bound" in SOURCE
    assert "_schedule_calibration_reflow(app)" in SOURCE


def test_auto_collapsed_library_restores_only_without_explicit_user_close() -> None:
    assert "def toggle_library(app" in SOURCE
    assert "_ux_library_user_closed" in SOURCE
    assert "body_width >= 820" in SOURCE
    assert 'not bool(getattr(app, "_gaming_library_visible", False))' in SOURCE
    assert 'not bool(getattr(app, "_ux_library_user_closed", False))' in SOURCE
    assert "show_library(app, user_opened=False)" in SOURCE
    assert "gaming_ui._toggle_library = toggle_library" in SOURCE
    assert "persistent._toggle_library_persistent = toggle_library" in SOURCE


def test_topbar_keeps_generated_songs_when_legacy_library_was_removed() -> None:
    assert "_dedupe_songs_button" in SOURCE
    assert 'full_ui._find_button(app, "Library")' in SOURCE
    assert "manager = str(library.winfo_manager())" in SOURCE
    assert "if not manager:" in SOURCE
    assert "library.destroy()" in SOURCE
    assert 'library.configure(text="Songs")' in SOURCE
    assert "songs.destroy()" in SOURCE
    assert "app._ux_songs_button = library" in SOURCE


def test_overlay_coordinator_installs_after_band_overlay_patch() -> None:
    assert "from ui_overlay_coordinator_2026 import install_overlay_coordinator" in LAUNCHER
    assert LAUNCHER.index("install_band_responsive_patch()") < LAUNCHER.index("install_overlay_coordinator()")
