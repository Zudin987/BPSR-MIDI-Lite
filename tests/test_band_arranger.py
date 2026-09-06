from __future__ import annotations

import midi_engine as me
from band_arranger import (
    BandPlanOptions,
    DEFAULT_ACTIVE_PARTS,
    _drum_plan_options,
    normalize_drum_pitch,
    split_band_notes,
)
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


def test_explicit_roles_are_split_without_duplication() -> None:
    notes = [_note(1, 76), _note(2, 60), _note(3, 40), _note(4, 60)]
    metadata = {
        1: _meta(1, 76, role="melody", track=1),
        2: _meta(2, 60, role="harmony", track=2),
        3: _meta(3, 40, role="bass", track=3, program=33),
        4: _meta(4, 60, role="drums", track=4, channel=9),
    }
    split = split_band_notes(notes, metadata)
    assert [note.serial for note in split["keyboard"]] == [1]
    assert [note.serial for note in split["guitar"]] == [2]
    assert [note.serial for note in split["bass"]] == [3]
    assert [note.serial for note in split["drums"]] == [4]
    serials = [note.serial for part in split.values() for note in part]
    assert sorted(serials) == [1, 2, 3, 4]
    assert len(serials) == len(set(serials))


def test_harmony_only_piano_recovers_top_voice_for_keyboard() -> None:
    notes = [
        _note(1, 48, start=0.0),
        _note(2, 60, start=0.0),
        _note(3, 67, start=0.0),
        _note(4, 50, start=0.5),
        _note(5, 62, start=0.5),
        _note(6, 69, start=0.5),
    ]
    metadata = {
        note.serial: _meta(note.serial, note.pitch, role="harmony", name="Piano Harmony")
        for note in notes
    }
    split = split_band_notes(notes, metadata)
    assert [note.pitch for note in split["keyboard"]] == [67, 69]
    assert [note.pitch for note in split["guitar"]] == [48, 60, 50, 62]


def test_single_ambiguous_chord_stream_splits_top_voice_and_lower_tones() -> None:
    notes = [_note(1, 55), _note(2, 64), _note(3, 71)]
    metadata = {
        note.serial: _meta(note.serial, note.pitch, role="unknown", name="Piano")
        for note in notes
    }
    split = split_band_notes(notes, metadata)
    assert [note.pitch for note in split["keyboard"]] == [71]
    assert [note.pitch for note in split["guitar"]] == [55, 64]


def test_gm_guitar_and_bass_programs_route_to_matching_parts() -> None:
    notes = [_note(1, 60), _note(2, 43)]
    metadata = {
        1: _meta(1, 60, program=25, track=1),
        2: _meta(2, 43, program=34, track=2),
    }
    split = split_band_notes(notes, metadata)
    assert [note.serial for note in split["guitar"]] == [1]
    assert [note.serial for note in split["bass"]] == [2]


def test_three_player_lineup_without_drums_drops_only_percussion() -> None:
    notes = [_note(1, 76), _note(2, 60), _note(3, 40), _note(4, 38)]
    metadata = {
        1: _meta(1, 76, role="melody", track=1),
        2: _meta(2, 60, role="harmony", track=2),
        3: _meta(3, 40, role="bass", track=3),
        4: _meta(4, 38, role="drums", track=4, channel=9),
    }
    split = split_band_notes(notes, metadata, ("keyboard", "guitar", "bass"))
    assert [note.serial for note in split["keyboard"]] == [1]
    assert [note.serial for note in split["guitar"]] == [2]
    assert [note.serial for note in split["bass"]] == [3]
    assert split["drums"] == []
    serials = [note.serial for part in split.values() for note in part]
    assert sorted(serials) == [1, 2, 3]


def test_missing_guitar_reassigns_harmony_to_keyboard() -> None:
    notes = [_note(1, 76), _note(2, 60), _note(3, 40)]
    metadata = {
        1: _meta(1, 76, role="melody"),
        2: _meta(2, 60, role="harmony"),
        3: _meta(3, 40, role="bass"),
    }
    split = split_band_notes(notes, metadata, ("keyboard", "bass"))
    assert [note.serial for note in split["keyboard"]] == [1, 2]
    assert split["guitar"] == []
    assert [note.serial for note in split["bass"]] == [3]


def test_missing_keyboard_reassigns_melody_to_guitar() -> None:
    notes = [_note(1, 76), _note(2, 60), _note(3, 40)]
    metadata = {
        1: _meta(1, 76, role="melody"),
        2: _meta(2, 60, role="harmony"),
        3: _meta(3, 40, role="bass"),
    }
    split = split_band_notes(notes, metadata, ("guitar", "bass"))
    assert split["keyboard"] == []
    assert [note.serial for note in split["guitar"]] == [1, 2]
    assert [note.serial for note in split["bass"]] == [3]


def test_verified_drum_mapping_is_fixed_c4_to_b5_without_octave_modes() -> None:
    assert normalize_drum_pitch(35) == 60
    assert normalize_drum_pitch(36) == 61
    assert normalize_drum_pitch(58) == 83
    assert normalize_drum_pitch(59) == 60
    assert normalize_drum_pitch(60) == 60
    assert normalize_drum_pitch(83) == 83

    options = _drum_plan_options(BandPlanOptions(band_enabled=True, band_part="drums"))
    assert options.instrument == "keyboard"
    assert options.mode == "stable"
    assert options.unlock_tier == "tier2"
    assert options.mapping_method == "skip"
    assert options.ignore_percussion is False
    assert options.use_sustain_pedal is False


def test_drum_c4_b5_uses_verified_default_key_span() -> None:
    state = me.KeyboardState(page=1, octave=0)
    assert me.key_for_pitch(60, state) == "a"   # C4
    assert me.key_for_pitch(71, state) == "j"   # B4
    assert me.key_for_pitch(72, state) == "q"   # C5
    assert me.key_for_pitch(83, state) == "u"   # B5


def test_band_options_default_off_and_keep_existing_adaptive_contract() -> None:
    options = BandPlanOptions()
    assert options.band_enabled is False
    assert options.band_part == "keyboard"
    assert options.band_active_parts == DEFAULT_ACTIVE_PARTS
    assert options.band_arrangement_version == 2
    assert options.adaptive_auto is True
