from pathlib import Path


def _source() -> str:
    return Path("modern_ui.py").read_text(encoding="utf-8")


def test_ui_is_single_page_and_scrollable() -> None:
    source = _source()
    assert "tk.Canvas(" in source
    assert "ttk.Scrollbar(" in source
    assert "yscrollcommand=scrollbar.set" in source
    assert 'self.minsize(560, 500)' in source


def test_ui_has_no_settings_layer_or_folder_buttons() -> None:
    source = _source()
    assert "More settings" not in source
    assert "Open folder" not in source
    assert "Open songs folder" not in source
    assert "custom_settings_frame" not in source


def test_countdown_restore_and_troubleshooting_are_on_main_page() -> None:
    source = _source()
    assert 'text="Countdown"' in source
    assert 'text="Restore recommended settings"' in source
    assert 'text="Troubleshooting ▾"' in source
    assert 'text="Help & recovery"' in source


def test_song_check_reports_remapping_counts() -> None:
    source = _source()
    assert "plan.folded_notes" in source
    assert "Remapped:" in source
    assert "Skipped:" in source
    assert "Filtered/simplified:" in source


def test_ui_keeps_song_speed_raw_mode_and_page_fail_safe() -> None:
    source = _source()
    assert 'text="Song speed"' in source
    assert "100% = original MIDI speed" in source
    assert "Raw MIDI" in source
    assert "out-of-range notes are skipped" in source
    assert "if plan.page_switches:" in source
    assert "Playback blocked — unexpected page change" in source
