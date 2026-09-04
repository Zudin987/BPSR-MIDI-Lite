from __future__ import annotations

import band_arranger
import band_musical_sharing as sharing
import midi_engine as me
import playback_adaptive as adaptive
from playback_adaptive import SourceMeta


def _note(serial: int, pitch: int, *, start: float = 0.0) -> me.SourceNote:
    return me.SourceNote(start=start, end=start + 0.25, pitch=pitch, velocity=90, serial=serial)


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


def test_strongly_authored_roles_remain_exclusive() -> None:
    _with_originals()
    notes = [_note(1, 76), _note(2, 60), _note(3, 43), _note(4, 38)]
    metadata = {
        1: _meta(1, 76, role="melody", name="Lead Melody"),
        2: _meta(2, 60, role="harmony", program=25, name="Electric Guitar"),
        3: _meta(3, 43, role="bass", program=34, name="Bass"),
        4: _meta(4, 38, role="drums", channel=9, name="Drums"),
    }

    split = sharing.split_band_notes_shared(notes, metadata)
    assert [note.serial for note in split["keyboard"]] == [1]
    assert [note.serial for note in split["guitar"]] == [2]
    assert [note.serial for note in split["bass"]] == [3]
    assert [note.serial for note in split["drums"]] == [4]


def test_named_drum_track_is_detected_without_gm_channel_10() -> None:
    _with_originals()
    for name in ("Drums", "Percussion", "Kick + Snare", "Hi-Hat"):
        assert sharing.enhanced_role_from_source(name, 0, 0) == "drums"


def test_normal_non_drum_track_keeps_original_classifier() -> None:
    _with_originals()
    assert sharing.enhanced_role_from_source("Lead Vocal", 0, 80) == adaptive._role_from_source(
        "Lead Vocal", 0, 80
    )


def test_shared_arrangement_version_is_v3() -> None:
    assert sharing.BAND_SHARED_ARRANGEMENT_VERSION == 3
