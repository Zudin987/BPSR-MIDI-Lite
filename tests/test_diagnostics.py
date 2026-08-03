from types import SimpleNamespace

from diagnostics import build_diagnostic_text


def test_diagnostic_report_without_song_analysis():
    report = build_diagnostic_text(
        app_name="BPSR MIDI Lite",
        app_version="1.1.0",
        instrument="Keyboard",
        profile="Tier 3",
        input_backend="Win32 scan code",
        midi_name="song.mid",
        administrator=False,
        plan=None,
        suitability=None,
        last_input_test="Not run",
        last_error=None,
    )
    assert "App version: 1.1.0" in report
    assert "Access mode: Standard" in report
    assert "Selected MIDI: song.mid" in report
    assert "Song analysis: Not available" in report


def test_diagnostic_report_includes_plan_metrics():
    plan = SimpleNamespace(
        source_min_pitch=48,
        source_max_pitch=84,
        planned_min_pitch=48,
        planned_max_pitch=83,
        note_count=100,
        source_note_count=120,
        duration=45.0,
        source_track_count=3,
        source_percussion_notes=20,
        max_source_chord=6,
        max_planned_chord=3,
        folded_notes=12,
        skipped_notes=2,
        chord_removed_notes=6,
        filtered_notes=26,
        merged_notes=1,
        page_switches=0,
        octave_switches=8,
        transposed_semitones=0,
    )
    suitability = SimpleNamespace(label="Busy")
    report = build_diagnostic_text(
        app_name="BPSR MIDI Lite",
        app_version="1.1.0",
        instrument="Guitar",
        profile="Tier 3",
        input_backend="Win32 scan code",
        midi_name="anime.mid",
        administrator=True,
        plan=plan,
        suitability=suitability,
        last_input_test="Success",
        last_error="None",
    )
    assert "Suitability: Busy" in report
    assert "Largest source chord: 6" in report
    assert "Remapped/folded: 12" in report
    assert "Access mode: Administrator" in report
