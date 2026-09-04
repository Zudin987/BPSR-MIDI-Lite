from __future__ import annotations

from types import SimpleNamespace

import midi_engine as me
import playback_adaptive as adaptive
import playback_evidence_refinements as evidence
from suitability import SuitabilityResult


def _candidate(start: float, pitch: int, track: int, *, role: str = "harmony", name: str = "Piano"):
    return adaptive._CandidateMeta(
        start=start,
        pitch=pitch,
        velocity=90,
        track_index=track,
        track_name=name,
        channel=0,
        program=0,
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


def test_explicit_harmony_name_is_never_rewritten_as_envelope_role() -> None:
    candidates = []
    for index in range(6):
        start = index * 0.25
        for pitch in (48, 52, 55):
            candidates.append(_candidate(start, pitch, 0, name="Harmony"))
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
    assert removed == 10
    assert metrics["arranged_out_notes"] == 10
    assert metrics["bass_line_notes"] == 10


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


def test_intentional_bass_arrangement_is_not_scored_as_destructive_loss(monkeypatch) -> None:
    monkeypatch.setattr(
        evidence,
        "_previous_evaluate_suitability",
        lambda plan: SuitabilityResult(
            code="complex",
            label="Very complex",
            summary="old",
            score=3,
            notes_per_second=3.0,
            changed_ratio=0.70,
            reasons=("70% of notes need remapping or removal",),
        ),
    )
    plan = SimpleNamespace(
        source_note_count=100,
        arranged_out_notes=70,
        bass_line_notes=30,
        folded_notes=0,
        skipped_notes=0,
        chord_removed_notes=70,
        retrigger_compressed_notes=0,
        retrigger_merged_notes=0,
        retrigger_dropped_notes=0,
        max_source_chord=2,
        max_planned_chord=1,
        max_simultaneous_keys=1,
    )

    result = evidence._evidence_evaluate_suitability(plan)

    assert result.code == "good"
    assert result.score == 0
    assert result.changed_ratio == 0.0
    assert not any("need remapping or removal" in reason for reason in result.reasons)
    assert any("Auto Bass Line" in reason for reason in result.reasons)
