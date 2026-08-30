from __future__ import annotations

from pathlib import Path

import midi_engine as me
import playback_adaptive as adaptive
from playback_adaptive import AdaptivePlanOptions, SourceMeta
from playback_arranger_refinements import (
    _refine_candidate_roles,
    _refined_normalize_chord_attacks,
    _refined_role_from_source,
    _role_continuity_penalty,
)
from playback_overhaul import EnhancedMidiPlan


def _candidate(
    *,
    start: float,
    pitch: int,
    track: int,
    name: str = "Track",
    channel: int = 0,
    program: int = 0,
    role: str = "unknown",
) -> adaptive._CandidateMeta:
    return adaptive._CandidateMeta(
        start=start,
        pitch=pitch,
        velocity=90,
        track_index=track,
        track_name=name,
        channel=channel,
        program=program,
        role=role,
    )


def _plan(events: list[me.PlannedEvent]) -> EnhancedMidiPlan:
    return EnhancedMidiPlan(
        events=events,
        instrument="keyboard",
        duration=max(event.time for event in events),
        mode="stable",
        note_count=sum(event.kind == "note_on" for event in events),
        source_min_pitch=60,
        source_max_pitch=72,
        planned_min_pitch=60,
        planned_max_pitch=72,
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
        source_duration=1.0,
        source_track_count=1,
        source_percussion_notes=0,
        max_source_chord=2,
        max_planned_chord=2,
        max_simultaneous_keys=2,
        chord_removed_notes=0,
    )


def _source(serial: int, pitch: int) -> me.SourceNote:
    return me.SourceNote(start=float(serial), end=float(serial) + 0.3, pitch=pitch, velocity=100, serial=serial)


def _mapped(pitch: int) -> me._MappedGroup:
    return me._MappedGroup(
        state=me.KeyboardState(1, 0),
        pitches=[pitch],
        folded_count=0,
        skipped_count=0,
        semitone_displacement=0,
        priority_fold_penalty=0.0,
        priority_displacement=0.0,
    )


def test_reed_and_pipe_programs_are_not_automatically_declared_melody() -> None:
    assert _refined_role_from_source("Track 3", 0, 68) == "unknown"
    assert _refined_role_from_source("Lead", 0, 68) == "melody"
    assert _refined_role_from_source("Track 3", 0, 81) == "melody"


def test_track_statistics_infer_monophonic_high_line_as_melody_and_chords_as_harmony() -> None:
    melody = [
        _candidate(start=index * 0.25, pitch=67 + index % 4, track=0, program=68)
        for index in range(8)
    ]
    harmony: list[adaptive._CandidateMeta] = []
    for group in range(4):
        for offset, pitch in enumerate((48, 52, 55)):
            harmony.append(_candidate(start=group * 0.5 + offset * 0.003, pitch=pitch, track=1))
    refined = _refine_candidate_roles(melody + harmony)
    assert {item.role for item in refined if item.track_index == 0} == {"melody"}
    assert {item.role for item in refined if item.track_index == 1} == {"harmony"}


def test_ambiguous_two_note_grace_attack_is_not_snapped_when_spread_exceeds_six_ms() -> None:
    events = [
        me.PlannedEvent(0.000, 20, "note_on", key="a", serial=0),
        me.PlannedEvent(0.010, 20, "note_on", key="s", serial=1),
        me.PlannedEvent(0.200, 0, "note_off", key="a", serial=0),
        me.PlannedEvent(0.210, 0, "note_off", key="s", serial=1),
    ]
    metadata = {
        0: SourceMeta(0, 0.0, 60, 90, 0, "Piano", 0, 0, "harmony"),
        1: SourceMeta(1, 0.01, 64, 90, 0, "Piano", 0, 0, "harmony"),
    }
    adjusted, normalized, _ = _refined_normalize_chord_attacks(
        _plan(events),
        AdaptivePlanOptions(instrument="keyboard", chord_stagger_ms=0),
        metadata,
    )
    assert normalized == 0
    assert [event.time for event in adjusted if event.kind == "note_on"] == [0.0, 0.01]


def test_tight_two_note_block_attack_is_still_normalized() -> None:
    events = [
        me.PlannedEvent(0.000, 20, "note_on", key="a", serial=0),
        me.PlannedEvent(0.004, 20, "note_on", key="s", serial=1),
        me.PlannedEvent(0.200, 0, "note_off", key="a", serial=0),
        me.PlannedEvent(0.204, 0, "note_off", key="s", serial=1),
    ]
    adjusted, normalized, _ = _refined_normalize_chord_attacks(
        _plan(events),
        AdaptivePlanOptions(instrument="keyboard", chord_stagger_ms=0),
        {},
    )
    assert normalized == 1
    assert [event.time for event in adjusted if event.kind == "note_on"] == [0.0, 0.0]


def test_named_melody_role_adds_strong_penalty_to_bad_remap_continuity() -> None:
    metadata = {
        0: SourceMeta(0, 0.0, 60, 100, 0, "Lead Melody", 0, 80, "melody"),
        1: SourceMeta(1, 1.0, 62, 100, 0, "Lead Melody", 0, 80, "melody"),
    }
    token = adaptive._metadata_context.set(metadata)
    try:
        good = _role_continuity_penalty([_source(0, 60)], _mapped(60), [_source(1, 62)], _mapped(62), "keyboard")
        bad = _role_continuity_penalty([_source(0, 60)], _mapped(60), [_source(1, 62)], _mapped(50), "keyboard")
    finally:
        adaptive._metadata_context.reset(token)
    assert good == 0.0
    assert bad > 100.0


def test_launchers_install_arranger_refinements_before_pressure_model() -> None:
    for filename in ("modern_launcher.py", "studio_launcher.py"):
        source = Path(filename).read_text(encoding="utf-8")
        assert "from playback_arranger_refinements import install_arranger_refinements" in source
        assert source.index("install_adaptive_arranger(app)") < source.index("install_arranger_refinements(app)")
        assert source.index("install_arranger_refinements(app)") < source.index("install_adaptive_pressure_model(app)")
