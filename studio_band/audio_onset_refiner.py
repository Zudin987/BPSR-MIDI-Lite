"""Refine clearly mis-timed Piano/Guitar note-ons to the nearby real audio attack.

This is deliberately not beat quantization.  It only considers singleton notes that
look rhythmically orphaned relative to nearby phrase anchors, then searches a small
window around the transcribed timestamp for the same pitch attack in both the
resolved instrument stem and the original mixture.  When both agree on a much
stronger nearby onset, the MIDI note is moved to that audio onset while preserving
its duration.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import ExitStack
from dataclasses import replace
import math
from pathlib import Path
from typing import Any

from .music import MasterSong, MusicEvent
from .rhythm_attack_guard import _onset_groups, _pitch_window, _rhythm_orphan_context

_TARGETS = {"piano", "guitar"}
_SCAN_STEP = .015
_SCAN_RADIUS = .090
_MIN_SHIFT = .025
_LOCAL_WINDOW = .050
_LOCAL_GAP = .008


def _local_attack(handle, pitch: int, onset: float) -> dict[str, float]:
    """Measure a short pitch-energy rise suitable for onset localization."""
    pre_start = onset - _LOCAL_GAP - _LOCAL_WINDOW
    pre_end = onset - _LOCAL_GAP
    if pre_start < 0.0 or pre_end <= pre_start:
        return {
            "pitch_attack_db": -60.0,
            "rms_attack_db": -60.0,
            "post_pitch_snr_db": -120.0,
            "post_rms_dbfs": -120.0,
            "post_signal": 0.0,
        }

    pre = _pitch_window(handle, pitch, pre_start, pre_end)
    post = _pitch_window(handle, pitch, onset, onset + _LOCAL_WINDOW)
    pitch_attack_db = 10.0 * math.log10((post["signal"] + 1e-18) / (pre["signal"] + 1e-18))
    rms_attack_db = 20.0 * math.log10((post["rms"] + 1e-12) / (pre["rms"] + 1e-12))
    post_rms_dbfs = 20.0 * math.log10(max(post["rms"], 1e-12))
    return {
        "pitch_attack_db": max(-60.0, min(60.0, float(pitch_attack_db))),
        "rms_attack_db": max(-60.0, min(60.0, float(rms_attack_db))),
        "post_pitch_snr_db": float(post["snr_db"]),
        "post_rms_dbfs": max(-120.0, min(0.0, float(post_rms_dbfs))),
        "post_signal": float(post["signal"]),
    }


def _probe(source_handle, mixture_handle, pitch: int, timestamp: float, offset: float) -> dict[str, Any]:
    source = _local_attack(source_handle, pitch, timestamp)
    mixture = _local_attack(mixture_handle, pitch, timestamp)
    joint = min(float(source["pitch_attack_db"]), float(mixture["pitch_attack_db"]))
    return {
        "timestamp": timestamp,
        "offset": offset,
        "joint_attack_db": joint,
        "source": source,
        "mixture": mixture,
    }


def _find_nearby_attack(source_handle, mixture_handle, pitch: int, onset: float) -> dict[str, Any] | None:
    """Return a conservative nearby attack correction, or None."""
    source_duration = len(source_handle) / max(1, int(source_handle.samplerate))
    mixture_duration = len(mixture_handle) / max(1, int(mixture_handle.samplerate))
    audio_end = min(source_duration, mixture_duration)

    probes: list[dict[str, Any]] = []
    steps = int(round(_SCAN_RADIUS / _SCAN_STEP))
    for index in range(-steps, steps + 1):
        offset = index * _SCAN_STEP
        timestamp = onset + offset
        if timestamp < _LOCAL_WINDOW + _LOCAL_GAP or timestamp + _LOCAL_WINDOW > audio_end:
            continue
        probes.append(_probe(source_handle, mixture_handle, pitch, timestamp, offset))

    if not probes:
        return None

    current = min(probes, key=lambda row: abs(float(row["offset"])))
    best = max(
        probes,
        key=lambda row: (float(row["joint_attack_db"]), -abs(float(row["offset"]))),
    )
    shift = float(best["offset"])
    if abs(shift) < _MIN_SHIFT:
        return None

    source = best["source"]
    mixture = best["mixture"]
    # Require a real pitch attack in both views, not just a broad transient.
    if float(source["pitch_attack_db"]) < 2.25 or float(mixture["pitch_attack_db"]) < 1.75:
        return None
    if float(source["post_pitch_snr_db"]) < .35 or float(mixture["post_pitch_snr_db"]) < -.25:
        return None
    # Extremely quiet rises are usually separator/noise-floor movement.  Skipping
    # them is safer than moving a valid expressive note.
    if float(source["post_rms_dbfs"]) < -58.0 or float(mixture["post_rms_dbfs"]) < -58.0:
        return None

    improvement = float(best["joint_attack_db"]) - float(current["joint_attack_db"])
    if improvement < 1.75:
        return None

    return {
        "timestamp": float(best["timestamp"]),
        "shift_seconds": shift,
        "joint_attack_db": round(float(best["joint_attack_db"]), 3),
        "original_joint_attack_db": round(float(current["joint_attack_db"]), 3),
        "improvement_db": round(improvement, 3),
        "source_attack_db": round(float(source["pitch_attack_db"]), 3),
        "mixture_attack_db": round(float(mixture["pitch_attack_db"]), 3),
        "source_post_snr_db": round(float(source["post_pitch_snr_db"]), 3),
        "mixture_post_snr_db": round(float(mixture["post_pitch_snr_db"]), 3),
    }


def _refined_event(event: MusicEvent, master: MasterSong, timing: dict[str, Any],
                   rhythm: dict[str, Any]) -> MusicEvent:
    duration = event.end - event.start
    new_start = max(0.0, min(master.duration - .001, float(timing["timestamp"])))
    new_end = min(master.duration, new_start + duration)
    if new_end <= new_start:
        new_end = min(master.duration, new_start + .001)
    evidence = {
        "original_start": round(float(event.start), 6),
        "refined_start": round(new_start, 6),
        "shift_seconds": round(new_start - float(event.start), 6),
        "rhythm_context": rhythm,
        **{key: value for key, value in timing.items() if key not in {"timestamp", "shift_seconds"}},
    }
    return replace(
        event,
        start=new_start,
        end=new_end,
        tags=event.tags | {"audio_onset_refined"},
        evidence={**event.evidence, "audio_onset_refinement": evidence},
    )


def refine_audio_onsets(master: MasterSong, stems: dict[str, Path], mixture: Path) -> MasterSong:
    """Repair only strong, locally proven timing errors on suspicious singleton notes."""
    import soundfile as sf

    targets = [
        event for event in master.events
        if event.source in _TARGETS and event.pitch is not None
    ]
    if not targets:
        master.provenance["audio_onset_refiner"] = {
            "version": 1, "considered": 0, "candidates": 0, "refined": 0,
        }
        return master

    mixture = Path(mixture)
    needed_sources = {event.source for event in targets}
    source_paths = {source: Path(stems[source]) for source in needed_sources if source in stems}
    if not mixture.is_file() or any(source not in source_paths or not source_paths[source].is_file()
                                    for source in needed_sources):
        raise OSError("Target stem or prepared mixture is missing for audio onset refinement")

    by_source: dict[str, list[MusicEvent]] = defaultdict(list)
    for event in targets:
        by_source[event.source].append(event)

    replacements: dict[int, MusicEvent] = {}
    candidates = refined = 0
    shifts_ms: list[float] = []

    with ExitStack() as stack:
        source_handles = {
            source: stack.enter_context(sf.SoundFile(str(source_paths[source]), "r"))
            for source in needed_sources
        }
        mixture_handle = stack.enter_context(sf.SoundFile(str(mixture), "r"))

        for source, source_events in by_source.items():
            groups = _onset_groups(source_events)
            for index, group in enumerate(groups):
                rhythm = _rhythm_orphan_context(groups, index, master.beat_map)
                if rhythm is None:
                    continue
                candidates += 1
                event = group[0]
                timing = _find_nearby_attack(
                    source_handles[source], mixture_handle, int(event.pitch), float(event.start)
                )
                if timing is None:
                    continue
                replacement = _refined_event(event, master, timing, rhythm)
                replacements[id(event)] = replacement
                refined += 1
                shifts_ms.append(abs(replacement.start - event.start) * 1000.0)

    if replacements:
        master.events = sorted(
            [replacements.get(id(event), event) for event in master.events],
            key=lambda event: (event.start, event.source, event.pitch or 0),
        )

    master.provenance["audio_onset_refiner"] = {
        "version": 1,
        "considered": len(targets),
        "candidates": candidates,
        "refined": refined,
        "max_search_ms": int(round(_SCAN_RADIUS * 1000.0)),
        "mean_abs_shift_ms": round(sum(shifts_ms) / len(shifts_ms), 3) if shifts_ms else 0.0,
        "max_abs_shift_ms": round(max(shifts_ms), 3) if shifts_ms else 0.0,
        "policy": "audio-grounded timing repair only; never snap directly to the beat grid",
    }
    return master
