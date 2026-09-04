from __future__ import annotations

import band_arranger
import band_musical_sharing as sharing
import midi_engine as me
import playback_adaptive as adaptive
from playback_adaptive import SourceMeta


def _note(
    serial: int,
    pitch: int,
    *,
    start: float = 0.0,
    duration: float = 0.25,
) -> me.SourceNote:
    return me.SourceNote(
        start=start,
        end=start + duration,
        pitch=pitch,
        velocity=90,
        serial=serial,
    )


def _meta(
    serial: int,
    pitch: int,
    *,
    role: str = "unknown",
    track: int = 0,
    program: int = 0,
    name: str = "Track",
    channel: int = 0,
) -> SourceMeta:
    return SourceMeta(
        serial=serial,
        source_start=0.0,
        pitch=pitch,
        velocity=90,
        track_index=track,
        track_name=name,
        channel=channel,
        program=program,
        role=role,  # type: ignore[arg-type]
    )


def _with_originals() -> None:
    # Tests call the v4 layer directly without running the app installer.
    sharing._original_split = band_arranger.split_band_notes
    sharing._original_role_from_source = adaptive._role_from_source


def test_generic_harmony_is_shared_by_piano_and_guitar() -> None:
    _with_originals()
    notes = [_note(1, 60), _note(2, 64), _note(3, 67)]
    metadata = {
        note.serial: _meta(
            note.serial,
            note.pitch,
            role="harmony",
            name="Piano Chords",
            program=0,
        )
        for note in notes
    }

    split = sharing.split_band_notes_shared(notes, metadata, ("keyboard", "guitar"))
    assert [note.serial for note in split["keyboard"]] == [1, 2, 3]
    assert [note.serial for note in split["guitar"]] == [1, 2, 3]


def test_dense_shared_chord_keeps_full_piano_and_top_three_guitar_voices() -> None:
    _with_originals()
    notes = [_note(index, pitch) for index, pitch in enumerate((48, 55, 60, 64, 67), start=1)]
    metadata = {
        note.serial: _meta(note.serial, note.pitch, role="harmony", name="Piano Chords")
        for note in notes
    }

    split = sharing.split_band_notes_shared(notes, metadata, ("keyboard", "guitar"))
    assert [note.pitch for note in split["keyboard"]] == [48, 55, 60, 64, 67]
    assert [note.pitch for note in split["guitar"]] == [60, 64, 67]


def test_strongly_authored_roles_remain_exclusive() -> None:
    _with_originals()
    notes = [_note(1, 76), _note(2, 60), _note(3, 43), _note(4, 38)]
    metadata = {
        1: _meta(1, 76, role="melody", name="Lead Melody", track=1),
        2: _meta(2, 60, role="harmony", program=25, name="Electric Guitar", track=2),
        3: _meta(3, 43, role="bass", program=34, name="Bass", track=3),
        4: _meta(4, 38, role="drums", channel=9, name="Drums", track=4),
    }

    split = sharing.split_band_notes_shared(notes, metadata)
    assert [note.serial for note in split["keyboard"]] == [1]
    assert [note.serial for note in split["guitar"]] == [2]
    assert [note.serial for note in split["bass"]] == [3]
    assert [note.serial for note in split["drums"]] == [4]


def test_phrase_segmentation_can_change_one_track_from_lead_to_shared_harmony() -> None:
    _with_originals()
    notes = [
        _note(1, 72, start=0.0),
        _note(2, 74, start=0.25),
        _note(3, 76, start=0.50),
        _note(4, 60, start=2.0),
        _note(5, 64, start=2.0),
        _note(6, 67, start=2.0),
    ]
    metadata = {
        1: _meta(1, 72, role="melody", name="Lead", track=1),
        2: _meta(2, 74, role="melody", name="Lead", track=1),
        3: _meta(3, 76, role="melody", name="Lead", track=1),
        4: _meta(4, 60, role="harmony", name="Piano Chords", track=1),
        5: _meta(5, 64, role="harmony", name="Piano Chords", track=1),
        6: _meta(6, 67, role="harmony", name="Piano Chords", track=1),
    }

    split = sharing.split_band_notes_shared(notes, metadata, ("keyboard", "guitar"))
    assert [note.serial for note in split["keyboard"]] == [1, 2, 3, 4, 5, 6]
    assert [note.serial for note in split["guitar"]] == [4, 5, 6]


def test_high_ambiguous_melody_prefers_keyboard_when_guitar_fit_is_poor() -> None:
    _with_originals()
    notes = [
        _note(1, 88, start=0.00),
        _note(2, 91, start=0.30),
        _note(3, 93, start=0.60),
        _note(4, 95, start=0.90),
    ]
    metadata = {
        note.serial: _meta(note.serial, note.pitch, role="unknown", name="Track", track=1)
        for note in notes
    }

    split = sharing.split_band_notes_shared(notes, metadata, ("keyboard", "guitar"))
    assert [note.serial for note in split["keyboard"]] == [1, 2, 3, 4]
    assert split["guitar"] == []


def test_named_drum_track_is_detected_without_gm_channel_10() -> None:
    _with_originals()
    for name in ("Drums", "Percussion", "Kick + Snare", "Hi-Hat"):
        assert sharing.enhanced_role_from_source(name, 0, 0) == "drums"


def test_unlabelled_repetitive_short_hits_can_be_rescued_as_drums() -> None:
    _with_originals()
    pitches = (36, 42, 38, 42, 36, 42, 38, 42, 36, 42, 38, 42)
    notes = [
        _note(index, pitch, start=(index - 1) * 0.10, duration=0.06)
        for index, pitch in enumerate(pitches, start=1)
    ]
    metadata = {
        note.serial: _meta(note.serial, note.pitch, role="unknown", name="Track", track=5)
        for note in notes
    }

    split = sharing.split_band_notes_shared(
        notes,
        metadata,
        ("keyboard", "guitar", "drums"),
    )
    assert split["drums"]
    assert not split["keyboard"]
    assert not split["guitar"]
    assert all(60 <= note.pitch <= 83 for note in split["drums"])


def test_normal_non_drum_track_keeps_original_classifier() -> None:
    _with_originals()
    assert sharing.enhanced_role_from_source("Lead Vocal", 0, 80) == adaptive._role_from_source(
        "Lead Vocal", 0, 80
    )


def test_v4_continuity_prefers_same_state_for_similar_adjacent_phrases() -> None:
    first = sharing._decision(
        [_note(1, 60), _note(2, 64), _note(3, 67)],
        {
            1: _meta(1, 60, role="harmony", name="Piano"),
            2: _meta(2, 64, role="harmony", name="Piano"),
            3: _meta(3, 67, role="harmony", name="Piano"),
        },
    )
    second = sharing._decision(
        [_note(4, 62), _note(5, 65), _note(6, 69)],
        {
            4: _meta(4, 62, role="harmony", name="Piano"),
            5: _meta(5, 65, role="harmony", name="Piano"),
            6: _meta(6, 69, role="harmony", name="Piano"),
        },
    )
    states = sharing._viterbi_states([first, second], ("keyboard", "guitar"))
    assert states == ["shared", "shared"]


def test_shared_arrangement_version_is_v4() -> None:
    assert sharing.BAND_SHARED_ARRANGEMENT_VERSION == 4
