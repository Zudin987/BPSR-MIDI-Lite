from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import studio_youtube as youtube


CORE_CACHE_VERSION = "bp040-core-v3"
ONSET_CLUSTER_SECONDS = 0.065
MIN_CORE_DURATION_SECONDS = 0.14
MIN_CLUSTER_GAP_SECONDS = 0.055
QUANTIZE_SECONDS = 0.02
MAX_CORE_DURATION_SECONDS = 4.0


@dataclass(slots=True)
class CoreNote:
    start: float
    end: float
    pitch: int
    strength: float


def _normalise_note_event(event: Any) -> CoreNote | None:
    """Accept Basic Pitch's tuple events and tolerate attribute-style events."""
    try:
        if isinstance(event, (tuple, list)) and len(event) >= 4:
            start, end, pitch, strength = event[:4]
        else:
            start = getattr(event, "start_time", getattr(event, "start", None))
            end = getattr(event, "end_time", getattr(event, "end", None))
            pitch = getattr(event, "pitch_midi", getattr(event, "pitch", None))
            strength = getattr(event, "amplitude", getattr(event, "velocity", 0.5))
        start_f = float(start)
        end_f = float(end)
        pitch_i = int(round(float(pitch)))
        strength_f = max(0.0, min(1.0, float(strength)))
    except (TypeError, ValueError, OverflowError):
        return None
    if not (0.0 <= start_f < end_f):
        return None
    if not (28 <= pitch_i <= 96):
        return None
    if end_f - start_f < MIN_CORE_DURATION_SECONDS:
        return None
    return CoreNote(start_f, end_f, pitch_i, strength_f)


def _lead_score(note: CoreNote, previous_pitch: int | None) -> float:
    # Prefer a clear mid/high melodic voice, while continuity prevents isolated
    # high harmonics from repeatedly stealing the melody line.
    register_bonus = 0.0
    if 48 <= note.pitch <= 84:
        register_bonus = 0.35
    elif 43 <= note.pitch <= 90:
        register_bonus = 0.12
    continuity_penalty = 0.0
    if previous_pitch is not None:
        continuity_penalty = min(abs(note.pitch - previous_pitch), 24) * 0.035
    return note.strength * 3.8 + register_bonus - continuity_penalty


def _bass_score(note: CoreNote, previous_pitch: int | None) -> float:
    continuity_penalty = 0.0
    if previous_pitch is not None:
        continuity_penalty = min(abs(note.pitch - previous_pitch), 18) * 0.045
    return note.strength * 3.5 - continuity_penalty - abs(note.pitch - 43) * 0.008


def _quantize(value: float) -> float:
    return round(value / QUANTIZE_SECONDS) * QUANTIZE_SECONDS


def extract_core_notes(note_events: Iterable[Any]) -> list[CoreNote]:
    """Reduce a dense transcription to a recognizable melody + optional bass core.

    Full mixed songs make Basic Pitch emit many harmonics and overlapping notes.
    BPSR cannot make useful music from all of them, so Studio keeps at most two
    musically useful voices per onset: one continuous lead and, when strong
    enough, one clearly separated bass note. The normal BPSR fitter still runs
    afterward for instrument/category safety.
    """
    notes = [note for event in note_events if (note := _normalise_note_event(event)) is not None]
    if not notes:
        return []
    notes.sort(key=lambda note: (note.start, note.pitch))

    clusters: list[list[CoreNote]] = []
    for note in notes:
        if not clusters or note.start - clusters[-1][0].start > ONSET_CLUSTER_SECONDS:
            clusters.append([note])
        else:
            clusters[-1].append(note)

    selected: list[CoreNote] = []
    previous_lead: int | None = None
    previous_bass: int | None = None
    previous_cluster_start: float | None = None

    for cluster in clusters:
        cluster_start = min(note.start for note in cluster)
        if (
            previous_cluster_start is not None
            and cluster_start - previous_cluster_start < MIN_CLUSTER_GAP_SECONDS
        ):
            continue

        # Collapse duplicate pitches inside the same tiny onset window.
        strongest_by_pitch: dict[int, CoreNote] = {}
        for note in cluster:
            existing = strongest_by_pitch.get(note.pitch)
            if existing is None or (note.strength, note.end - note.start) > (
                existing.strength,
                existing.end - existing.start,
            ):
                strongest_by_pitch[note.pitch] = note
        candidates = list(strongest_by_pitch.values())
        maximum_strength = max(note.strength for note in candidates)

        preferred_leads = [note for note in candidates if 48 <= note.pitch <= 84]
        if not preferred_leads:
            preferred_leads = [note for note in candidates if 43 <= note.pitch <= 90]
        if not preferred_leads:
            preferred_leads = candidates
        lead = max(preferred_leads, key=lambda note: _lead_score(note, previous_lead))

        chosen = [lead]
        bass_candidates = [
            note
            for note in candidates
            if note.pitch <= 59
            and lead.pitch - note.pitch >= 12
            and note.strength >= maximum_strength * 0.58
        ]
        if bass_candidates:
            bass = max(bass_candidates, key=lambda note: _bass_score(note, previous_bass))
            chosen.append(bass)
            previous_bass = bass.pitch

        for note in chosen:
            start = max(0.0, _quantize(note.start))
            duration = min(MAX_CORE_DURATION_SECONDS, max(MIN_CORE_DURATION_SECONDS, note.end - note.start))
            end = max(start + MIN_CORE_DURATION_SECONDS, _quantize(start + duration))
            selected.append(CoreNote(start, end, note.pitch, note.strength))

        previous_lead = lead.pitch
        previous_cluster_start = cluster_start

    # Avoid overlapping instances of the same MIDI pitch, which otherwise make
    # note-off pairing/retrigger behavior unpredictable in keyboard playback.
    selected.sort(key=lambda note: (note.pitch, note.start, note.end))
    by_pitch: dict[int, list[CoreNote]] = {}
    for note in selected:
        by_pitch.setdefault(note.pitch, []).append(note)
    for pitch_notes in by_pitch.values():
        for previous, current in zip(pitch_notes, pitch_notes[1:]):
            if previous.end >= current.start:
                previous.end = max(previous.start + 0.08, current.start - 0.02)

    selected.sort(key=lambda note: (note.start, note.pitch))
    return selected


def _write_core_midi(notes: list[CoreNote], midi_path: Path) -> None:
    try:
        import mido
    except ImportError as exc:
        raise youtube.StudioError("The Studio MIDI component is missing.") from exc

    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="BPSR Studio core transcription", time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))

    # At 120 BPM and 480 PPQ there are exactly 960 ticks per second.
    events: list[tuple[int, int, Any]] = []
    for note in notes:
        start_tick = max(0, int(round(note.start * 960.0)))
        end_tick = max(start_tick + 1, int(round(note.end * 960.0)))
        velocity = max(42, min(112, int(round(42 + note.strength * 70))))
        events.append((start_tick, 1, mido.Message("note_on", note=note.pitch, velocity=velocity, time=0)))
        events.append((end_tick, 0, mido.Message("note_off", note=note.pitch, velocity=0, time=0)))

    events.sort(key=lambda item: (item[0], item[1]))  # note-off before note-on on the same tick
    previous_tick = 0
    for tick, _priority, message in events:
        message.time = max(0, tick - previous_tick)
        track.append(message)
        previous_tick = tick

    midi_path.parent.mkdir(parents=True, exist_ok=True)
    midi.save(str(midi_path))


def _transcribe_core_audio(
    audio_path: Path,
    midi_path: Path,
    *,
    progress: Any | None = None,
) -> None:
    if progress is not None:
        progress("Listening for the main musical notes…")
    try:
        from basic_pitch.inference import predict
    except ImportError as exc:
        raise youtube.StudioError("The Studio transcription component is missing.") from exc

    try:
        _model_output, _midi_data, note_events = predict(
            audio_path,
            youtube._basic_pitch_model(),
            onset_threshold=0.62,
            frame_threshold=0.40,
            minimum_note_length=140.0,
            minimum_frequency=27.50,
            maximum_frequency=2093.00,
            multiple_pitch_bends=False,
            melodia_trick=True,
        )
    except Exception as exc:
        raise youtube.StudioError("Audio-to-MIDI conversion failed for this song.") from exc
    if not note_events:
        raise youtube.StudioError("No clear musical notes were detected in this audio.")

    if progress is not None:
        progress("Cleaning the transcription into a melody + bass core…")
    core = extract_core_notes(note_events)
    if not core:
        raise youtube.StudioError("The song did not contain enough clear notes for a clean BPSR MIDI.")
    try:
        _write_core_midi(core, midi_path)
    except youtube.StudioError:
        raise
    except Exception as exc:
        raise youtube.StudioError("The converted MIDI could not be saved to temporary cache.") from exc


def install_core_transcription() -> None:
    """Install Studio-only cleanup without changing Lite or upstream Basic Pitch."""
    youtube.TRANSCRIPTION_CACHE_VERSION = CORE_CACHE_VERSION
    youtube._transcribe_audio = _transcribe_core_audio
