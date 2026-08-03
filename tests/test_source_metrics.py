from pathlib import Path

import mido

from midi_engine import PlanOptions, build_plan


def test_build_plan_reports_source_complexity_metrics(tmp_path: Path):
    path = tmp_path / "metrics.mid"
    midi = mido.MidiFile(type=1, ticks_per_beat=480)

    melody = mido.MidiTrack()
    melody.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    for index, pitch in enumerate((60, 64, 67, 72)):
        melody.append(mido.Message("note_on", note=pitch, velocity=80, time=120 if index == 0 else 0))
    for index, pitch in enumerate((60, 64, 67, 72)):
        melody.append(mido.Message("note_off", note=pitch, velocity=0, time=120 if index == 0 else 0))

    drums = mido.MidiTrack()
    drums.append(mido.Message("note_on", channel=9, note=36, velocity=100, time=0))
    drums.append(mido.Message("note_off", channel=9, note=36, velocity=0, time=120))

    midi.tracks.extend((melody, drums))
    midi.save(path)

    plan = build_plan(
        path,
        PlanOptions(
            speed_percent=100,
            max_notes_per_chord=2,
            ignore_percussion=True,
        ),
    )

    assert plan.source_note_count == 4
    assert plan.source_track_count == 2
    assert plan.source_percussion_notes == 1
    assert plan.max_source_chord == 4
    assert plan.max_planned_chord == 2
    assert plan.chord_removed_notes == 2
