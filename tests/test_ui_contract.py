from __future__ import annotations

from pathlib import Path


APP_SOURCE = Path("app.py")


def _source() -> str:
    return APP_SOURCE.read_text(encoding="utf-8")


def test_ui_has_profile_song_and_play_sections() -> None:
    source = _source()
    assert "Choose instrument and unlock profile" in source
    assert "Choose a song" in source
    assert "3. Play" in source
    assert "Song preview" in source


def test_ui_keeps_local_midi_library_tools() -> None:
    source = _source()
    assert 'text="Open Folder"' in source
    assert 'text="Reload"' in source
    assert "scan_midi_folder" in source
    assert "MIDI_EXTENSIONS" in source


def test_ui_keeps_bpsr_safety_and_input_controls() -> None:
    source = _source()
    assert "F10 is an emergency stop" in source
    assert "Administrator permission is required" in source
    assert "Input method" in source
    assert "INPUT_BACKEND_LABELS" in source


def test_ui_keeps_profile_summary_and_before_playback_notice() -> None:
    source = _source()
    assert "profile_summary_var" in source
    assert "Before playback" in source
    assert "notice_var" in source


def test_ui_keeps_raw_mode_and_page_fail_safe() -> None:
    source = _source()
    assert 'text="Song speed"' in source
    assert "Raw MIDI" in source
    assert "out-of-range notes are skipped" in source
    assert 'if plan.page_switches or any(event.kind == "page"' in source
    assert "Playback blocked — unexpected page change" in source


def test_v3_layers_online_library_without_replacing_stable_modern_ui() -> None:
    launcher = Path("modern_launcher.py").read_text(encoding="utf-8")
    integration = Path("online_integration.py").read_text(encoding="utf-8")
    online = Path("online_ui.py").read_text(encoding="utf-8")

    assert "install_modern_ui(app)" in launcher
    assert "install_online_integration(app)" in launcher
    assert 'app.APP_VERSION = "3.3.0"' in launcher
    assert "install_gaming_ui_2026(app)" in launcher
    assert "install_online_search_bridge()" in launcher
    assert "install_playback_overhaul(app)" in launcher
    assert "install_advanced_playback_profile(app)" in launcher
    assert "install_adaptive_arranger(app)" in launcher
    assert "install_calibration_provenance(app)" in launcher
    assert "_online_original_build_ui" in integration
    assert "online_ui.build_song_source_ui" in integration
    assert 'text="Online Sequencer"' in online
    assert 'text="Bookmarks"' in online
    # The stable source layer still carries its legacy labels; the launcher
    # relabels those controls at runtime to Search / Verify once.
    assert 'text="Load link / ID"' in online
    assert 'text="Find online MIDI ID"' in online
    assert 'text="Find in browser"' not in online
    assert 'text="Open on Online Sequencer"' not in online
    assert 'text="Save to Local"' in online
    assert 'text="Bookmark"' in online
    assert "Temporary online cache" in online
