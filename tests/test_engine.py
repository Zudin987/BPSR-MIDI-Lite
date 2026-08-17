from pathlib import Path

import mido

from midi_engine import PlanOptions, build_plan


def make_test_midi(
    path: Path,
    notes: list[int],
    gap_ticks: int = 120,
    duration_ticks: int = 120,
) -> None:
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    for note in notes:
        track.append(mido.Message("note_on", note=note, velocity=80, time=gap_ticks))
        track.append(mido.Message("note_off", note=note, velocity=0, time=duration_ticks))
    midi.tracks.append(track)
    midi.save(path)


def test_stable_mode_never_uses_page_keys(tmp_path: Path) -> None:
    midi_path = tmp_path / "stable.mid"
    make_test_midi(midi_path, [24, 36, 60, 84, 108])
    plan = build_plan(midi_path, PlanOptions(mode="stable"))

    assert 36 <= plan.planned_min_pitch <= 95
    assert 36 <= plan.planned_max_pitch <= 95
    assert plan.page_switches == 0
    assert all(event.kind != "page" for event in plan.events)


def test_full_range_can_keep_exact_extreme_notes(tmp_path: Path) -> None:
    midi_path = tmp_path / "full.mid"
    make_test_midi(midi_path, [60, 21, 95, 108], gap_ticks=20, duration_ticks=20)
    plan = build_plan(
        midi_path,
        PlanOptions(
            mode="full",
            speed_percent=100,
            note_length_percent=100,
            minimum_note_ms=20,
            unlocked_max_pitch=108,
            page_switch_delay_ms=180,
        ),
    )

    assert plan.folded_notes == 0
    assert plan.planned_min_pitch == 21
    assert plan.planned_max_pitch == 108
    assert plan.page_switches > 0
    assert plan.added_delay > 0


def test_ensemble_avoids_unsafe_fast_page_jump(tmp_path: Path) -> None:
    midi_path = tmp_path / "ensemble.mid"
    make_test_midi(midi_path, [60, 21, 60], gap_ticks=10, duration_ticks=10)
    plan = build_plan(
        midi_path,
        PlanOptions(
            mode="ensemble",
            speed_percent=100,
            note_length_percent=100,
            minimum_note_ms=20,
            unlocked_max_pitch=108,
            page_switch_delay_ms=250,
        ),
    )

    # The notes are too close for a 250 ms page animation. Ensemble mode keeps
    # the global timeline and octave-folds rather than inserting a page change.
    assert plan.page_switches == 0
    assert plan.folded_notes >= 1


def test_note_length_is_extended_but_repeat_can_retrigger(tmp_path: Path) -> None:
    midi_path = tmp_path / "length.mid"
    make_test_midi(midi_path, [60, 60], gap_ticks=120, duration_ticks=60)
    plan = build_plan(
        midi_path,
        PlanOptions(
            mode="stable",
            speed_percent=100,
            note_length_percent=150,
            minimum_note_ms=20,
            repeated_release_gap_ms=35,
        ),
    )

    note_ons = [event for event in plan.events if event.kind == "note_on"]
    note_offs = [event for event in plan.events if event.kind == "note_off"]
    assert len(note_ons) == 2
    assert len(note_offs) == 2
    assert note_offs[0].time < note_ons[1].time



def test_short_note_gets_small_bpsr_hold_without_changing_tempo(tmp_path: Path) -> None:
    midi_path = tmp_path / "short_hold.mid"
    make_test_midi(midi_path, [60], gap_ticks=0, duration_ticks=10)
    plan = build_plan(
        midi_path,
        PlanOptions(
            mode="stable",
            speed_percent=100,
            note_length_percent=100,
            minimum_note_ms=70,
        ),
    )

    note_on = next(event for event in plan.events if event.kind == "note_on")
    note_off = next(event for event in plan.events if event.kind == "note_off")
    assert note_off.time - note_on.time >= 0.070 - 1e-9


def test_unrelated_note_onset_does_not_cut_authored_hold(tmp_path: Path) -> None:
    midi_path = tmp_path / "polyphony.mid"
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    track.append(mido.Message("note_on", note=60, velocity=80, time=0))
    track.append(mido.Message("note_on", note=64, velocity=80, time=48))
    track.append(mido.Message("note_off", note=64, velocity=0, time=48))
    track.append(mido.Message("note_off", note=60, velocity=0, time=144))
    midi.tracks.append(track)
    midi.save(midi_path)

    plan = build_plan(
        midi_path,
        PlanOptions(
            mode="stable",
            speed_percent=100,
            note_length_percent=100,
            minimum_note_ms=70,
        ),
    )

    c_on = next(event for event in plan.events if event.kind == "note_on" and event.serial == 0)
    c_off = next(event for event in plan.events if event.kind == "note_off" and event.serial == 0)
    e_on = next(event for event in plan.events if event.kind == "note_on" and event.serial == 1)
    assert e_on.time < c_off.time
    assert c_off.time - c_on.time >= 0.249


def test_dangling_note_is_capped_instead_of_held_to_song_end(tmp_path: Path) -> None:
    midi_path = tmp_path / "dangling.mid"
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    track.append(mido.Message("note_on", note=60, velocity=80, time=0))
    track.append(mido.MetaMessage("text", text="later event", time=4800))
    midi.tracks.append(track)
    midi.save(midi_path)

    plan = build_plan(
        midi_path,
        PlanOptions(
            mode="stable",
            speed_percent=100,
            note_length_percent=100,
            minimum_note_ms=70,
        ),
    )

    note_on = next(event for event in plan.events if event.kind == "note_on")
    note_off = next(event for event in plan.events if event.kind == "note_off")
    assert 0.119 <= note_off.time - note_on.time <= 0.501

def test_full_range_prefers_middle_page_ctrl_when_exact_mapping_ties(tmp_path: Path) -> None:
    midi_path = tmp_path / "middle_tie.mid"
    make_test_midi(midi_path, [60, 36, 38, 40, 60], gap_ticks=240, duration_ticks=120)
    plan = build_plan(
        midi_path,
        PlanOptions(
            mode="full",
            speed_percent=100,
            note_length_percent=100,
            minimum_note_ms=20,
            unlocked_max_pitch=108,
        ),
    )

    # C2-D2-E2 can be played on either left/default or middle/Ctrl. Starting
    # from the middle page must prefer Ctrl instead of pressing <.
    assert plan.page_switches == 0
    assert plan.octave_switches >= 1


def test_two_page_move_is_emitted_as_separate_spaced_presses(tmp_path: Path) -> None:
    midi_path = tmp_path / "two_page.mid"
    make_test_midi(midi_path, [21, 108], gap_ticks=960, duration_ticks=120)
    delay_ms = 220
    plan = build_plan(
        midi_path,
        PlanOptions(
            mode="full",
            speed_percent=100,
            note_length_percent=100,
            minimum_note_ms=20,
            unlocked_max_pitch=108,
            page_switch_delay_ms=delay_ms,
        ),
    )

    page_events = [event for event in plan.events if event.kind == "page"]
    assert len(page_events) >= 3  # middle->left, then left->middle->right

    current_page = 1
    for event in page_events:
        assert event.page is not None
        assert abs(event.page - current_page) == 1
        current_page = event.page

    # At least one pair belongs to the two-step left-to-right move.
    spaced_pairs = [
        later.time - earlier.time
        for earlier, later in zip(page_events, page_events[1:])
        if earlier.page == 1 and later.page == 2
    ]
    assert spaced_pairs
    assert min(spaced_pairs) >= delay_ms / 1000.0 - 1e-9


def test_skip_mapping_reports_dropped_notes(tmp_path: Path) -> None:
    midi_path = tmp_path / "skip.mid"
    make_test_midi(midi_path, [21, 60, 108], gap_ticks=120, duration_ticks=120)
    plan = build_plan(
        midi_path,
        PlanOptions(
            mode="stable",
            speed_percent=100,
            mapping_method="skip",
        ),
    )

    assert plan.skipped_notes == 2
    assert plan.note_count == 1
    assert plan.folded_notes == 0


def test_chord_limit_keeps_bass_and_melody(tmp_path: Path) -> None:
    midi_path = tmp_path / "chord.mid"
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    for index, pitch in enumerate([48, 55, 60, 72]):
        track.append(mido.Message("note_on", note=pitch, velocity=80, time=120 if index == 0 else 0))
    for index, pitch in enumerate([48, 55, 60, 72]):
        track.append(mido.Message("note_off", note=pitch, velocity=0, time=120 if index == 0 else 0))
    midi.tracks.append(track)
    midi.save(midi_path)

    plan = build_plan(
        midi_path,
        PlanOptions(
            mode="stable",
            speed_percent=100,
            max_notes_per_chord=2,
        ),
    )

    assert plan.note_count == 2
    assert plan.filtered_notes == 2
    note_keys = [event.key for event in plan.events if event.kind == "note_on"]
    assert len(note_keys) == 2


def test_auto_transpose_does_not_change_song_that_already_fits(tmp_path: Path) -> None:
    midi_path = tmp_path / "fits.mid"
    make_test_midi(midi_path, [60, 64, 67], gap_ticks=120, duration_ticks=120)
    plan = build_plan(
        midi_path,
        PlanOptions(
            mode="stable",
            speed_percent=100,
            mapping_method="transpose",
        ),
    )

    assert plan.transposed_semitones == 0
    assert plan.folded_notes == 0


def test_ensemble_skip_can_keep_page_and_silence_unsafe_group(tmp_path: Path) -> None:
    midi_path = tmp_path / "ensemble_skip.mid"
    make_test_midi(midi_path, [60, 21, 60], gap_ticks=10, duration_ticks=10)
    plan = build_plan(
        midi_path,
        PlanOptions(
            mode="ensemble",
            speed_percent=100,
            note_length_percent=100,
            minimum_note_ms=20,
            unlocked_max_pitch=108,
            mapping_method="skip",
            page_switch_delay_ms=250,
        ),
    )

    assert plan.page_switches == 0
    assert plan.skipped_notes >= 1
    assert plan.note_count >= 1


def test_unlock_tier1_forces_c3_b4_without_page_or_modifier(tmp_path: Path) -> None:
    midi_path = tmp_path / "tier1.mid"
    make_test_midi(midi_path, [21, 48, 71, 95, 108])
    plan = build_plan(
        midi_path,
        PlanOptions(mode="full", unlock_tier="tier1", speed_percent=100),
    )

    assert plan.effective_min_pitch == 48
    assert plan.effective_max_pitch == 71
    assert 48 <= plan.planned_min_pitch <= plan.planned_max_pitch <= 71
    assert plan.page_switches == 0
    assert plan.octave_switches == 0
    assert all(event.kind not in {"page", "state"} for event in plan.events)


def test_unlock_tier2_uses_default_and_shift_only(tmp_path: Path) -> None:
    midi_path = tmp_path / "tier2.mid"
    make_test_midi(midi_path, [48, 60, 84, 95])
    plan = build_plan(
        midi_path,
        PlanOptions(mode="full", unlock_tier="tier2", speed_percent=100),
    )

    assert plan.effective_min_pitch == 48
    assert plan.effective_max_pitch == 95
    assert plan.page_switches == 0
    assert all(event.page is None for event in plan.events if event.kind == "page")
    assert all(
        event.state in {0, 1}
        for event in plan.events
        if event.kind == "state"
    )


def test_unlock_tier3_c2_b6_never_uses_page_keys(tmp_path: Path) -> None:
    midi_path = tmp_path / "tier3.mid"
    make_test_midi(midi_path, [21, 35, 36, 60, 95, 108], gap_ticks=480)
    plan = build_plan(
        midi_path,
        PlanOptions(
            mode="full",
            unlock_tier="tier3",
            speed_percent=100,
            note_length_percent=100,
        ),
    )

    assert plan.effective_min_pitch == 36
    assert plan.effective_max_pitch == 95
    assert 36 <= plan.planned_min_pitch <= plan.planned_max_pitch <= 95
    assert plan.page_switches == 0
    assert all(event.kind != "page" for event in plan.events)
    assert all(
        event.state in {-1, 0, 1}
        for event in plan.events
        if event.kind == "state"
    )


def test_unlock_tier4_can_preserve_c8_with_right_page(tmp_path: Path) -> None:
    midi_path = tmp_path / "tier4.mid"
    make_test_midi(midi_path, [60, 108], gap_ticks=960, duration_ticks=120)
    plan = build_plan(
        midi_path,
        PlanOptions(
            mode="full",
            unlock_tier="tier4",
            speed_percent=100,
            note_length_percent=100,
        ),
    )

    assert plan.effective_min_pitch == 21
    assert plan.effective_max_pitch == 108
    assert plan.planned_max_pitch == 108
    assert plan.page_switches > 0
    assert any(event.kind == "page" and event.page == 2 for event in plan.events)


def test_stable_mode_uses_safe_subset_of_large_unlock_tier(tmp_path: Path) -> None:
    midi_path = tmp_path / "stable_tier4.mid"
    make_test_midi(midi_path, [21, 36, 60, 95, 108])
    plan = build_plan(
        midi_path,
        PlanOptions(mode="stable", unlock_tier="tier4", speed_percent=100),
    )

    assert plan.configured_min_pitch == 21
    assert plan.configured_max_pitch == 108
    assert plan.effective_min_pitch == 36
    assert plan.effective_max_pitch == 95
    assert plan.page_switches == 0
    assert 36 <= plan.planned_min_pitch <= plan.planned_max_pitch <= 95
