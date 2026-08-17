from pathlib import Path


def _source() -> str:
    return Path("modern_ui.py").read_text(encoding="utf-8")


def test_ui_is_single_page_and_scrollable() -> None:
    source = _source()
    assert "tk.Canvas(" in source
    assert "ttk.Scrollbar(" in source
    assert "yscrollcommand=scrollbar.set" in source
    assert 'self.minsize(560, 500)' in source


def test_instrument_and_category_are_side_by_side() -> None:
    source = _source()
    assert 'setup.columnconfigure(0, weight=1, uniform="setup")' in source
    assert 'setup.columnconfigure(1, weight=1, uniform="setup")' in source
    assert 'text="What are you playing?"' in source
    assert 'text="Which category have you unlocked?"' in source
    assert 'row=0, column=0' in source
    assert 'row=0, column=1' in source


def test_song_uses_open_folder_and_clear_speed_restore_label() -> None:
    source = _source()
    assert 'text="Open folder"' in source
    assert "_open_midi_folder" in source
    assert "Add MIDI…" not in source
    assert 'text="Restore song speed to default 100%"' in source
    assert "100% = original MIDI speed" in source
    assert "_poll_song_library" in source


def test_help_and_recovery_has_only_restore_and_keyboard_connection_controls() -> None:
    source = _source()
    assert 'text="Help & recovery"' in source
    assert 'text="Restore recommended settings"' in source
    assert 'text="Keyboard connection"' in source
    assert "INPUT_BACKEND_LABELS" in source
    assert "Troubleshooting" not in source
    assert "Test keyboard input" not in source
    assert "Copy support info" not in source


def test_song_check_reports_remapping_counts() -> None:
    source = _source()
    assert "plan.folded_notes" in source
    assert "Remapped:" in source
    assert "Skipped:" in source
    assert "Filtered/simplified:" in source


def test_ui_keeps_raw_mode_and_page_fail_safe() -> None:
    source = _source()
    assert 'text="Song speed"' in source
    assert "Raw MIDI" in source
    assert "out-of-range notes are skipped" in source
    assert "if plan.page_switches:" in source
    assert "Playback blocked — unexpected page change" in source
