"""Reject rhythmically orphaned piano/guitar re-attacks with no local audio onset.

The pitch guard intentionally protects independently corroborated and repeated-motif
notes. The final spectral guard then asks whether the pitch exists in the source
audio. A decoder can still create a bad MIDI re-trigger on top of a sustained
harmonic: the pitch is genuinely present, but there was no new note attack at that
time. This precision-only pass targets that narrow failure mode.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from contextlib import ExitStack
from dataclasses import replace
import math
from pathlib import Path
from typing import Any

from .audio_note_guard import _pitch_evidence, _spectrum
from .music import MasterSong, MusicEvent

_TARGETS = {"piano", "guitar"}


def _raw_confidence(event: MusicEvent) -> float:
    value = event.original_confidence
    return float(event.confidence if value is None else value)


def _strong_support(event: MusicEvent) -> bool:
    if event.tags & {"independent_agreement", "targeted_repair"}:
        return True
    return any(event.evidence.get(key) for key in ("beta9_support_engines", "agreement_engines"))


def _onset_groups(events: list[MusicEvent], tolerance: float = .045) -> list[list[MusicEvent]]:
    groups: list[list[MusicEvent]] = []
    for event in sorted(events, key=lambda item: (item.start, item.pitch or -1)):
        if not groups or event.start - groups[-1][0].start > tolerance:
            groups.append([])
        groups[-1].append(event)
    return groups


def _group_anchor(group: list[MusicEvent]) -> bool:
    return (
        len(group) >= 2
        or any(_strong_support(event) for event in group)
        or max((event.confidence for event in group), default=0.0) >= .70
    )


def _neighbor_anchor(groups: list[list[MusicEvent]], index: int, direction: int):
    stop = max(-1, index - 4) if direction < 0 else min(len(groups), index + 4)
    for candidate in range(index + direction, stop, direction):
        if 0 <= candidate < len(groups) and _group_anchor(groups[candidate]):
            return groups[candidate]
    return None


def _beat_grid_context(beat_map, timestamp: float):
    """Return loose sixteenth-grid context without moving the MIDI event."""
    if beat_map is None or getattr(beat_map, "confidence", 0.0) < .60:
        return None
    beats = list(getattr(beat_map, "beats", ()) or ())
    if len(beats) < 2:
        return None

    index = bisect_right(beats, timestamp) - 1
    candidates = []
    for left_index in range(max(0, index - 1), min(len(beats) - 1, index + 2)):
        left = beats[left_index]
        right = beats[left_index + 1]
        interval = right - left
        if interval <= .12 or interval > 2.5:
            continue
        step = interval / 4.0
        nearest = left + round((timestamp - left) / step) * step
        candidates.append((abs(timestamp - nearest), interval, nearest))

    if not candidates:
        if timestamp < beats[0]:
            interval, anchor = beats[1] - beats[0], beats[0]
        else:
            interval, anchor = beats[-1] - beats[-2], beats[-1]
        if .12 < interval <= 2.5:
            step = interval / 4.0
            nearest = anchor + round((timestamp - anchor) / step) * step
            candidates.append((abs(timestamp - nearest), interval, nearest))

    if not candidates:
        return None
    distance, interval, nearest = min(candidates, key=lambda item: item[0])
    tolerance = max(.042, min(.078, interval * .11))
    return {
        "distance": distance,
        "interval": interval,
        "nearest": nearest,
        "tolerance": tolerance,
        "off_grid": distance > tolerance,
    }


def _rhythm_orphan_context(groups: list[list[MusicEvent]], index: int, beat_map):
    group = groups[index]
    if len(group) != 1:
        return None
    event = group[0]
    grid = _beat_grid_context(beat_map, event.start)
    if not grid or not grid["off_grid"]:
        return None

    previous = _neighbor_anchor(groups, index, -1)
    following = _neighbor_anchor(groups, index, 1)
    if previous is None or following is None:
        return None
    previous_grid = _beat_grid_context(beat_map, previous[0].start)
    following_grid = _beat_grid_context(beat_map, following[0].start)
    if not previous_grid or not following_grid:
        return None
    if previous_grid["off_grid"] or following_grid["off_grid"]:
        # Preserve phrases that are consistently played ahead/behind the grid.
        return None

    max_context = max(1.0, grid["interval"] * 2.5)
    if event.start - previous[0].start > max_context:
        return None
    if following[0].start - event.start > max_context:
        return None

    return {
        "distance": round(float(grid["distance"]), 6),
        "tolerance": round(float(grid["tolerance"]), 6),
        "nearest": round(float(grid["nearest"]), 6),
        "beat_interval": round(float(grid["interval"]), 6),
        "previous_onset": round(float(previous[0].start), 6),
        "next_onset": round(float(following[0].start), 6),
    }


def _read_interval(handle, start: float, end: float):
    import numpy as np

    sr = int(handle.samplerate)
    start_frame = max(0, int(start * sr))
    end_frame = max(start_frame + 1, int(end * sr))
    start_frame = min(start_frame, max(0, len(handle) - 1))
    handle.seek(start_frame)
    audio = handle.read(max(1, end_frame - start_frame), dtype="float32", always_2d=True)
    if not len(audio):
        return np.zeros(256, dtype="float32"), sr
    return np.asarray(audio, dtype="float32").mean(axis=1), sr


def _pitch_window(handle, pitch: int, start: float, end: float) -> dict[str, float]:
    samples, sample_rate = _read_interval(handle, start, end)
    power, frequencies, rms, _ = _spectrum(samples, sample_rate)
    evidence = _pitch_evidence(power, frequencies, pitch)
    return {
        "signal": float(evidence["signal"]),
        "snr_db": float(evidence["snr_db"]),
        "rms": float(rms),
    }


def _attack_evidence(handle, pitch: int, onset: float) -> dict[str, float]:
    # Equal 90 ms windows make a sustained tone measure near 0 dB. The 25 ms
    # gap before onset also avoids separator smearing hiding a real re-attack.
    pre = _pitch_window(handle, pitch, max(0.0, onset - .115), max(.001, onset - .025))
    post = _pitch_window(handle, pitch, onset, onset + .090)
    pitch_attack_db = 10.0 * math.log10((post["signal"] + 1e-18) / (pre["signal"] + 1e-18))
    rms_attack_db = 20.0 * math.log10((post["rms"] + 1e-12) / (pre["rms"] + 1e-12))
    return {
        "pre_pitch_snr_db": round(pre["snr_db"], 3),
        "post_pitch_snr_db": round(post["snr_db"], 3),
        "pitch_attack_db": round(max(-60.0, min(60.0, pitch_attack_db)), 3),
        "rms_attack_db": round(max(-60.0, min(60.0, rms_attack_db)), 3),
    }


def _annotate(event: MusicEvent, evidence: dict[str, Any], tag: str) -> MusicEvent:
    return replace(
        event,
        tags=event.tags | {tag},
        evidence={**event.evidence, "rhythm_attack_validation": evidence},
    )


def validate_rhythm_attacks(master: MasterSong, stems: dict[str, Path], mixture: Path) -> MasterSong:
    """Remove only off-grid singleton re-triggers that have no local pitch attack."""
    import soundfile as sf

    targets = [
        event for event in master.events
        if event.source in _TARGETS and event.pitch is not None
    ]
    if not targets:
        master.provenance["rhythm_attack_guard"] = {
            "version": 1, "considered": 0, "checked": 0, "removed": 0,
        }
        return master

    mixture = Path(mixture)
    source_paths = {source: Path(stems[source]) for source in _TARGETS if source in stems}
    needed_sources = {event.source for event in targets}
    if not mixture.is_file() or any(source not in source_paths or not source_paths[source].is_file()
                                    for source in needed_sources):
        raise OSError("Target stem or prepared mixture is missing for rhythm attack validation")

    replacements: dict[int, MusicEvent | None] = {}
    rejected: list[dict[str, Any]] = []
    checked = 0
    candidates = 0

    by_source = {
        source: [event for event in targets if event.source == source]
        for source in needed_sources
    }

    with ExitStack() as stack:
        source_handles = {
            source: stack.enter_context(sf.SoundFile(str(source_paths[source]), "r"))
            for source in needed_sources
        }
        mixture_handle = stack.enter_context(sf.SoundFile(str(mixture), "r"))

        for source, source_events in by_source.items():
            groups = _onset_groups(source_events)
            for index, group in enumerate(groups):
                context = _rhythm_orphan_context(groups, index, master.beat_map)
                if context is None:
                    continue
                candidates += 1
                event = group[0]
                checked += 1

                source_attack = _attack_evidence(source_handles[source], int(event.pitch), event.start)
                mixture_attack = _attack_evidence(mixture_handle, int(event.pitch), event.start)
                evidence = {
                    "source": source,
                    "pitch": int(event.pitch),
                    "rhythm": context,
                    "source_attack": source_attack,
                    "mixture_attack": mixture_attack,
                    "strong_support": _strong_support(event),
                    "repeated_motif": "repeated_motif" in event.tags,
                }

                source_attack_db = float(source_attack["pitch_attack_db"])
                mixture_attack_db = float(mixture_attack["pitch_attack_db"])
                duration = event.end - event.start
                raw = _raw_confidence(event)
                supported = _strong_support(event)

                # A false re-trigger commonly sits on a sustained harmonic, so
                # pitch SNR can be excellent while the pitch energy itself shows
                # no new rise at the alleged onset. Require agreement from both
                # the separated source and original mixture before rejecting.
                flat_attack = source_attack_db < 1.35 and mixture_attack_db < 1.10
                very_flat_attack = source_attack_db < .65 and mixture_attack_db < .65

                if supported:
                    reject = (
                        very_flat_attack
                        and event.confidence < .88
                        and (duration < .45 or raw < .80)
                    )
                elif source == "piano":
                    reject = (
                        flat_attack
                        and event.confidence < .84
                        and (duration < .52 or raw < .76)
                    )
                else:  # guitar
                    reject = (
                        flat_attack
                        and event.confidence < .88
                        and (duration < .58 or raw < .80)
                    )

                if reject:
                    checked_event = _annotate(event, evidence, "rhythm_attack_rejected")
                    replacements[id(event)] = None
                    rejected.append({
                        "event": checked_event.to_dict(),
                        "reason": "off_rhythm_retrigger_without_audio_attack",
                    })
                else:
                    replacements[id(event)] = _annotate(event, evidence, "rhythm_attack_validated")

    kept: list[MusicEvent] = []
    for event in master.events:
        if id(event) not in replacements:
            kept.append(event)
            continue
        replacement = replacements[id(event)]
        if replacement is not None:
            kept.append(replacement)

    master.events = sorted(kept, key=lambda event: (event.start, event.source, event.pitch or 0))
    master.rejected.extend(rejected)
    reasons = Counter(item["reason"] for item in rejected)
    master.provenance["rhythm_attack_guard"] = {
        "version": 1,
        "considered": len(targets),
        "candidates": candidates,
        "checked": checked,
        "removed": len(rejected),
        "reasons": dict(sorted(reasons.items())),
        "policy": "off-grid singleton re-trigger rejection only when source and mixture lack a local pitch attack",
    }
    return master
