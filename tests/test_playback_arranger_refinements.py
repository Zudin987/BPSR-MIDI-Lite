from __future__ import annotations

from pathlib import Path

import midi_engine as me
import playback_adaptive as adaptive
import playback_arranger_refinements as refinements
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
        octave_switches=sum(event.kind == "state" for event in events),
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
        source_note_count=sum(event.kind == "note_on" for event in events),
        source_duration=1.0,
        source_track_count=1,
        source_percussion_notes=0,
        max_source_chord=4,
        max_planned_chord=4,
        max_simultaneous_keys=4,
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


def test_program_change_splits_role_inference_within_same_track_channel() -> None:
    bass = [
        _candidate(start=index * 0.25, pitch=38 + index % 3, track=0, channel=0, program=33)
        for index in range(4)
    ]
    lead = [
        _candidate(start=2.0 + index * 0.25, pitch=72 + index % 3, track=0, channel=0, program=81)
        for index in range(4)
    ]
    refined = _refine_candidate_roles(bass + lead)
    assert {item.role for item in refined if item.program == 33} == {"bass"}
    assert {item.role for item in refined if item.program == 81} == {"melody"}


def test_candidate_metadata_cache_reuses_unchanged_midi_identity(tmp_path: Path, monkeypatch) -> None:
    midi = tmp_path / "song.mid"
    midi.write_bytes(b"test")
    calls = 0

    def fake_collect(_path: object):
        nonlocal calls
        calls += 1
        return [_candidate(start=0.0, pitch=60, track=0)]

    refinements._candidate_cache.clear()
    monkeypatch.setattr(refinements, "_original_collect_candidates", fake_collect)
    first = refinements._refined_collect_candidates(midi)
    second = refinements._refined_collect_candidates(midi)
    refinements._candidate_cache.clear()

    assert calls == 1
    assert first == second
    assert first is not second


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


def test_positive_chord_stagger_is_skipped_if_it_would_cross_modifier_transition() -> None:
    events = [
        me.PlannedEvent(0.000, 20, "note_on", key="a", serial=0),
        me.PlannedEvent(0.000, 20, "note_on", key="s", serial=1),
        me.PlannedEvent(0.000, 20, "note_on", key="d", serial=2),
        me.PlannedEvent(0.000, 20, "note_on", key="f", serial=3),
        me.PlannedEvent(0.100, 0, "note_off", key="a", serial=0),
        me.PlannedEvent(0.100, 0, "note_off", key="s", serial=1),
        me.PlannedEvent(0.100, 0, "note_off", key="d", serial=2),
        me.PlannedEvent(0.100, 0, "note_off", key="f", serial=3),
        me.PlannedEvent(0.115, -20, "state", state=1, serial=10),
    ]
    adjusted, normalized, stagger = _refined_normalize_chord_attacks(
        _plan(events),
        AdaptivePlanOptions(instrument="keyboard", chord_stagger_ms=6),
        {},
    )
    assert stagger == 6
    assert normalized == 0
    assert [event.time for event in adjusted if event.kind == "note_on"] == [0.0, 0.0, 0.0, 0.0]
    assert max(event.time for event in adjusted if event.kind == "note_off") == 0.100


def test_attack_snap_is_skipped_if_it_would_cross_control_state() -> None:
    events = [
        me.PlannedEvent(0.100, 20, "note_on", key="a", serial=0),
        me.PlannedEvent(0.108, -20, "state", state=1, serial=10),
        me.PlannedEvent(0.114, 20, "note_on", key="s", serial=1),
        me.PlannedEvent(0.114, 20, "note_on", key="d", serial=2),
        me.PlannedEvent(0.200, 0, "note_off", key="a", serial=0),
        me.PlannedEvent(0.214, 0, "note_off", key="s", serial=1),
        me.PlannedEvent(0.214, 0, "note_off", key="d", serial=2),
    ]
    metadata = {
        0: SourceMeta(0, 0.100, 60, 90, 0, "Piano", 0, 0, "harmony"),
        1: SourceMeta(1, 0.114, 67, 90, 0, "Piano", 0, 0, "harmony"),
        2: SourceMeta(2, 0.114, 64, 90, 0, "Piano", 0, 0, "harmony"),
    }
    adjusted, normalized, _ = _refined_normalize_chord_attacks(
        _plan(events),
        AdaptivePlanOptions(instrument="keyboard", chord_stagger_ms=0),
        metadata,
    )
    assert normalized == 0
    assert [event.time for event in adjusted if event.kind == "note_on"] == [0.100, 0.114, 0.114]


def test_positive_chord_stagger_remains_allowed_when_transition_has_safe_headroom() -> None:
    events = [
        me.PlannedEvent(0.000, 20, "note_on", key="a", serial=0),
        me.PlannedEvent(0.000, 20, "note_on", key="s", serial=1),
        me.PlannedEvent(0.000, 20, "note_on", key="d", serial=2),
        me.PlannedEvent(0.000, 20, "note_on", key="f", serial=3),
        me.PlannedEvent(0.100, 0, "note_off", key="a", serial=0),
        me.PlannedEvent(0.100, 0, "note_off", key="s", serial=1),
        me.PlannedEvent(0.100, 0, "note_off", key="d", serial=2),
        me.PlannedEvent(0.100, 0, "note_off", key="f", serial=3),
        me.PlannedEvent(0.150, -20, "state", state=1, serial=10),
    ]
    adjusted, normalized, _ = _refined_normalize_chord_attacks(
        _plan(events),
        AdaptivePlanOptions(instrument="keyboard", chord_stagger_ms=6),
        {},
    )
    assert normalized == 1
    assert [round(event.time, 3) for event in adjusted if event.kind == "note_on"] == [0.0, 0.006, 0.012, 0.018]
    assert max(event.time for event in adjusted if event.kind == "note_off") < 0.150


def test_positive_stagger_is_skipped_if_it_would_break_next_same_key_release_gap() -> None:
    events = [
        me.PlannedEvent(0.000, 20, "note_on", key="a", serial=0),
        me.PlannedEvent(0.000, 20, "note_on", key="s", serial=1),
        me.PlannedEvent(0.000, 20, "note_on", key="d", serial=2),
        me.PlannedEvent(0.000, 20, "note_on", key="f", serial=3),
        me.PlannedEvent(0.100, 0, "note_off", key="a", serial=0),
        me.PlannedEvent(0.100, 0, "note_off", key="s", serial=1),
        me.PlannedEvent(0.100, 0, "note_off", key="d", serial=2),
        me.PlannedEvent(0.100, 0, "note_off", key="f", serial=3),
        me.PlannedEvent(0.135, 20, "note_on", key="f", serial=10),
        me.PlannedEvent(0.235, 0, "note_off", key="f", serial=10),
    ]
    adjusted, normalized, _ = _refined_normalize_chord_attacks(
        _plan(events),
        AdaptivePlanOptions(
            instrument="keyboard",
            chord_stagger_ms=6,
            repeated_release_gap_ms=24,
        ),
        {},
    )
    assert normalized == 0
    assert [event.time for event in adjusted if event.kind == "note_on"][:4] == [0.0, 0.0, 0.0, 0.0]
    assert next(event.time for event in adjusted if event.kind == "note_off" and event.serial == 3) == 0.100


def test_snapping_attack_earlier_is_skipped_if_it_would_break_previous_same_key_gap() -> None:
    events = [
        me.PlannedEvent(0.000, 20, "note_on", key="s", serial=20),
        me.PlannedEvent(0.090, 0, "note_off", key="s", serial=20),
        me.PlannedEvent(0.100, 20, "note_on", key="a", serial=0),
        me.PlannedEvent(0.114, 20, "note_on", key="s", serial=1),
        me.PlannedEvent(0.114, 20, "note_on", key="d", serial=2),
        me.PlannedEvent(0.200, 0, "note_off", key="a", serial=0),
        me.PlannedEvent(0.214, 0, "note_off", key="s", serial=1),
        me.PlannedEvent(0.214, 0, "note_off", key="d", serial=2),
    ]
    metadata = {
        0: SourceMeta(0, 0.100, 60, 90, 0, "Piano", 0, 0, "harmony"),
        1: SourceMeta(1, 0.114, 67, 90, 0, "Piano", 0, 0, "harmony"),
        2: SourceMeta(2, 0.114, 64, 90, 0, "Piano", 0, 0, "harmony"),
    }
    adjusted, normalized, _ = _refined_normalize_chord_attacks(
        _plan(events),
        AdaptivePlanOptions(
            instrument="keyboard",
            chord_stagger_ms=0,
            repeated_release_gap_ms=24,
        ),
        metadata,
    )
    assert normalized == 0
    chord_attacks = [event.time for event in adjusted if event.kind == "note_on" and event.serial in {0, 1, 2}]
    assert chord_attacks == [0.100, 0.114, 0.114]


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
