from pathlib import Path


def test_modern_ui_has_no_advanced_fitting_or_minimize_option() -> None:
    source = Path("modern_ui.py").read_text(encoding="utf-8")
    assert "Advanced song fitting" not in source
    assert "Minimize after Play" not in source
    assert "Minimize this app" not in source
    assert "custom_settings_frame" not in source


def test_modern_ui_keeps_song_speed_and_raw_explanation() -> None:
    source = Path("modern_ui.py").read_text(encoding="utf-8")
    assert 'text="Song speed"' in source
    assert "100% = original MIDI speed" in source
    assert "Raw MIDI" in source
    assert "out-of-range notes are skipped" in source


def test_modern_ui_blocks_unexpected_page_events() -> None:
    source = Path("modern_ui.py").read_text(encoding="utf-8")
    assert "if plan.page_switches:" in source
    assert "Playback blocked — unexpected page change" in source
