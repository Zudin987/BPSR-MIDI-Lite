from types import SimpleNamespace

from suitability import evaluate_song_suitability


def make_plan(**overrides):
    values = {
        "note_count": 120,
        "duration": 60.0,
        "source_note_count": 120,
        "source_track_count": 1,
        "source_percussion_notes": 0,
        "max_source_chord": 2,
        "max_planned_chord": 2,
        "folded_notes": 0,
        "skipped_notes": 0,
        "chord_removed_notes": 0,
        "page_switches": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_simple_song_is_good_fit():
    result = evaluate_song_suitability(make_plan())
    assert result.code == "good"
    assert result.label == "Good fit"


def test_moderately_dense_song_is_busy():
    result = evaluate_song_suitability(
        make_plan(
            note_count=300,
            duration=60.0,
            source_note_count=320,
            max_source_chord=5,
            folded_notes=40,
            source_track_count=5,
        )
    )
    assert result.code == "busy"
    assert result.reasons


def test_extreme_density_is_very_complex():
    result = evaluate_song_suitability(
        make_plan(note_count=900, duration=60.0, max_source_chord=15)
    )
    assert result.code == "complex"
    assert "simpler" in result.summary
