from pathlib import Path

import mido

from studio_core_transcription import CoreNote, _write_core_midi, extract_core_notes


def test_core_extraction_rejects_harmonic_clutter_and_keeps_melody_plus_bass() -> None:
    events = [
        (0.00, 0.45, 40, 0.72, None),
        (0.01, 0.40, 60, 0.88, None),
        (0.02, 0.35, 64, 0.42, None),
        (0.02, 0.30, 88, 0.97, None),  # strong high harmonic; not the lead when a normal lead exists
        (0.30, 0.70, 43, 0.65, None),
        (0.31, 0.68, 62, 0.82, None),
        (0.31, 0.60, 91, 0.96, None),
    ]

    notes = extract_core_notes(events)
    first = [note.pitch for note in notes if note.start < 0.1]
    second = [note.pitch for note in notes if 0.25 <= note.start < 0.4]

    assert set(first) == {40, 60}
    assert set(second) == {43, 62}
    assert all(pitch not in {88, 91} for pitch in [note.pitch for note in notes])


def test_core_extraction_limits_density_and_drops_tiny_noise() -> None:
    events = [
        (0.00, 0.08, 72, 1.0, None),  # too short
        (0.10, 0.40, 60, 0.9, None),
        (0.12, 0.42, 64, 0.8, None),
        (0.13, 0.45, 67, 0.7, None),
        (0.14, 0.50, 43, 0.7, None),
    ]

    notes = extract_core_notes(events)
    assert len(notes) <= 2
    assert 72 not in [note.pitch for note in notes]


def test_core_midi_writer_preserves_real_time_and_two_voice_limit(tmp_path: Path) -> None:
    path = tmp_path / "core.mid"
    notes = [
        CoreNote(0.0, 0.5, 60, 0.9),
        CoreNote(0.0, 0.5, 40, 0.7),
        CoreNote(0.5, 1.0, 62, 0.9),
    ]
    _write_core_midi(notes, path)

    midi = mido.MidiFile(path)
    absolute = 0
    note_ons: list[tuple[int, int]] = []
    for message in midi.tracks[0]:
        absolute += message.time
        if message.type == "note_on" and message.velocity > 0:
            note_ons.append((absolute, message.note))

    assert {item for item in note_ons if item[0] == 0} == {(0, 40), (0, 60)}
    assert (480, 62) in note_ons  # 0.5 sec at 120 BPM / 480 PPQ
