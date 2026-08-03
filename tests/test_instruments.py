from pathlib import Path

import mido

from midi_engine import PlanOptions, build_plan


def make_midi(path: Path, notes: list[int], simultaneous: bool = False) -> None:
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    if simultaneous:
        for index, pitch in enumerate(notes):
            track.append(mido.Message("note_on", note=pitch, velocity=80, time=120 if index == 0 else 0))
        for index, pitch in enumerate(notes):
            track.append(mido.Message("note_off", note=pitch, velocity=0, time=120 if index == 0 else 0))
    else:
        for pitch in notes:
            track.append(mido.Message("note_on", note=pitch, velocity=80, time=240))
            track.append(mido.Message("note_off", note=pitch, velocity=0, time=120))
    midi.tracks.append(track)
    midi.save(path)


def note_on_keys(plan) -> list[str]:
    return [event.key for event in plan.events if event.kind == "note_on"]


def test_guitar_tier1_matches_default_c3_b4(tmp_path: Path) -> None:
    path = tmp_path / "guitar1.mid"
    make_midi(path, [48, 71])
    plan = build_plan(path, PlanOptions(instrument="guitar", unlock_tier="tier1", speed_percent=100))
    assert note_on_keys(plan) == ["z", "j"]
    assert plan.page_switches == 0
    assert plan.octave_switches == 0


def test_guitar_tier2_uses_ctrl_and_default_for_e2_b4(tmp_path: Path) -> None:
    path = tmp_path / "guitar2.mid"
    make_midi(path, [40, 71])
    plan = build_plan(path, PlanOptions(instrument="guitar", unlock_tier="tier2", speed_percent=100))
    assert plan.planned_min_pitch == 40
    assert plan.planned_max_pitch == 71
    assert set(note_on_keys(plan)) == {"c", "u"}
    assert plan.page_switches == 0
    assert any(event.kind == "state" and event.state == -1 for event in plan.events)


def test_guitar_tier3_reaches_d6_without_page_keys(tmp_path: Path) -> None:
    path = tmp_path / "guitar3.mid"
    make_midi(path, [40, 86])
    plan = build_plan(path, PlanOptions(instrument="guitar", unlock_tier="tier3", speed_percent=100))
    assert plan.planned_min_pitch == 40
    assert plan.planned_max_pitch == 86
    assert plan.page_switches == 0
    assert any(event.kind == "state" and event.state == 1 for event in plan.events)


def test_bass_tier1_default_layout_e1_b2(tmp_path: Path) -> None:
    path = tmp_path / "bass1.mid"
    make_midi(path, [28, 47])
    plan = build_plan(path, PlanOptions(instrument="bass", unlock_tier="tier1", speed_percent=100))
    assert note_on_keys(plan) == ["d", "u"]
    assert plan.planned_min_pitch == 28
    assert plan.planned_max_pitch == 47
    assert plan.page_switches == 0
    assert plan.octave_switches == 0


def test_bass_tier2_high_layout_e1_b3(tmp_path: Path) -> None:
    path = tmp_path / "bass2.mid"
    make_midi(path, [28, 59])
    plan = build_plan(path, PlanOptions(instrument="bass", unlock_tier="tier2", speed_percent=100))
    assert note_on_keys(plan) == ["c", "u"]
    assert plan.planned_min_pitch == 28
    assert plan.planned_max_pitch == 59
    assert plan.page_switches == 0
    assert any(event.kind == "state" and event.state == 1 for event in plan.events)


def test_bass_single_note_chord_limit_keeps_lowest_note(tmp_path: Path) -> None:
    path = tmp_path / "bass_chord.mid"
    make_midi(path, [28, 40, 52], simultaneous=True)
    plan = build_plan(
        path,
        PlanOptions(
            instrument="bass",
            unlock_tier="tier2",
            max_notes_per_chord=1,
            speed_percent=100,
        ),
    )
    assert plan.note_count == 1
    assert plan.planned_min_pitch == 28
    assert plan.planned_max_pitch == 28


def test_guitar_custom_full_range_can_use_page_keys(tmp_path: Path) -> None:
    path = tmp_path / "guitar_full.mid"
    make_midi(path, [21, 108])
    plan = build_plan(
        path,
        PlanOptions(
            instrument="guitar",
            unlock_tier="tier4",
            mode="full",
            speed_percent=100,
        ),
    )
    assert plan.planned_min_pitch == 21
    assert plan.planned_max_pitch == 108
    assert plan.page_switches > 0


def test_bass_rejects_nonexistent_tier3(tmp_path: Path) -> None:
    path = tmp_path / "bass_bad.mid"
    make_midi(path, [28])
    try:
        build_plan(path, PlanOptions(instrument="bass", unlock_tier="tier3"))
    except ValueError as exc:
        assert "bass" in str(exc).lower()
    else:
        raise AssertionError("Bass tier3 should be rejected")
