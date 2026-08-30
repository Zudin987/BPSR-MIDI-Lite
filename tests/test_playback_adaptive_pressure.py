from __future__ import annotations

import midi_engine as me
from playback_adaptive import AdaptivePlanOptions, CalibrationProfile, SourceAnalysis
from playback_adaptive_pressure import (
    _attack_rate_context,
    _attack_rate_for_starts,
    _refined_apply_note_lengths,
    _refined_auto_tune,
)


def _planned(start: float, pitch: int, key: str, serial: int) -> me.PlannedNote:
    return me.PlannedNote(
        source_start=start,
        source_end=start + 0.10,
        start=start,
        end=start + 0.10,
        pitch=pitch,
        page=1,
        octave=0,
        key=key,
        velocity=90,
        serial=serial,
    )


def test_isolated_humanized_four_note_chord_is_one_attack_not_fast_run() -> None:
    assert _attack_rate_for_starts([0.000, 0.004, 0.009, 0.013]) == 4.0


def test_fast_distinct_attacks_still_trigger_dense_auto_articulation() -> None:
    token = _attack_rate_context.set(16.0)
    try:
        tuned = _refined_auto_tune(
            AdaptivePlanOptions(instrument="keyboard", articulation_mode="balanced"),
            SourceAnalysis(max_chord=1, peak_250ms_nps=16.0, fast_repeat_ratio=0.0),
            CalibrationProfile(
                instrument="keyboard",
                minimum_clean_hold_ms=90,
                hard_floor_ms=40,
                retrigger_gap_ms=24,
                chord_stagger_ms=0,
                modifier_settle_ms=55,
                max_polyphony=4,
            ),
        )
    finally:
        _attack_rate_context.reset(token)
    assert tuned.articulation_mode == "dense"


def test_large_slow_chord_does_not_shorten_gate_as_if_it_were_rapid_notes() -> None:
    notes = [
        _planned(0.000, 60, "a", 0),
        _planned(0.004, 64, "d", 1),
        _planned(0.008, 67, "g", 2),
        _planned(0.012, 72, "q", 3),
    ]
    tuned = _refined_apply_note_lengths(
        notes,
        AdaptivePlanOptions(
            instrument="keyboard",
            minimum_note_ms=90,
            hard_press_floor_ms=40,
            repeated_release_gap_ms=24,
            short_note_tail_ms=20,
            attack_cluster_ms=15,
        ),
    )
    durations = [note.end - note.start for note in tuned]
    assert min(durations) >= 0.09
