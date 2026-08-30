from __future__ import annotations

import midi_engine as me
from playback_adaptive import AdaptivePlanOptions
from playback_arranger_refinements import _refined_normalize_chord_attacks
from playback_overhaul import EnhancedMidiPlan


def _plan() -> EnhancedMidiPlan:
    events = [
        me.PlannedEvent(0.000, 20, "note_on", key="a", serial=0),
        me.PlannedEvent(0.004, 20, "note_on", key="s", serial=1),
        me.PlannedEvent(0.200, 0, "note_off", key="a", serial=0),
        me.PlannedEvent(0.204, 0, "note_off", key="s", serial=1),
    ]
    return EnhancedMidiPlan(
        events=events,
        instrument="keyboard",
        duration=0.204,
        mode="stable",
        note_count=2,
        source_min_pitch=60,
        source_max_pitch=64,
        planned_min_pitch=60,
        planned_max_pitch=64,
        page_switches=0,
        octave_switches=0,
        folded_notes=0,
        remapped_notes=0,
        skipped_notes=0,
        merged_notes=0,
        retrigger_merged_notes=0,
        retrigger_dropped_notes=0,
        filtered_notes=0,
        transposed_semitones=0,
        added_delay=0.0,
        page_switch_delay=0.22,
        unlock_tier="tier4",
        configured_min_pitch=36,
        configured_max_pitch=95,
        effective_min_pitch=36,
        effective_max_pitch=95,
        source_note_count=2,
        source_duration=0.204,
        source_track_count=1,
        source_percussion_notes=0,
        max_source_chord=2,
        max_planned_chord=2,
        max_simultaneous_keys=2,
        chord_removed_notes=0,
    )


def test_custom_or_raw_manual_mode_does_not_snap_authored_attacks() -> None:
    plan = _plan()
    adjusted, normalized, _ = _refined_normalize_chord_attacks(
        plan,
        AdaptivePlanOptions(instrument="keyboard", adaptive_auto=False, chord_stagger_ms=-1),
        {},
    )
    assert normalized == 0
    assert [event.time for event in adjusted if event.kind == "note_on"] == [0.0, 0.004]
