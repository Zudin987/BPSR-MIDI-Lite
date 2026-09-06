from __future__ import annotations

from pathlib import Path


def test_lite_and_studio_install_band_lineup_before_runtime_hardening() -> None:
    for path in ("modern_launcher.py", "studio_launcher.py"):
        source = Path(path).read_text(encoding="utf-8")
        assert "install_band_mode(app)" in source
        assert "install_band_lineup(app)" in source
        assert "install_band_runtime_hardening(app)" in source
        assert "install_band_midi_sharing(app)" in source
        assert "install_band_network_hardening(app)" in source
        assert source.index("install_band_mode(app)") < source.index("install_band_lineup(app)")
        assert source.index("install_band_lineup(app)") < source.index(
            "install_band_runtime_hardening(app)"
        )
        assert source.index("install_band_runtime_hardening(app)") < source.index(
            "install_band_midi_sharing(app)"
        )
        assert source.index("install_band_midi_sharing(app)") < source.index(
            "install_band_network_hardening(app)"
        )


def test_band_ui_is_single_window_and_has_room_workflow() -> None:
    source = Path("band_ui.py").read_text(encoding="utf-8")
    for text in (
        "Band Mode (Beta)",
        "Band room",
        'text="Create"',
        'text="Join"',
        'text="Leave"',
        'text="Ready"',
        'text="Start Band"',
    ):
        assert text in source
    assert "Toplevel(" not in source
    assert "messagebox" not in source


def test_band_lineup_has_tickable_active_instruments_and_verified_drums() -> None:
    lineup = Path("band_lineup.py").read_text(encoding="utf-8")
    arranger = Path("band_arranger.py").read_text(encoding="utf-8")
    for text in ("Piano", "Guitar", "Bass", "Drums"):
        assert text in lineup
    assert "Players / instruments present" in lineup
    assert "Tick only instruments your group actually has" in lineup
    assert "Drums use C4-B5 only; no High/Low Octave." in lineup
    assert '"Drums": "drums"' in arranger
    assert "DRUM_MIN_PITCH = 60" in arranger
    assert "DRUM_MAX_PITCH = 83" in arranger
    assert "Drums (mapping pending)" not in arranger


def test_band_room_verifies_song_version_speed_clock_and_lineup() -> None:
    lineup = Path("band_lineup.py").read_text(encoding="utf-8")
    sync = Path("band_sync.py").read_text(encoding="utf-8")
    assert "midi_sha256" in sync
    assert "MIDI files do not all match" in sync
    assert "Everyone must use the same BPSR MIDI version" in sync
    assert "Song speed does not match between players" in sync
    assert "Every player needs a synchronized clock" in sync
    assert "Band lineup does not match between players" in sync
    assert "Missing player for" in sync
    assert "START_LEAD_SECONDS = 6.0" in sync
    assert "expected_active_parts=active_parts(app)" in lineup
    assert "active_parts=parts" in lineup
    assert "delay_until_utc_ms" in lineup


def test_synchronized_playback_disables_pause_and_keeps_stop_path() -> None:
    lineup = Path("band_lineup.py").read_text(encoding="utf-8")
    assert 'app.pause_button.configure(state="disabled", text="Pause")' in lineup
    assert 'app.stop_button.configure(state="normal")' in lineup


def test_runtime_hardening_preserves_deadline_for_every_part_and_deduplicates_start() -> None:
    source = Path("band_runtime_hardening.py").read_text(encoding="utf-8")
    assert "_band_start_deadline_perf" in source
    assert "time.perf_counter() + delay" in source
    assert "_band_last_start_utc_ms" in source
    assert 'if getattr(getattr(app, "player", None), "is_playing", False):' in source
    assert 'part != "drums"' not in source
    assert "Drum playback is disabled" not in source


def test_band_files_trigger_both_windows_workflows() -> None:
    lite = Path(".github/workflows/build-windows.yml").read_text(encoding="utf-8")
    studio = Path(".github/workflows/build-studio.yml").read_text(encoding="utf-8")
    assert '- "band_*.py"' in lite
    assert '- "band_*.py"' in studio
    assert '- "tests/test_band*.py"' in studio
