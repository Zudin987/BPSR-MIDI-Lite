from __future__ import annotations

import threading
from pathlib import Path

import midi_engine as me
from playback_overhaul import (
    EnhancedMidiPlayer,
    EnhancedPlanOptions,
    TIMING_PROFILES,
    _apply_simulated_sustain,
    _desired_note_duration,
    _enhanced_choose_group_states,
    _enhanced_limit_notes_per_chord,
    _enhanced_resolve_retrigger_conflicts,
    _send_physical_batch,
    build_calibration_plan,
)


def _planned(
    *,
    start: float,
    end: float,
    pitch: int = 60,
    key: str = "a",
    serial: int = 0,
    page: int = 1,
    octave: int = 0,
) -> me.PlannedNote:
    return me.PlannedNote(
        source_start=start,
        source_end=end,
        start=start,
        end=end,
        pitch=pitch,
        page=page,
        octave=octave,
        key=key,
        velocity=100,
        serial=serial,
    )


def _source(*, start: float, end: float, pitch: int, serial: int, velocity: int = 90) -> me.SourceNote:
    return me.SourceNote(start=start, end=end, pitch=pitch, velocity=velocity, serial=serial)


def test_instruments_have_distinct_bpsr_timing_profiles() -> None:
    assert TIMING_PROFILES["keyboard"].musical_min_ms == 90
    assert TIMING_PROFILES["guitar"].musical_min_ms == 105
    assert TIMING_PROFILES["bass"].musical_min_ms == 120
    assert TIMING_PROFILES["keyboard"].hard_floor_ms < TIMING_PROFILES["keyboard"].musical_min_ms
    assert TIMING_PROFILES["bass"].retrigger_gap_ms > TIMING_PROFILES["keyboard"].retrigger_gap_ms


def test_short_notes_receive_game_tail_but_long_notes_keep_authored_length() -> None:
    options = EnhancedPlanOptions(
        instrument="keyboard",
        minimum_note_ms=90,
        hard_press_floor_ms=40,
        short_note_tail_ms=20,
        articulation_mode="musical",
    )
    assert _desired_note_duration(0.020, options) >= 0.090
    assert _desired_note_duration(0.060, options) >= 0.090
    assert 0.795 <= _desired_note_duration(0.800, options) <= 0.805


def test_retrigger_can_compress_musical_hold_but_never_breaks_hard_floor() -> None:
    options = EnhancedPlanOptions(
        instrument="keyboard",
        minimum_note_ms=90,
        hard_press_floor_ms=40,
        repeated_release_gap_ms=24,
    )
    notes = [
        _planned(start=0.0, end=0.100, serial=0),
        _planned(start=0.080, end=0.180, serial=1),
    ]
    resolved, merged, dropped = _enhanced_resolve_retrigger_conflicts(notes, options)
    assert merged == 0
    assert dropped == 0
    assert len(resolved) == 2
    first_duration = resolved[0].end - resolved[0].start
    assert first_duration >= 0.040
    assert abs(first_duration - 0.056) < 1e-6


def test_impossible_same_pitch_repeat_merges_instead_of_emitting_fake_attack() -> None:
    options = EnhancedPlanOptions(
        instrument="keyboard",
        minimum_note_ms=90,
        hard_press_floor_ms=40,
        repeated_release_gap_ms=24,
    )
    resolved, merged, dropped = _enhanced_resolve_retrigger_conflicts(
        [
            _planned(start=0.0, end=0.090, serial=0),
            _planned(start=0.050, end=0.140, serial=1),
        ],
        options,
    )
    assert len(resolved) == 1
    assert merged == 1
    assert dropped == 0
    assert resolved[0].end >= 0.140


def test_impossible_different_pitch_collision_on_same_physical_key_is_dropped() -> None:
    options = EnhancedPlanOptions(
        instrument="keyboard",
        minimum_note_ms=90,
        hard_press_floor_ms=40,
        repeated_release_gap_ms=24,
    )
    resolved, merged, dropped = _enhanced_resolve_retrigger_conflicts(
        [
            _planned(start=0.0, end=0.090, pitch=60, key="a", serial=0),
            _planned(start=0.050, end=0.140, pitch=72, key="a", serial=1),
        ],
        options,
    )
    assert len(resolved) == 1
    assert merged == 0
    assert dropped == 1


def test_chord_reduction_keeps_bass_top_melody_and_strong_harmony() -> None:
    group = [
        _source(start=0.0, end=0.4, pitch=48, serial=0),  # C bass
        _source(start=0.0, end=0.4, pitch=52, serial=1),  # E
        _source(start=0.0, end=0.4, pitch=55, serial=2),  # G fifth
        _source(start=0.0, end=0.4, pitch=59, serial=3),  # B
        _source(start=0.0, end=0.4, pitch=72, serial=4),  # top melody C
    ]
    kept, removed = _enhanced_limit_notes_per_chord(group, 3, "keyboard")
    pitches = {note.pitch for note in kept}
    assert removed == 2
    assert pitches == {48, 55, 72}


def test_simulated_sustain_extends_release_to_cc64_off() -> None:
    notes = [_source(start=0.0, end=0.50, pitch=60, serial=0)]
    sustained, changed = _apply_simulated_sustain(
        notes,
        [(0.20, True), (1.00, False)],
        1.00,
    )
    assert changed == 1
    assert sustained[0].end == 1.00


def test_state_planner_does_not_switch_octave_while_previous_note_tail_is_active() -> None:
    groups = [
        [_source(start=0.0, end=1.0, pitch=60, serial=0)],
        [_source(start=0.2, end=0.3, pitch=84, serial=1)],
    ]
    options = EnhancedPlanOptions(
        instrument="keyboard",
        mode="stable",
        unlock_tier="tier2",
        mapping_method="octave",
        minimum_note_ms=90,
        hard_press_floor_ms=40,
        repeated_release_gap_ms=24,
    )
    mapped = _enhanced_choose_group_states(groups, options)
    assert mapped[0].state == mapped[1].state
    assert mapped[1].pitches == [72]


class _FakeSender:
    def __init__(self) -> None:
        self.backend = "fake"
        self._lock = threading.RLock()
        self._held: set[str] = set()
        self.events: list[tuple[str, bool]] = []

    def _send(self, key: str, key_up: bool) -> None:
        self.events.append((key, not key_up))


def test_batch_sender_preserves_simultaneous_chord_and_deduplicates_state() -> None:
    sender = _FakeSender()
    sent = _send_physical_batch(sender, [("a", True), ("s", True), ("d", True), ("f", True)])
    assert sent == 4
    assert sender._held == {"a", "s", "d", "f"}
    assert sender.events == [("a", True), ("s", True), ("d", True), ("f", True)]
    assert _send_physical_batch(sender, [("a", True)]) == 0
    assert _send_physical_batch(sender, [("a", False), ("s", False)]) == 2


def test_runtime_expands_control_tap_without_blocking_note_timeline() -> None:
    player = EnhancedMidiPlayer()
    plan = build_calibration_plan("keyboard")
    plan.events = [
        me.PlannedEvent(time=0.000, priority=-20, kind="state", state=1, serial=0),
        me.PlannedEvent(time=0.055, priority=20, kind="note_on", key="a", serial=1),
    ]
    actions = player._expand_actions(plan)
    assert [(action.kind, action.key, round(action.time, 3)) for action in actions] == [
        ("control_down", "shift", 0.000),
        ("control_up", "shift", 0.016),
        ("note_on", "a", 0.055),
    ]


def test_calibration_plan_contains_hold_gap_and_batched_chord_sections() -> None:
    plan = build_calibration_plan("keyboard")
    assert plan.mode == "stable"
    assert plan.page_switches == 0
    assert plan.octave_switches == 0
    assert plan.max_simultaneous_keys == 4
    first_on = next(event for event in plan.events if event.kind == "note_on")
    first_off = next(event for event in plan.events if event.kind == "note_off")
    assert abs((first_off.time - first_on.time) - 0.020) < 1e-9
    chord_times: dict[float, int] = {}
    for event in plan.events:
        if event.kind == "note_on":
            chord_times[event.time] = chord_times.get(event.time, 0) + 1
    assert max(chord_times.values()) == 4


def test_launchers_install_overhaul_after_pause_aware_gaming_runtime() -> None:
    for filename in ("modern_launcher.py", "studio_launcher.py"):
        source = Path(filename).read_text(encoding="utf-8")
        assert "from playback_overhaul import install_playback_overhaul" in source
        assert source.index("install_gaming_runtime_2026(app)") < source.index("install_playback_overhaul(app)")
