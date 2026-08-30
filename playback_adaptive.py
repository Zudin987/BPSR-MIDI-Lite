from __future__ import annotations

import contextvars
import json
import math
import os
import time
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any, Literal

import mido

import midi_engine as me
import playback_overhaul as po
import suitability as suitability_module

Role = Literal["melody", "bass", "harmony", "drums", "unknown"]


@dataclass(frozen=True, slots=True)
class SourceMeta:
    serial: int
    source_start: float
    pitch: int
    velocity: int
    track_index: int
    track_name: str
    channel: int
    program: int
    role: Role


@dataclass(frozen=True, slots=True)
class SourceAnalysis:
    note_count: int = 0
    duration: float = 0.0
    max_chord: int = 0
    peak_100ms_nps: float = 0.0
    peak_250ms_nps: float = 0.0
    p95_500ms_nps: float = 0.0
    fast_repeat_ratio: float = 0.0
    metadata_tracks: int = 0


@dataclass(frozen=True, slots=True)
class AdaptiveDefaults:
    max_polyphony: int
    chord_stagger_ms: int


ADAPTIVE_DEFAULTS: dict[str, AdaptiveDefaults] = {
    "keyboard": AdaptiveDefaults(max_polyphony=4, chord_stagger_ms=0),
    "guitar": AdaptiveDefaults(max_polyphony=3, chord_stagger_ms=0),
    "bass": AdaptiveDefaults(max_polyphony=1, chord_stagger_ms=0),
}


@dataclass(frozen=True, slots=True)
class CalibrationProfile:
    instrument: str
    minimum_clean_hold_ms: int
    hard_floor_ms: int
    retrigger_gap_ms: int
    chord_stagger_ms: int
    modifier_settle_ms: int
    max_polyphony: int
    calibrated: bool = False
    updated_at: float = 0.0


def _default_calibration(instrument: str) -> CalibrationProfile:
    timing = po.TIMING_PROFILES[instrument]
    adaptive = ADAPTIVE_DEFAULTS[instrument]
    return CalibrationProfile(
        instrument=instrument,
        minimum_clean_hold_ms=timing.musical_min_ms,
        hard_floor_ms=timing.hard_floor_ms,
        retrigger_gap_ms=timing.retrigger_gap_ms,
        chord_stagger_ms=adaptive.chord_stagger_ms,
        modifier_settle_ms=55,
        max_polyphony=adaptive.max_polyphony,
        calibrated=False,
        updated_at=0.0,
    )


def calibration_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home())) / "BPSR MIDI Lite"
    else:
        base = Path.home() / ".config" / "bpsr-midi-lite"
    base.mkdir(parents=True, exist_ok=True)
    return base / "bpsr_calibration.json"


def load_calibration_profiles() -> dict[str, CalibrationProfile]:
    profiles = {instrument: _default_calibration(instrument) for instrument in ADAPTIVE_DEFAULTS}
    path = calibration_path()
    if not path.exists():
        return profiles
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return profiles
    if not isinstance(raw, dict):
        return profiles
    for instrument, default in tuple(profiles.items()):
        saved = raw.get(instrument)
        if not isinstance(saved, dict):
            continue
        try:
            profiles[instrument] = CalibrationProfile(
                instrument=instrument,
                minimum_clean_hold_ms=max(15, int(saved.get("minimum_clean_hold_ms", default.minimum_clean_hold_ms))),
                hard_floor_ms=max(15, int(saved.get("hard_floor_ms", default.hard_floor_ms))),
                retrigger_gap_ms=max(1, int(saved.get("retrigger_gap_ms", default.retrigger_gap_ms))),
                chord_stagger_ms=max(0, min(12, int(saved.get("chord_stagger_ms", default.chord_stagger_ms)))),
                modifier_settle_ms=max(10, int(saved.get("modifier_settle_ms", default.modifier_settle_ms))),
                max_polyphony=max(1, min(12, int(saved.get("max_polyphony", default.max_polyphony)))),
                calibrated=bool(saved.get("calibrated", False)),
                updated_at=float(saved.get("updated_at", 0.0)),
            )
        except (TypeError, ValueError):
            continue
    return profiles


def save_calibration_profile(profile: CalibrationProfile) -> None:
    profiles = load_calibration_profiles()
    profiles[profile.instrument] = replace(profile, calibrated=True, updated_at=time.time())
    payload = {
        instrument: {
            "minimum_clean_hold_ms": item.minimum_clean_hold_ms,
            "hard_floor_ms": item.hard_floor_ms,
            "retrigger_gap_ms": item.retrigger_gap_ms,
            "chord_stagger_ms": item.chord_stagger_ms,
            "modifier_settle_ms": item.modifier_settle_ms,
            "max_polyphony": item.max_polyphony,
            "calibrated": item.calibrated,
            "updated_at": item.updated_at,
        }
        for instrument, item in profiles.items()
    }
    path = calibration_path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def get_calibration_profile(instrument: str) -> CalibrationProfile:
    return load_calibration_profiles().get(instrument, _default_calibration(instrument))


@dataclass(slots=True)
class AdaptivePlanOptions(po.EnhancedPlanOptions):
    adaptive_auto: bool = True
    adaptive_chord_limit: int = 0
    chord_stagger_ms: int = -1


@dataclass(slots=True)
class AdaptiveMidiPlan(po.EnhancedMidiPlan):
    adaptive_enabled: bool = True
    normalized_chords: int = 0
    priority_evictions: int = 0
    local_peak_nps: float = 0.0
    p95_window_nps: float = 0.0
    fast_repeat_ratio: float = 0.0
    metadata_tracks: int = 0
    melody_role_notes: int = 0
    bass_role_notes: int = 0
    harmony_role_notes: int = 0
    auto_chord_limit: int = 0
    chord_stagger_ms: int = 0
    calibration_source: str = "defaults"
    arranger_summary: str = ""


_previous_extract: Any = None
_previous_limit: Any = None
_previous_apply_lengths: Any = None
_previous_resolve: Any = None
_previous_build_plan: Any = None
_previous_evaluate: Any = None

_metadata_context: contextvars.ContextVar[dict[int, SourceMeta] | None] = contextvars.ContextVar(
    "bpsr_adaptive_metadata", default=None
)
_analysis_context: contextvars.ContextVar[SourceAnalysis | None] = contextvars.ContextVar(
    "bpsr_adaptive_analysis", default=None
)
_metrics_context: contextvars.ContextVar[dict[str, int] | None] = contextvars.ContextVar(
    "bpsr_adaptive_metrics", default=None
)
_options_context: contextvars.ContextVar[AdaptivePlanOptions | None] = contextvars.ContextVar(
    "bpsr_adaptive_options", default=None
)


def _coerce_adaptive_options(options: Any | None) -> AdaptivePlanOptions:
    if options is None:
        return AdaptivePlanOptions()
    if isinstance(options, AdaptivePlanOptions):
        return options
    values: dict[str, Any] = {}
    for name in AdaptivePlanOptions.__dataclass_fields__:
        if hasattr(options, name):
            values[name] = getattr(options, name)
    return AdaptivePlanOptions(**values)


def _role_from_source(track_name: str, channel: int, program: int) -> Role:
    if channel == 9:
        return "drums"
    name = track_name.casefold()
    if any(word in name for word in ("melody", "lead", "vocal", "voice", "solo", "soprano", "theme")):
        return "melody"
    if "bass" in name or any(word in name for word in ("contrabass", "low end", "bassline")):
        return "bass"
    if any(word in name for word in ("chord", "harmony", "pad", "accomp", "rhythm", "strings")):
        return "harmony"
    if 32 <= program <= 39:
        return "bass"
    if 64 <= program <= 87:
        return "melody"
    return "unknown"


def _tempo_events(mid: mido.MidiFile) -> list[tuple[int, int]]:
    events: list[tuple[int, int]] = [(0, 500_000)]
    for track in mid.tracks:
        tick = 0
        for message in track:
            tick += int(message.time)
            if message.type == "set_tempo":
                events.append((tick, int(message.tempo)))
    events.sort(key=lambda item: item[0])
    collapsed: list[tuple[int, int]] = []
    for tick, tempo in events:
        if collapsed and collapsed[-1][0] == tick:
            collapsed[-1] = (tick, tempo)
        else:
            collapsed.append((tick, tempo))
    return collapsed


def _tick_converter(mid: mido.MidiFile):
    tempo_events = _tempo_events(mid)
    segments: list[tuple[int, float, int]] = []
    seconds = 0.0
    previous_tick = tempo_events[0][0]
    tempo = tempo_events[0][1]
    segments.append((previous_tick, seconds, tempo))
    for tick, new_tempo in tempo_events[1:]:
        if tick > previous_tick:
            seconds += mido.tick2second(tick - previous_tick, mid.ticks_per_beat, tempo)
        previous_tick = tick
        tempo = new_tempo
        segments.append((tick, seconds, tempo))

    def convert(tick: int) -> float:
        segment = segments[0]
        for candidate in segments:
            if candidate[0] > tick:
                break
            segment = candidate
        base_tick, base_seconds, base_tempo = segment
        return base_seconds + mido.tick2second(tick - base_tick, mid.ticks_per_beat, base_tempo)

    return convert


@dataclass(frozen=True, slots=True)
class _CandidateMeta:
    start: float
    pitch: int
    velocity: int
    track_index: int
    track_name: str
    channel: int
    program: int
    role: Role


def _collect_candidates(path: Path) -> list[_CandidateMeta]:
    mid = mido.MidiFile(path)
    tick_to_seconds = _tick_converter(mid)
    result: list[_CandidateMeta] = []
    for track_index, track in enumerate(mid.tracks):
        absolute_tick = 0
        track_name = f"Track {track_index + 1}"
        programs: dict[int, int] = defaultdict(int)
        for message in track:
            absolute_tick += int(message.time)
            if message.type == "track_name":
                track_name = str(message.name).strip() or track_name
            elif message.type == "program_change":
                programs[int(message.channel)] = int(message.program)
            elif message.type == "note_on" and int(message.velocity) > 0:
                channel = int(getattr(message, "channel", 0))
                program = programs[channel]
                result.append(
                    _CandidateMeta(
                        start=tick_to_seconds(absolute_tick),
                        pitch=int(message.note),
                        velocity=int(message.velocity),
                        track_index=track_index,
                        track_name=track_name,
                        channel=channel,
                        program=program,
                        role=_role_from_source(track_name, channel, program),
                    )
                )
    result.sort(key=lambda item: (item.start, item.track_index, item.pitch))
    return result


def _match_metadata(notes: list[me.SourceNote], candidates: list[_CandidateMeta]) -> dict[int, SourceMeta]:
    by_pitch: dict[int, list[_CandidateMeta]] = defaultdict(list)
    for candidate in candidates:
        by_pitch[candidate.pitch].append(candidate)
    used: set[tuple[int, int]] = set()
    metadata: dict[int, SourceMeta] = {}
    for note in notes:
        best_index = -1
        best_score = float("inf")
        choices = by_pitch.get(note.pitch, [])
        for index, candidate in enumerate(choices):
            marker = (note.pitch, index)
            if marker in used:
                continue
            delta = abs(candidate.start - note.start)
            if delta > 0.030:
                continue
            score = delta * 1000.0 + abs(candidate.velocity - note.velocity) * 0.05
            if score < best_score:
                best_score = score
                best_index = index
        if best_index >= 0:
            candidate = choices[best_index]
            used.add((note.pitch, best_index))
            metadata[note.serial] = SourceMeta(
                serial=note.serial,
                source_start=note.start,
                pitch=note.pitch,
                velocity=note.velocity,
                track_index=candidate.track_index,
                track_name=candidate.track_name,
                channel=candidate.channel,
                program=candidate.program,
                role=candidate.role,
            )
        else:
            metadata[note.serial] = SourceMeta(
                serial=note.serial,
                source_start=note.start,
                pitch=note.pitch,
                velocity=note.velocity,
                track_index=-1,
                track_name="Unknown",
                channel=-1,
                program=-1,
                role="unknown",
            )
    return metadata


def _window_peak(starts: list[float], window: float) -> float:
    if not starts:
        return 0.0
    left = 0
    best = 0
    for right, value in enumerate(starts):
        while value - starts[left] > window:
            left += 1
        best = max(best, right - left + 1)
    return best / window


def _window_rates(starts: list[float], window: float) -> list[float]:
    if not starts:
        return []
    rates: list[float] = []
    left = 0
    for right, value in enumerate(starts):
        while value - starts[left] > window:
            left += 1
        rates.append((right - left + 1) / window)
    return rates


def _analyse_notes(notes: list[me.SourceNote], metadata: dict[int, SourceMeta]) -> SourceAnalysis:
    if not notes:
        return SourceAnalysis()
    starts = sorted(note.start for note in notes)
    duration = max(note.end for note in notes) - min(note.start for note in notes)
    groups = me._group_notes_by_onset_window(notes)
    max_chord = max((len(group) for group in groups), default=0)
    rates = sorted(_window_rates(starts, 0.5))
    p95 = rates[max(0, math.ceil(len(rates) * 0.95) - 1)] if rates else 0.0
    by_pitch: dict[int, list[float]] = defaultdict(list)
    for note in notes:
        by_pitch[note.pitch].append(note.start)
    repeats = fast = 0
    for pitch_starts in by_pitch.values():
        pitch_starts.sort()
        for first, second in zip(pitch_starts, pitch_starts[1:]):
            repeats += 1
            if second - first < 0.110:
                fast += 1
    track_ids = {meta.track_index for meta in metadata.values() if meta.track_index >= 0}
    return SourceAnalysis(
        note_count=len(notes),
        duration=max(0.0, duration),
        max_chord=max_chord,
        peak_100ms_nps=_window_peak(starts, 0.100),
        peak_250ms_nps=_window_peak(starts, 0.250),
        p95_500ms_nps=p95,
        fast_repeat_ratio=(fast / repeats) if repeats else 0.0,
        metadata_tracks=len(track_ids),
    )


def _adaptive_extract_notes_and_pedal(path: Path, ignore_percussion: bool):
    assert _previous_extract is not None
    data = _previous_extract(path, ignore_percussion)
    notes = data[0]
    container = _metadata_context.get()
    if container is not None:
        try:
            candidates = _collect_candidates(Path(path))
            container.update(_match_metadata(notes, candidates))
        except Exception:
            container.update(
                {
                    note.serial: SourceMeta(
                        serial=note.serial,
                        source_start=note.start,
                        pitch=note.pitch,
                        velocity=note.velocity,
                        track_index=-1,
                        track_name="Unknown",
                        channel=-1,
                        program=-1,
                        role="unknown",
                    )
                    for note in notes
                }
            )
        _analysis_context.set(_analyse_notes(notes, container))
    return data


def _infer_root_pitch_class(group: list[me.SourceNote]) -> int:
    pcs = {note.pitch % 12 for note in group}
    bass_pc = min(group, key=lambda note: note.pitch).pitch % 12
    templates = (
        ({0, 4, 7, 10}, 5.0),
        ({0, 3, 7, 10}, 5.0),
        ({0, 4, 7, 11}, 4.8),
        ({0, 3, 7, 11}, 4.5),
        ({0, 4, 7}, 4.0),
        ({0, 3, 7}, 4.0),
        ({0, 2, 7}, 3.5),
        ({0, 5, 7}, 3.5),
    )
    best_pc = bass_pc
    best_score = float("-inf")
    for root in pcs:
        intervals = {(pc - root) % 12 for pc in pcs}
        template_score = max(
            len(intervals & template) * weight - len(template - intervals) * 0.6
            for template, weight in templates
        )
        score = template_score + (1.2 if root == bass_pc else 0.0)
        if score > best_score:
            best_score = score
            best_pc = root
    return best_pc


def _role_bonus(meta: SourceMeta | None, instrument: str) -> float:
    if meta is None:
        return 0.0
    if meta.role == "melody":
        return 16.0 if instrument != "bass" else 2.0
    if meta.role == "bass":
        return 18.0 if instrument == "bass" else 7.0
    if meta.role == "harmony":
        return 2.0
    if meta.role == "drums":
        return -100.0
    return 0.0


def _chord_note_score(
    note: me.SourceNote,
    group: list[me.SourceNote],
    root_pc: int,
    instrument: str,
    metadata: dict[int, SourceMeta],
) -> float:
    low = min(item.pitch for item in group)
    high = max(item.pitch for item in group)
    interval = (note.pitch - root_pc) % 12
    chord_tone = {0: 10.0, 3: 8.0, 4: 8.0, 10: 7.0, 11: 7.0, 7: 6.0, 2: 3.5, 5: 3.5}.get(interval, 1.0)
    score = chord_tone + _role_bonus(metadata.get(note.serial), instrument)
    score += min(4.0, max(0.0, note.end - note.start) * 4.0)
    score += min(3.0, note.velocity / 42.0)
    if instrument == "keyboard":
        if note.pitch == high:
            score += 16.0
        if note.pitch == low:
            score += 10.0
    elif instrument == "guitar":
        if note.pitch == high:
            score += 20.0
        if interval in {0, 3, 4, 7, 10, 11}:
            score += 3.0
        if note.pitch == low:
            score += 3.0
    else:
        score += max(0.0, 18.0 - (note.pitch - low) * 1.3)
        if metadata.get(note.serial) and metadata[note.serial].role == "bass":
            score += 20.0
    return score


def _adaptive_limit_notes_per_chord(
    notes: list[me.SourceNote], maximum: int, instrument: me.InstrumentCode = "keyboard"
) -> tuple[list[me.SourceNote], int]:
    options = _options_context.get()
    analysis = _analysis_context.get()
    metadata = _metadata_context.get() or {}
    requested = int(maximum)
    if options is not None and options.adaptive_auto and options.mapping_method != "skip":
        default_limit = ADAPTIVE_DEFAULTS[instrument].max_polyphony
        if options.adaptive_chord_limit > 0:
            default_limit = options.adaptive_chord_limit
        if analysis is not None and analysis.max_chord > default_limit:
            requested = default_limit if requested <= 0 else min(requested, default_limit)
    if requested <= 0:
        return notes, 0

    kept: list[me.SourceNote] = []
    removed = 0
    for group in me._group_notes_by_onset_window(notes):
        if len(group) <= requested:
            kept.extend(group)
            continue
        root_pc = _infer_root_pitch_class(group)
        ranked = sorted(
            group,
            key=lambda note: (
                _chord_note_score(note, group, root_pc, instrument, metadata),
                note.velocity,
                note.pitch,
                -note.serial,
            ),
            reverse=True,
        )
        selected = {note.serial for note in ranked[:requested]}
        kept.extend(note for note in group if note.serial in selected)
        removed += len(group) - requested
    kept.sort(key=lambda note: (note.start, note.serial))
    return kept, removed


def _register_scale(instrument: str, pitch: int) -> float:
    if instrument == "keyboard":
        if pitch < 48:
            return 0.86
        if pitch >= 72:
            return 1.06
        return 1.0
    if instrument == "guitar":
        return 1.04 if pitch >= 64 else 0.94
    return 1.10 if pitch < 45 else 1.0


def _adaptive_apply_note_lengths(notes: list[me.PlannedNote], options: Any) -> list[me.PlannedNote]:
    adaptive = _coerce_adaptive_options(options)
    if not notes:
        return []
    ordered = sorted(notes, key=lambda note: (note.start, note.serial))
    starts = [note.start for note in ordered]
    densities = [
        (bisect_right(starts, value + 0.250) - bisect_left(starts, value - 0.250)) / 0.5
        for value in starts
    ]
    next_same_key: list[float | None] = [None] * len(ordered)
    upcoming_by_key: dict[str, float] = {}
    for index in range(len(ordered) - 1, -1, -1):
        note = ordered[index]
        next_same_key[index] = upcoming_by_key.get(note.key)
        upcoming_by_key[note.key] = note.start

    result: list[me.PlannedNote] = []
    hard_floor = adaptive.resolved_hard_floor_ms / 1000.0
    release_gap = adaptive.resolved_release_gap_ms / 1000.0
    for index, note in enumerate(ordered):
        source_duration = max(0.001, note.end - note.start)
        base = po._desired_note_duration(source_duration, adaptive)
        density = densities[index]
        target = base * _register_scale(adaptive.instrument, note.pitch)

        following = ordered[index + 1].start if index + 1 < len(ordered) else None
        if following is not None:
            onset_gap = max(0.001, following - note.start)
            gate_ratio = source_duration / onset_gap
            if gate_ratio < 0.45:
                target = min(
                    target,
                    max(hard_floor, source_duration + adaptive.resolved_short_tail_ms / 2000.0),
                )
            elif gate_ratio > 0.92 and note.key != ordered[index + 1].key:
                target = max(target, min(onset_gap + 0.030, base + 0.050))

        if density >= 12.0:
            target *= 0.70
        elif density >= 8.0:
            target *= 0.80
        elif density >= 5.0:
            target *= 0.90

        if following is None or following - note.start > 0.35:
            target += min(0.045, adaptive.resolved_short_tail_ms / 1000.0)

        if next_same_key[index] is not None:
            target = min(
                target,
                max(hard_floor, next_same_key[index] - note.start - release_gap),
            )
        target = max(hard_floor, target)
        result.append(replace(note, end=note.start + target))
    result.sort(key=lambda note: (note.start, note.serial))
    return result


def _importance(note: me.PlannedNote, metadata: dict[int, SourceMeta], instrument: str) -> float:
    meta = metadata.get(note.serial)
    score = _role_bonus(meta, instrument)
    score += note.velocity / 16.0
    score += min(6.0, max(0.0, note.source_end - note.source_start) * 6.0)
    if instrument == "keyboard":
        score += max(0.0, (note.pitch - 60) * 0.18)
    elif instrument == "guitar":
        score += max(0.0, (note.pitch - 55) * 0.24)
    else:
        score += max(0.0, (55 - note.pitch) * 0.20)
    return score


def _adaptive_resolve_retrigger_conflicts(
    notes: list[me.PlannedNote], options: Any
) -> tuple[list[me.PlannedNote], int, int]:
    adaptive = _coerce_adaptive_options(options)
    metadata = _metadata_context.get() or {}
    metrics = _metrics_context.get()
    hard_floor = adaptive.resolved_hard_floor_ms / 1000.0
    release_gap = adaptive.resolved_release_gap_ms / 1000.0
    impossible_cycle = hard_floor + release_gap
    musical_floor = hard_floor if adaptive.articulation_mode == "raw" else adaptive.resolved_minimum_note_ms / 1000.0

    by_key: dict[str, list[me.PlannedNote]] = defaultdict(list)
    for note in notes:
        by_key[note.key].append(note)

    resolved: list[me.PlannedNote] = []
    merged = dropped = compressed = evictions = 0
    for key_notes in by_key.values():
        kept: list[me.PlannedNote] = []
        for current in sorted(key_notes, key=lambda item: (item.start, item.serial)):
            if not kept:
                kept.append(current)
                continue
            previous = kept[-1]
            onset_interval = current.start - previous.start
            if onset_interval + 1e-9 < impossible_cycle:
                same_attack = (
                    current.pitch == previous.pitch
                    and current.page == previous.page
                    and current.octave == previous.octave
                )
                if same_attack:
                    kept[-1] = replace(
                        previous,
                        source_end=max(previous.source_end, current.source_end),
                        end=max(previous.end, current.end),
                        velocity=max(previous.velocity, current.velocity),
                    )
                    merged += 1
                    continue
                previous_score = _importance(previous, metadata, adaptive.instrument)
                current_score = _importance(current, metadata, adaptive.instrument)
                if current_score > previous_score + 2.5:
                    kept[-1] = current
                    evictions += 1
                    dropped += 1
                else:
                    dropped += 1
                continue

            latest_end = current.start - release_gap
            if previous.end > latest_end:
                new_end = max(previous.start + hard_floor, latest_end)
                if new_end + 1e-9 < previous.start + musical_floor:
                    compressed += 1
                kept[-1] = replace(previous, end=new_end)
            kept.append(current)
        resolved.extend(kept)

    if metrics is not None:
        metrics["priority_evictions"] = metrics.get("priority_evictions", 0) + evictions
        metrics["retrigger_compressed_notes"] = compressed
    po_metrics = po._context_metrics.get()
    if po_metrics is not None:
        po_metrics["retrigger_compressed_notes"] = compressed
    resolved.sort(key=lambda item: (item.start, item.serial))
    return resolved, merged, dropped


def _is_probable_arpeggio(group: list[me.PlannedEvent], metadata: dict[int, SourceMeta]) -> bool:
    if len(group) < 3:
        return False
    span = group[-1].time - group[0].time
    if span <= 0.004:
        return False
    pitches = [metadata[event.serial].pitch for event in group if event.serial in metadata]
    if len(pitches) < 3:
        return False
    ascending = all(first < second for first, second in zip(pitches, pitches[1:]))
    descending = all(first > second for first, second in zip(pitches, pitches[1:]))
    return (ascending or descending) and span >= 0.007


def _normalize_chord_attacks(
    plan: po.EnhancedMidiPlan,
    options: AdaptivePlanOptions,
    metadata: dict[int, SourceMeta],
) -> tuple[list[me.PlannedEvent], int, int]:
    note_ons = sorted(
        (event for event in plan.events if event.kind == "note_on" and event.key),
        key=lambda event: (event.time, event.serial),
    )
    if len(note_ons) < 2:
        return list(plan.events), 0, 0

    window = max(0.005, options.attack_cluster_ms / 1000.0)
    groups: list[list[me.PlannedEvent]] = []
    anchor: float | None = None
    for event in note_ons:
        if anchor is None or event.time - anchor > window:
            groups.append([])
            anchor = event.time
        groups[-1].append(event)

    stagger_ms = options.chord_stagger_ms
    if stagger_ms < 0:
        stagger_ms = ADAPTIVE_DEFAULTS[options.instrument].chord_stagger_ms
    stagger = stagger_ms / 1000.0
    delta_by_serial: dict[int, float] = {}
    normalized = 0
    for group in groups:
        if len(group) < 2 or _is_probable_arpeggio(group, metadata):
            continue
        base = min(event.time for event in group)
        ordered = sorted(
            group,
            key=lambda event: (
                metadata.get(event.serial).pitch if metadata.get(event.serial) else 60,
                event.serial,
            ),
        )
        if options.instrument == "guitar":
            placement = ordered
        else:
            placement = sorted(group, key=lambda event: event.serial)
        for index, event in enumerate(placement):
            target = base + index * stagger
            delta_by_serial[event.serial] = target - event.time
        normalized += 1

    if not delta_by_serial:
        return list(plan.events), 0, stagger_ms

    adjusted: list[me.PlannedEvent] = []
    for event in plan.events:
        delta = delta_by_serial.get(event.serial)
        if delta is not None and event.kind in {"note_on", "note_off"}:
            adjusted.append(replace(event, time=max(0.0, event.time + delta)))
        else:
            adjusted.append(event)
    adjusted.sort(key=lambda event: (event.time, event.priority, event.serial))
    return adjusted, normalized, stagger_ms


def _auto_tune_options(
    options: AdaptivePlanOptions,
    analysis: SourceAnalysis,
    calibration: CalibrationProfile,
) -> AdaptivePlanOptions:
    if not options.adaptive_auto or options.mapping_method == "skip":
        return options
    tuned = replace(
        options,
        minimum_note_ms=calibration.minimum_clean_hold_ms,
        hard_press_floor_ms=calibration.hard_floor_ms,
        repeated_release_gap_ms=calibration.retrigger_gap_ms,
        adaptive_chord_limit=options.adaptive_chord_limit or calibration.max_polyphony,
        chord_stagger_ms=calibration.chord_stagger_ms if options.chord_stagger_ms < 0 else options.chord_stagger_ms,
        octave_switch_lead_ms=max(options.octave_switch_lead_ms, calibration.modifier_settle_ms),
    )
    default_limit = tuned.adaptive_chord_limit or ADAPTIVE_DEFAULTS[options.instrument].max_polyphony
    if tuned.max_notes_per_chord <= 0 and analysis.max_chord > default_limit:
        tuned.max_notes_per_chord = default_limit
    if analysis.peak_250ms_nps >= 12.0 or analysis.fast_repeat_ratio >= 0.20:
        tuned.articulation_mode = "dense"
    elif analysis.peak_250ms_nps >= 8.0 and tuned.articulation_mode == "musical":
        tuned.articulation_mode = "balanced"
    return tuned


def _preanalyse(path: Path) -> SourceAnalysis:
    try:
        candidates = _collect_candidates(path)
        if not candidates:
            return SourceAnalysis()
        filtered = [item for item in candidates if item.channel != 9]
        pseudo = [
            me.SourceNote(
                start=item.start,
                end=item.start + 0.100,
                pitch=item.pitch,
                velocity=item.velocity,
                serial=index,
            )
            for index, item in enumerate(filtered)
        ]
        metadata = {
            note.serial: SourceMeta(
                serial=note.serial,
                source_start=note.start,
                pitch=note.pitch,
                velocity=note.velocity,
                track_index=candidate.track_index,
                track_name=candidate.track_name,
                channel=candidate.channel,
                program=candidate.program,
                role=candidate.role,
            )
            for note, candidate in zip(pseudo, filtered)
        }
        return _analyse_notes(pseudo, metadata)
    except Exception:
        return SourceAnalysis()


def _to_adaptive_plan(
    plan: po.EnhancedMidiPlan,
    *,
    analysis: SourceAnalysis,
    metadata: dict[int, SourceMeta],
    metrics: dict[str, int],
    normalized: int,
    auto_limit: int,
    stagger_ms: int,
    calibration: CalibrationProfile,
) -> AdaptiveMidiPlan:
    values = {field.name: getattr(plan, field.name) for field in fields(po.EnhancedMidiPlan)}
    roles = defaultdict(int)
    for meta in metadata.values():
        roles[meta.role] += 1
    summary_bits = [
        f"peak {analysis.peak_250ms_nps:.1f} notes/s",
        f"p95 {analysis.p95_500ms_nps:.1f}/s",
    ]
    if normalized:
        summary_bits.append(f"{normalized} chord attack(s) normalized")
    if metrics.get("priority_evictions", 0):
        summary_bits.append(f"{metrics['priority_evictions']} melody-priority collision(s)")
    if auto_limit:
        summary_bits.append(f"auto chord cap {auto_limit}")
    return AdaptiveMidiPlan(
        **values,
        adaptive_enabled=True,
        normalized_chords=normalized,
        priority_evictions=metrics.get("priority_evictions", 0),
        local_peak_nps=analysis.peak_250ms_nps,
        p95_window_nps=analysis.p95_500ms_nps,
        fast_repeat_ratio=analysis.fast_repeat_ratio,
        metadata_tracks=analysis.metadata_tracks,
        melody_role_notes=roles["melody"],
        bass_role_notes=roles["bass"],
        harmony_role_notes=roles["harmony"],
        auto_chord_limit=auto_limit,
        chord_stagger_ms=stagger_ms,
        calibration_source="calibrated" if calibration.calibrated else "defaults",
        arranger_summary=" • ".join(summary_bits),
    )


def adaptive_build_plan(path: str | Path, options: Any | None = None) -> AdaptiveMidiPlan:
    assert _previous_build_plan is not None
    midi_path = Path(path)
    requested = _coerce_adaptive_options(options)
    preanalysis = _preanalyse(midi_path)
    calibration = get_calibration_profile(requested.instrument)
    effective = _auto_tune_options(requested, preanalysis, calibration)
    metadata: dict[int, SourceMeta] = {}
    metrics = {"priority_evictions": 0, "retrigger_compressed_notes": 0}
    token_meta = _metadata_context.set(metadata)
    token_analysis = _analysis_context.set(preanalysis)
    token_metrics = _metrics_context.set(metrics)
    token_options = _options_context.set(effective)
    try:
        plan = _previous_build_plan(midi_path, effective)
        analysis = _analysis_context.get() or preanalysis
        normalized_events, normalized, stagger_ms = _normalize_chord_attacks(plan, effective, metadata)
        plan.events = normalized_events
        plan.duration = max((event.time for event in normalized_events), default=plan.duration)
        auto_limit = effective.max_notes_per_chord if requested.max_notes_per_chord <= 0 else 0
        return _to_adaptive_plan(
            plan,
            analysis=analysis,
            metadata=metadata,
            metrics=metrics,
            normalized=normalized,
            auto_limit=auto_limit,
            stagger_ms=stagger_ms,
            calibration=calibration,
        )
    finally:
        _metadata_context.reset(token_meta)
        _analysis_context.reset(token_analysis)
        _metrics_context.reset(token_metrics)
        _options_context.reset(token_options)


def adaptive_evaluate_song_suitability(plan: Any):
    assert _previous_evaluate is not None
    base = _previous_evaluate(plan)
    score = int(base.score)
    reasons = list(base.reasons)
    peak = float(getattr(plan, "local_peak_nps", 0.0))
    p95 = float(getattr(plan, "p95_window_nps", 0.0))
    evictions = int(getattr(plan, "priority_evictions", 0))
    if peak >= 16.0:
        score += 2
        reasons.append(f"short burst reaches {peak:.1f} notes/sec")
    elif peak >= 10.0:
        score += 1
        reasons.append(f"short burst reaches {peak:.1f} notes/sec")
    if p95 >= 10.0:
        score += 1
        reasons.append(f"95th-percentile local density is {p95:.1f} notes/sec")
    if evictions:
        score += 1
        reasons.append(f"{evictions} impossible physical-key collision(s) resolved by note importance")
    if score >= 7:
        code, label = "complex", "Very complex"
        summary = "Adaptive arranger can simplify it, but the busiest passages may still exceed BPSR input limits."
    elif score >= 3:
        code, label = "busy", "Busy"
        summary = "Adaptive arranger will thin/reshape the busiest passages while protecting melody and bass roles."
    else:
        code, label = "good", "Good fit"
        summary = "Adaptive arranger should translate this cleanly with the selected BPSR instrument."
    return suitability_module.SuitabilityResult(
        code=code,
        label=label,
        summary=summary,
        score=score,
        notes_per_second=base.notes_per_second,
        changed_ratio=base.changed_ratio,
        reasons=tuple(reasons),
    )


def _patch_app_options(app_module: Any) -> None:
    app_class = app_module.App
    if getattr(app_class, "_adaptive_arranger_options_installed", False):
        return
    original_plan_options = app_class._plan_options
    original_analyze = app_class._analyze

    def plan_options(self: Any) -> AdaptivePlanOptions:
        base = original_plan_options(self)
        values = {
            name: getattr(base, name)
            for name in po.EnhancedPlanOptions.__dataclass_fields__
            if hasattr(base, name)
        }
        profile = self._profile_code()
        return AdaptivePlanOptions(
            **values,
            adaptive_auto=profile not in {"custom", "raw"},
            adaptive_chord_limit=0,
            chord_stagger_ms=-1,
        )

    def analyze(self: Any) -> None:
        original_analyze(self)
        plan = getattr(self, "current_plan", None)
        if plan is None or not getattr(plan, "adaptive_enabled", False):
            return
        base = str(self.analysis_var.get())
        marker = "\nAdaptive arranger • "
        base = base.split(marker, 1)[0]
        detail = str(getattr(plan, "arranger_summary", "")).strip()
        roles = []
        if getattr(plan, "melody_role_notes", 0):
            roles.append(f"melody {plan.melody_role_notes}")
        if getattr(plan, "bass_role_notes", 0):
            roles.append(f"bass {plan.bass_role_notes}")
        if getattr(plan, "metadata_tracks", 0):
            roles.append(f"{plan.metadata_tracks} source track(s)")
        role_text = f" • roles: {', '.join(roles)}" if roles else ""
        self.analysis_var.set(f"{base}{marker}{detail}{role_text}")

    app_class._plan_options = plan_options
    app_class._analyze = analyze
    app_class._adaptive_arranger_options_installed = True


def install_adaptive_arranger(app_module: Any) -> None:
    global _previous_extract, _previous_limit, _previous_apply_lengths
    global _previous_resolve, _previous_build_plan, _previous_evaluate
    if getattr(app_module, "_adaptive_arranger_installed", False):
        return

    _previous_extract = me._extract_notes_and_pedal
    _previous_limit = me._limit_notes_per_chord
    _previous_apply_lengths = me._apply_note_lengths
    _previous_resolve = me._resolve_retrigger_conflicts
    _previous_build_plan = me.build_plan
    _previous_evaluate = suitability_module.evaluate_song_suitability

    me.PlanOptions = AdaptivePlanOptions
    me.MidiPlan = AdaptiveMidiPlan
    me._extract_notes_and_pedal = _adaptive_extract_notes_and_pedal
    me._limit_notes_per_chord = _adaptive_limit_notes_per_chord
    me._apply_note_lengths = _adaptive_apply_note_lengths
    me._resolve_retrigger_conflicts = _adaptive_resolve_retrigger_conflicts
    me.build_plan = adaptive_build_plan

    suitability_module.evaluate_song_suitability = adaptive_evaluate_song_suitability
    app_module.PlanOptions = AdaptivePlanOptions
    app_module.build_plan = adaptive_build_plan
    app_module.evaluate_song_suitability = adaptive_evaluate_song_suitability
    for name in ("online_ui", "online_integration", "online_search_bridge"):
        import sys
        module = sys.modules.get(name)
        if module is None:
            continue
        if hasattr(module, "build_plan"):
            module.build_plan = adaptive_build_plan
        if hasattr(module, "evaluate_song_suitability"):
            module.evaluate_song_suitability = adaptive_evaluate_song_suitability

    _patch_app_options(app_module)
    app_module._adaptive_arranger_installed = True
