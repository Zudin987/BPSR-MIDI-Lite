from pathlib import Path


SOURCE = Path("ui_full_overhaul_2026.py").read_text(encoding="utf-8")


def test_full_ui_overhaul_is_dpi_aware_and_screen_fitted() -> None:
    assert "SetProcessDpiAwarenessContext" in SOURCE
    assert "SetProcessDpiAwareness" in SOURCE
    assert "SetProcessDPIAware" in SOURCE
    assert "sw - 80" in SOURCE and "sh - 100" in SOURCE
    assert "_MAIN_MIN_WIDTH = 560" in SOURCE
    assert "_MAIN_MIN_HEIGHT = 380" in SOURCE


def test_library_is_responsive_instead_of_permanently_400px() -> None:
    assert "_WIDE_LIBRARY = 360" in SOURCE
    assert "_MEDIUM_LIBRARY = 300" in SOURCE
    assert "_COMPACT_LIBRARY = 260" in SOURCE
    assert 'text="Songs"' in SOURCE
    assert "body_width < 820" in SOURCE
    assert "_ux_library_overlay" in SOURCE
    assert 'displaycolumns=("fit", "notes")' in SOURCE


def test_settings_and_rare_panels_scroll_without_new_windows() -> None:
    assert "_settings_scroll_command" in SOURCE
    assert "_ux_settings_scrollbar" in SOURCE
    assert "_overlay_scroll_command" in SOURCE
    assert 'advanced._show_custom_panel = show_custom' in SOURCE
    assert 'calibration._show_panel = show_calibration' in SOURCE
    assert "Custom tuning…" in SOURCE
    assert "<Escape>" in SOURCE


def test_song_check_and_band_room_use_progressive_responsive_layouts() -> None:
    assert "_hide_song_diagnostics" in SOURCE
    assert "_toggle_song_details" in SOURCE
    assert "_reflow_metric_cards" in SOURCE
    assert "_reflow_primary_setup" in SOURCE
    assert "_reflow_band_panel" in SOURCE


def test_studio_audio_band_removes_redundant_source_choice_and_action_column() -> None:
    assert "_studio_hide_single_source_combo" in SOURCE
    assert 'value not in {"availability", "action"}' in SOURCE
    assert "Models & quality…" in SOURCE
    assert "Apply changes" in SOURCE
    assert "_studio_search_reflow" in SOURCE
