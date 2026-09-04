from __future__ import annotations

import midi_engine as me
import playback_adaptive as adaptive
import playback_evidence_refinements as evidence


def _candidate(
    start: float,
    pitch: int,
    track: int,
    *,
    role: str = "harmony",
    name: str = "Piano",
    program: int = 0,
):
    return adaptive._CandidateMeta(
        start=start,
        pitch=pitch,
        velocity=90,
        track_index=track,
        track_name=name,
        channel=0,
        program=program,
        role=role,
    )


def test_two_hand_polyphonic_piano_recovers_top_melody_and_low_bass_envelopes() -> None:
    candidates = []
    for index in range(6):
        start = index * 0.25
        candidates.extend(
            [
                _candidate(start, 67, 0),
                _candidate(start + 0.003, 71, 0),
                _candidate(start + 0.006, 74, 0),
                _candidate(start, 38, 1),
                _candidate(start + 0.003, 43, 1),
                _candidate(start + 0.006, 50, 1),
            ]
        )

    refined = evidence._refine_polyphonic_roles(candidates)
    upper = [item for item in refined if item.track_index == 0]
    lower = [item for item in refined if item.track_index == 1]

    assert sum(item.role == "melody" for item in upper) == 6
    assert sum(item.role == "bass" for item in lower) == 6
    assert all(item.role in {"melody", "harmony"} for item in upper)
    assert all(item.role in {"bass", "harmony"} for item in lower)


def test_separated_piano_lines_promote_unknown_lower_track_to_bass() -> None:
    candidates = []
    for index in range(12):
        start = index * 0.25
        candidates.append(
            _candidate(start, 78 + index % 5, 0, role="melody", name="Piano")
        )
        candidates.append(
            _candidate(start + 0.004, 55 + index % 7, 1, role="unknown", name="Piano")
        )

    refined = evidence._refine_polyphonic_roles(candidates)
    upper = [item for item in refined if item.track_index == 0]
    lower = [item for item in refined if item.track_index == 1]

    assert {item.role for item in upper} == {"melody"}
    assert {item.role for item in lower} == {"bass"}


def test_separated_non_keyboard_lines_are_not_reclassified() -> None:
    candidates = []
    for index in range(12):
        start = index * 0.25
        candidates.append(
            _candidate(start, 78 + index % 4, 0, role="melody", name="Track", program=40)
        )
        candidates.append(
            _candidate(start + 0.004, 54 + index % 5, 1, role="unknown", name="Track", program=40)
        )

    refined = evidence._refine_polyphonic_roles(candidates)
    assert {item.role for item in refined if item.track_index == 0} == {"melody"}
    assert {item.role for item in refined if item.track_index == 1} == {"unknown"}


def test_explicit_harmony_name_is_never_rewritten_as_envelope_role() -> None:
    candidates = []
    for index in range(6):
        start = index * 0.25
        for pitch in (48, 52, 55):
            candidates.append(_candidate(start, pitch, 0, name="Harmony"))
    refined = evidence._refine_polyphonic_roles(candidates)
    assert {item.role for item in refined} == {"harmony"}


def test_dense_non_keyboard_harmony_is_not_rewritten_as_piano_hands() -> None:
    candidates = []
    for index in range(6):
        start = index * 0.25
        for pitch in (67, 71, 74):
            candidates.append(_candidate(start, pitch, 0, name="Track", program=48))
        for pitch in (38, 43, 50):
            candidates.append(_candidate(start, pitch, 1, name="Track", program=48))

    refined = evidence._refine_polyphonic_roles(candidates)
    assert {item.role for item in refined} == {"harmony"}


def test_nearby_polyphonic_streams_are_not_invented_as_separate_hands() -> None:
    candidates = []
    for index in range(6):
        start = index * 0.25
        for pitch in (60, 64, 67):
            candidates.append(_candidate(start, pitch, 0))
        for pitch in (62, 65, 69):
            candidates.append(_candidate(start, pitch, 1))

    refined = evidence._refine_polyphonic_roles(candidates)
    assert {item.role for item in refined} == {"harmony"}


def _source(serial: int, start: float, pitch: int) -> me.SourceNote:
    return me.SourceNote(
        start=start,
        end=start + 0.12,
        pitch=pitch,
        velocity=90,
        serial=serial,
    )


def _meta(note: me.SourceNote, role: str) -> adaptive.SourceMeta:
    return adaptive.SourceMeta(
        serial=note.serial,
        source_start=note.start,
        pitch=note.pitch,
        velocity=note.velocity,
        track_index=0,
        track_name="Track",
        channel=0,
        program=0,
        role=role,
    )


def test_bass_auto_uses_reliable_detected_bass_line(monkeypatch) -> None:
    notes = []
    metadata = {}
    serial = 0
    for index in range(10):
        start = index * 0.25
        bass = _source(serial, start, 40 + index % 3)
        serial += 1
        melody = _source(serial, start, 67 + index % 4)
        serial += 1
        notes.extend((bass, melody))
        metadata[bass.serial] = _meta(bass, "bass")
        metadata[melody.serial] = _meta(melody, "melody")

    monkeypatch.setattr(
        evidence,
        "_previous_limit_notes_per_chord",
        lambda selected, maximum, instrument: (list(selected), 0),
    )
    options_token = adaptive._options_context.set(
        adaptive.AdaptivePlanOptions(
            instrument="bass",
            mapping_method="transpose",
            adaptive_auto=True,
        )
    )
    metadata_token = adaptive._metadata_context.set(metadata)
    metrics = {}
    metrics_token = adaptive._metrics_context.set(metrics)
    try:
        kept, removed = evidence._evidence_limit_notes_per_chord(notes, 1, "bass")
    finally:
        adaptive._options_context.reset(options_token)
        adaptive._metadata_context.reset(metadata_token)
        adaptive._metrics_context.reset(metrics_token)

    assert len(kept) == 10
    assert all(metadata[note.serial].role == "bass" for note in kept)
    assert removed == 0
    assert metrics["arranged_out_notes"] == 10
    assert metrics["bass_line_notes"] == 10


def test_sparse_bass_evidence_falls_back_to_existing_arranger(monkeypatch) -> None:
    notes = []
    metadata = {}
    for index in range(12):
        note = _source(index, index * 0.25, 60 + index % 4)
        notes.append(note)
        metadata[note.serial] = _meta(note, "bass" if index < 4 else "melody")

    calls = []

    def passthrough(selected, maximum, instrument):
        calls.append((list(selected), maximum, instrument))
        return list(selected), 0

    monkeypatch.setattr(evidence, "_previous_limit_notes_per_chord", passthrough)
    options_token = adaptive._options_context.set(
        adaptive.AdaptivePlanOptions(
            instrument="bass",
            mapping_method="transpose",
            adaptive_auto=True,
        )
    )
    metadata_token = adaptive._metadata_context.set(metadata)
    try:
        kept, removed = evidence._evidence_limit_notes_per_chord(notes, 1, "bass")
    finally:
        adaptive._options_context.reset(options_token)
        adaptive._metadata_context.reset(metadata_token)

    assert kept == notes
    assert removed == 0
    assert len(calls) == 1
    assert calls[0][0] == notes


def test_raw_bass_does_not_auto_extract_roles(monkeypatch) -> None:
    notes = [_source(index, index * 0.25, 40 + index % 3) for index in range(10)]
    metadata = {note.serial: _meta(note, "bass") for note in notes}
    calls = []

    def passthrough(selected, maximum, instrument):
        calls.append((list(selected), maximum, instrument))
        return list(selected), 0

    monkeypatch.setattr(evidence, "_previous_limit_notes_per_chord", passthrough)
    options_token = adaptive._options_context.set(
        adaptive.AdaptivePlanOptions(
            instrument="bass",
            mapping_method="skip",
            adaptive_auto=False,
        )
    )
    metadata_token = adaptive._metadata_context.set(metadata)
    try:
        kept, removed = evidence._evidence_limit_notes_per_chord(notes, 0, "bass")
    finally:
        adaptive._options_context.reset(options_token)
        adaptive._metadata_context.reset(metadata_token)

    assert kept == notes
    assert removed == 0
    assert len(calls) == 1
    assert calls[0][0] == notes
