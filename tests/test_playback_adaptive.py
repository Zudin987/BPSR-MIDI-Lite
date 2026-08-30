from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import mido

import midi_engine as me
import playback_adaptive as adaptive
from playback_adaptive import (
    AdaptivePlanOptions,
    CalibrationProfile,
    SourceAnalysis,
    SourceMeta,
    _adaptive_apply_note_lengths,
    _adaptive_limit_notes_per_chord,
    _adaptive_resolve_retrigger_conflicts,
    _auto_tune_options,
    _collect_candidates,
    _normalize_chord_attacks,
)
from playback_calibration_ui import build_calibration_test_plan
from playback_overhaul import EnhancedMidiPlan


def _planned(
    *,
    start: float,
    end: float,
    pitch: int,
    key: str,
    serial: int,
    velocity: int = 90,
) -> me.PlannedNote:
    return me.PlannedNote(
        source_start=start,
        source_end=end,
        start=start,
        end=end,
        pitch=pitch,
        page=1,
        octave=0,
        key=key,
        velocity=velocity,
        serial=serial,
    )


def _source(pitch: int, serial: int, *, start: float = 0.0, end: float = 0.4) -> me.SourceNote:
    return me.SourceNote(start=start, end=end, pitch=pitch, velocity=90, serial=serial)


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
        source_note_count=3,
        source_duration=1.0,
        source_track_count=1,
        source_percussion_notes=0,
        max_source_chord=3,
        max_planned_chord=3,
        max_simultaneous_keys=3,
        chord_removed_notes=0,
    )


def test_humanized_block_chord_is_normalized_into_one_runtime_batch() -> None:
    events = [
        me.PlannedEvent(0.000, 20, "note_on", key="a", serial=0),
        me.PlannedEvent(0.005, 20, "note_on", key="s", serial=1),
        me.PlannedEvent(0.010, 20, "note_on", key="d", serial=2),
        me.PlannedEvent(0.200, 0, "note_off", key="a", serial=0),
        me.PlannedEvent(0.205, 0, "note_off", key="s", serial=1),
        me.PlannedEvent(0.210, 0, "note_off", key="d", serial=2),
    ]
    metadata = {
        0: SourceMeta(0, 0.000, 60, 90, 0, "Piano", 0, 0, "harmony"),
        1: SourceMeta(1, 0.005, 67, 90, 0, "Piano", 0, 0, "harmony"),
        2: SourceMeta(2, 0.010, 64, 90, 0, "Piano", 0, 0, "harmony"),
    }
    adjusted, normalized, stagger = _normalize_chord_attacks(
        _plan(events),
        AdaptivePlanOptions(instrument="keyboard", chord_stagger_ms=0),
        metadata,
    )
    attacks = [event.time for event in adjusted if event.kind == "note_on"]
    assert normalized == 1
    assert stagger == 0
    assert attacks == [0.0, 0.0, 0.0]


def test_intentional_fast_monotonic_arpeggio_is_not_snapped_to_chord() -> None:
    events = [
        me.PlannedEvent(0.000, 20, "note_on", key="a", serial=0),
        me.PlannedEvent(0.008, 20, "note_on", key="s", serial=1),
        me.PlannedEvent(0.014, 20, "note_on", key="d", serial=2),
        me.PlannedEvent(0.200, 0, "note_off", key="a", serial=0),
        me.PlannedEvent(0.208, 0, "note_off", key="s", serial=1),
        me.PlannedEvent(0.214, 0, "note_off", key="d", serial=2),
    ]
    metadata = {
        0: SourceMeta(0, 0.000, 60, 90, 0, "Piano", 0, 0, "harmony"),
        1: SourceMeta(1, 0.008, 64, 90, 0, "Piano", 0, 0, "harmony"),
        2: SourceMeta(2, 0.014, 67, 90, 0, "Piano", 0, 0, "harmony"),
    }
    adjusted, normalized, _ = _normalize_chord_attacks(
        _plan(events),
        AdaptivePlanOptions(instrument="keyboard", chord_stagger_ms=0),
        metadata,
    )
    assert normalized == 0
    assert [event.time for event in adjusted if event.kind == "note_on"] == [0.0, 0.008, 0.014]


def test_priority_collision_can_evict_accompaniment_to_preserve_later_melody() -> None:
    metadata = {
        0: SourceMeta(0, 0.0, 60, 55, 0, "Harmony", 0, 0, "harmony"),
        1: SourceMeta(1, 0.05, 72, 120, 1, "Lead Melody", 1, 80, "melody"),
    }
    token_meta = adaptive._metadata_context.set(metadata)
    token_metrics = adaptive._metrics_context.set({"priority_evictions": 0})
    try:
        resolved, merged, dropped = _adaptive_resolve_retrigger_conflicts(
            [
                _planned(start=0.0, end=0.09, pitch=60, key="a", serial=0, velocity=55),
                _planned(start=0.05, end=0.14, pitch=72, key="a", serial=1, velocity=120),
            ],
            AdaptivePlanOptions(
                instrument="keyboard",
                minimum_note_ms=90,
                hard_press_floor_ms=40,
                repeated_release_gap_ms=24,
            ),
        )
        assert len(resolved) == 1
        assert resolved[0].serial == 1
        assert merged == 0
        assert dropped == 1
        assert adaptive._metrics_context.get()["priority_evictions"] == 1
    finally:
        adaptive._metadata_context.reset(token_meta)
        adaptive._metrics_context.reset(token_metrics)


def test_root_aware_keyboard_thinning_keeps_inferred_root_and_top_voice() -> None:
    group = [
        _source(52, 0),
        _source(55, 1),
        _source(60, 2),
        _source(64, 3),
        _source(67, 4),
    ]
    token_meta = adaptive._metadata_context.set({})
    token_analysis = adaptive._analysis_context.set(SourceAnalysis(max_chord=5))
    token_options = adaptive._options_context.set(
        AdaptivePlanOptions(instrument="keyboard", adaptive_auto=False)
    )
    try:
        kept, removed = _adaptive_limit_notes_per_chord(group, 3, "keyboard")
    finally:
        adaptive._metadata_context.reset(token_meta)
        adaptive._analysis_context.reset(token_analysis)
        adaptive._options_context.reset(token_options)
    pitches = {note.pitch for note in kept}
    assert removed == 2
    assert 60 in pitches
    assert 67 in pitches


def test_context_gate_engine_shortens_low_register_and_protects_same_key_retrigger() -> None:
    notes = [
        _planned(start=0.0, end=0.08, pitch=43, key="a", serial=0),
        _planned(start=0.12, end=0.20, pitch=43, key="a", serial=1),
        _planned(start=0.30, end=0.38, pitch=76, key="q", serial=2),
    ]
    result = _adaptive_apply_note_lengths(
        notes,
        AdaptivePlanOptions(
            instrument="keyboard",
            minimum_note_ms=90,
            hard_press_floor_ms=40,
            repeated_release_gap_ms=24,
            short_note_tail_ms=20,
        ),
    )
    first = next(note for note in result if note.serial == 0)
    high = next(note for note in result if note.serial == 2)
    assert first.end <= 0.096 + 1e-9
    assert first.end - first.start >= 0.040
    assert high.end - high.start > first.end - first.start


def test_auto_tuner_uses_calibration_and_dense_mode_for_bursts() -> None:
    options = AdaptivePlanOptions(
        instrument="guitar",
        max_notes_per_chord=0,
        articulation_mode="balanced",
        adaptive_auto=True,
    )
    analysis = SourceAnalysis(max_chord=7, peak_250ms_nps=14.0, fast_repeat_ratio=0.25)
    calibration = CalibrationProfile(
        instrument="guitar",
        minimum_clean_hold_ms=112,
        hard_floor_ms=48,
        retrigger_gap_ms=31,
        chord_stagger_ms=2,
        modifier_settle_ms=68,
        max_polyphony=3,
        calibrated=True,
    )
    tuned = _auto_tune_options(options, analysis, calibration)
    assert tuned.minimum_note_ms == 112
    assert tuned.hard_press_floor_ms == 48
    assert tuned.repeated_release_gap_ms == 31
    assert tuned.max_notes_per_chord == 3
    assert tuned.chord_stagger_ms == 2
    assert tuned.octave_switch_lead_ms >= 68
    assert tuned.articulation_mode == "dense"


def test_track_channel_program_metadata_recognizes_named_melody_and_gm_bass(tmp_path: Path) -> None:
    path = tmp_path / "roles.mid"
    mid = mido.MidiFile(ticks_per_beat=480)

    lead = mido.MidiTrack()
    lead.append(mido.MetaMessage("track_name", name="Lead Melody", time=0))
    lead.append(mido.Message("program_change", channel=0, program=80, time=0))
    lead.append(mido.Message("note_on", channel=0, note=72, velocity=100, time=0))
    lead.append(mido.Message("note_off", channel=0, note=72, velocity=0, time=240))
    mid.tracks.append(lead)

    bass = mido.MidiTrack()
    bass.append(mido.MetaMessage("track_name", name="Track 2", time=0))
    bass.append(mido.Message("program_change", channel=1, program=33, time=0))
    bass.append(mido.Message("note_on", channel=1, note=40, velocity=90, time=0))
    bass.append(mido.Message("note_off", channel=1, note=40, velocity=0, time=240))
    mid.tracks.append(bass)
    mid.save(path)

    candidates = _collect_candidates(path)
    assert candidates[0].role == "melody"
    assert candidates[0].track_name == "Lead Melody"
    assert candidates[0].program == 80
    assert candidates[1].role == "bass"
    assert candidates[1].channel == 1


def test_calibration_profile_round_trip_uses_local_json(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "bpsr_calibration.json"
    monkeypatch.setattr(adaptive, "calibration_path", lambda: target)
    profile = CalibrationProfile(
        instrument="keyboard",
        minimum_clean_hold_ms=101,
        hard_floor_ms=44,
        retrigger_gap_ms=27,
        chord_stagger_ms=1,
        modifier_settle_ms=63,
        max_polyphony=5,
    )
    adaptive.save_calibration_profile(profile)
    loaded = adaptive.get_calibration_profile("keyboard")
    assert loaded.calibrated is True
    assert loaded.minimum_clean_hold_ms == 101
    assert loaded.retrigger_gap_ms == 27
    assert loaded.max_polyphony == 5


def test_guided_calibration_plans_cover_hold_repeat_chord_and_modifier() -> None:
    hold = build_calibration_test_plan("keyboard", "hold", 70)
    repeat = build_calibration_test_plan("keyboard", "repeat", 24)
    chord = build_calibration_test_plan("guitar", "chord", 2)
    modifier = build_calibration_test_plan("keyboard", "modifier", 60)
    assert abs(
        next(event.time for event in hold.events if event.kind == "note_off")
        - next(event.time for event in hold.events if event.kind == "note_on")
        - 0.070
    ) < 1e-9
    repeat_on = [event.time for event in repeat.events if event.kind == "note_on"]
    assert abs((repeat_on[1] - repeat_on[0]) - 0.104) < 1e-9
    chord_on = [event.time for event in chord.events if event.kind == "note_on"]
    assert chord_on == [0.5, 0.502, 0.504, 0.506]
    assert [event.kind for event in modifier.events].count("state") == 2


def test_launchers_install_adaptive_layer_after_v32_overhaul_and_advanced_ui() -> None:
    for filename in ("modern_launcher.py", "studio_launcher.py"):
        source = Path(filename).read_text(encoding="utf-8")
        assert "from playback_adaptive import install_adaptive_arranger" in source
        assert "from playback_calibration_ui import install_calibration_lab" in source
        assert source.index("install_playback_overhaul(app)") < source.index("install_adaptive_arranger(app)")
        assert source.index("install_advanced_playback_profile(app)") < source.index("install_adaptive_arranger(app)")
        assert source.index("install_adaptive_arranger(app)") < source.index("install_calibration_lab(app)")
