from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from statistics import median
from typing import Any

import midi_engine as me
import playback_adaptive as adaptive
import playback_overhaul as po

_original_collect_candidates: Any = None
_original_voice_continuity: Any = None


def _name_role(track_name: str) -> adaptive.Role | None:
    name = track_name.casefold()
    if any(word in name for word in ("melody", "lead", "vocal", "voice", "solo", "soprano", "theme")):
        return "melody"
    if any(word in name for word in ("bass", "contrabass", "bassline", "low end")):
        return "bass"
    if any(word in name for word in ("chord", "harmony", "pad", "accomp", "rhythm", "strings")):
        return "harmony"
    return None


def _refined_role_from_source(track_name: str, channel: int, program: int) -> adaptive.Role:
    if channel == 9:
        return "drums"
    named = _name_role(track_name)
    if named is not None:
        return named
    if 32 <= program <= 39:
        return "bass"
    # GM programs 80-87 are synth leads. Reed/pipe programs 64-79 are not
    # automatically melody: they are often harmony parts in orchestral MIDIs.
    if 80 <= program <= 87:
        return "melody"
    return "unknown"


def _refine_candidate_roles(
    candidates: list[adaptive._CandidateMeta],
) -> list[adaptive._CandidateMeta]:
    by_stream: dict[tuple[int, int], list[adaptive._CandidateMeta]] = defaultdict(list)
    for candidate in candidates:
        by_stream[(candidate.track_index, candidate.channel)].append(candidate)

    role_by_stream: dict[tuple[int, int], adaptive.Role] = {}
    for stream, notes in by_stream.items():
        explicit = next((_name_role(note.track_name) for note in notes if _name_role(note.track_name)), None)
        if explicit is not None:
            role_by_stream[stream] = explicit
            continue
        if notes and 32 <= notes[0].program <= 39:
            role_by_stream[stream] = "bass"
            continue

        pitches = [note.pitch for note in notes]
        starts = sorted(note.start for note in notes)
        clustered_notes = 0
        index = 0
        while index < len(starts):
            anchor = starts[index]
            end = index + 1
            while end < len(starts) and starts[end] - anchor <= 0.015:
                end += 1
            if end - index > 1:
                clustered_notes += end - index
            index = end
        chord_ratio = clustered_notes / max(1, len(notes))
        middle = float(median(pitches)) if pitches else 60.0

        if chord_ratio >= 0.28:
            role_by_stream[stream] = "harmony"
        elif middle <= 48 and len(notes) >= 4:
            role_by_stream[stream] = "bass"
        elif middle >= 60 and chord_ratio <= 0.12 and len(notes) >= 4:
            role_by_stream[stream] = "melody"
        elif notes and 80 <= notes[0].program <= 87:
            role_by_stream[stream] = "melody"
        else:
            role_by_stream[stream] = "unknown"

    return [
        replace(candidate, role=role_by_stream[(candidate.track_index, candidate.channel)])
        for candidate in candidates
    ]


def _refined_collect_candidates(path: Any) -> list[adaptive._CandidateMeta]:
    assert _original_collect_candidates is not None
    return _refine_candidate_roles(_original_collect_candidates(path))


def _mapped_pitch_for_note(
    group: list[me.SourceNote],
    mapped: me._MappedGroup,
    note: me.SourceNote,
) -> int | None:
    for source, pitch in zip(group, mapped.pitches):
        if source.serial == note.serial:
            return pitch
    return None


def _best_role_note(
    group: list[me.SourceNote],
    metadata: dict[int, adaptive.SourceMeta],
    role: str,
) -> me.SourceNote | None:
    candidates = [note for note in group if metadata.get(note.serial) and metadata[note.serial].role == role]
    if not candidates:
        return None
    if role == "bass":
        return min(candidates, key=lambda note: (note.pitch, -note.velocity, note.serial))
    return max(candidates, key=lambda note: (note.velocity, note.pitch, note.end - note.start, -note.serial))


def _role_continuity_penalty(
    previous_group: list[me.SourceNote],
    previous_mapped: me._MappedGroup,
    current_group: list[me.SourceNote],
    current_mapped: me._MappedGroup,
    instrument: me.InstrumentCode,
) -> float:
    metadata = adaptive._metadata_context.get() or {}
    total = 0.0
    for role, weight in (("melody", 5.0), ("bass", 3.5 if instrument != "bass" else 6.0)):
        previous_note = _best_role_note(previous_group, metadata, role)
        current_note = _best_role_note(current_group, metadata, role)
        if previous_note is None or current_note is None:
            continue
        previous_pitch = _mapped_pitch_for_note(previous_group, previous_mapped, previous_note)
        current_pitch = _mapped_pitch_for_note(current_group, current_mapped, current_note)
        if previous_pitch is None or current_pitch is None:
            continue
        source_interval = current_note.pitch - previous_note.pitch
        mapped_interval = current_pitch - previous_pitch
        total += abs(mapped_interval - source_interval) * weight
        if source_interval and mapped_interval and source_interval * mapped_interval < 0:
            total += 30.0 * weight
        total += max(0, abs(mapped_interval) - 12) * 2.5 * weight
        if role == "melody" and current_pitch != current_note.pitch:
            total += abs(current_pitch - current_note.pitch) * 0.8 * weight
    return total


def _refined_voice_continuity_cost(
    previous_group: list[me.SourceNote],
    previous_mapped: me._MappedGroup,
    current_group: list[me.SourceNote],
    current_mapped: me._MappedGroup,
    instrument: me.InstrumentCode,
) -> float:
    assert _original_voice_continuity is not None
    return _original_voice_continuity(
        previous_group,
        previous_mapped,
        current_group,
        current_mapped,
        instrument,
    ) + _role_continuity_penalty(
        previous_group,
        previous_mapped,
        current_group,
        current_mapped,
        instrument,
    )


def _refined_normalize_chord_attacks(
    plan: po.EnhancedMidiPlan,
    options: adaptive.AdaptivePlanOptions,
    metadata: dict[int, adaptive.SourceMeta],
) -> tuple[list[me.PlannedEvent], int, int]:
    # Custom and Raw are explicitly manual modes. They still use physical-key
    # safety/retrigger handling, but the arranger must not rewrite authored
    # attack placement unless Adaptive Auto is enabled.
    if not options.adaptive_auto:
        return list(plan.events), 0, max(0, options.chord_stagger_ms)

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
        stagger_ms = adaptive.ADAPTIVE_DEFAULTS[options.instrument].chord_stagger_ms
    stagger = stagger_ms / 1000.0
    delta_by_serial: dict[int, float] = {}
    normalized = 0

    for group in groups:
        if len(group) < 2:
            continue
        span = group[-1].time - group[0].time
        # Dyads are ambiguous. Only snap extremely tight two-note attacks; a
        # 7-15 ms dyad may intentionally be a grace note, guitar strum, or roll.
        if len(group) == 2 and span > 0.006:
            continue
        if adaptive._is_probable_arpeggio(group, metadata):
            continue

        base = min(event.time for event in group)
        if options.instrument == "guitar":
            placement = sorted(
                group,
                key=lambda event: (
                    metadata[event.serial].pitch if event.serial in metadata else 60,
                    event.serial,
                ),
            )
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


def install_arranger_refinements(app_module: Any) -> None:
    global _original_collect_candidates, _original_voice_continuity
    if getattr(app_module, "_arranger_refinements_installed", False):
        return
    _original_collect_candidates = adaptive._collect_candidates
    _original_voice_continuity = po._voice_continuity_cost

    adaptive._role_from_source = _refined_role_from_source
    adaptive._collect_candidates = _refined_collect_candidates
    adaptive._normalize_chord_attacks = _refined_normalize_chord_attacks
    po._voice_continuity_cost = _refined_voice_continuity_cost
    app_module._arranger_refinements_installed = True
