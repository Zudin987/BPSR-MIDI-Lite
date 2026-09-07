"""Precision-first post-fusion musical sanity guard for Audio -> Band.

Separation quality cannot prevent every transcription hallucination: a harmonic,
brief bleed, or decoder fragment can still become a plausible MIDI note.  This
layer runs on the final musical map (after beta.9 fusion, motif marking and
instrument-presence filtering, but before BPSR physical octave/key mapping).
It removes only unsupported local outliers and keeps independently corroborated
notes, repeated riffs, chords and normal sixteenth-note syncopation.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import replace
from statistics import median

_APPLIED = False
_GUARDED_SOURCES = {"piano", "guitar", "other"}


def _supported(event) -> bool:
    if event.tags & {"independent_agreement", "repeated_motif", "targeted_repair"}:
        return True
    for key in ("beta9_support_engines", "agreement_engines"):
        if event.evidence.get(key):
            return True
    return False


def _raw_confidence(event) -> float:
    value = event.original_confidence
    return float(event.confidence if value is None else value)


def _onset_groups(events, tolerance: float = .045):
    groups = []
    for event in sorted(events, key=lambda item: (item.start, item.pitch or -1)):
        if not groups or event.start - groups[-1][0].start > tolerance:
            groups.append([])
        groups[-1].append(event)
    return groups


def _group_pitch(group) -> float | None:
    pitches = [event.pitch for event in group if event.pitch is not None]
    return float(median(pitches)) if pitches else None


def _group_pitch_classes(group) -> set[int]:
    return {event.pitch % 12 for event in group if event.pitch is not None}


def _group_anchor(group) -> bool:
    """True for an onset strong enough to describe the surrounding phrase."""
    return (
        len(group) >= 2 or
        any(_supported(event) for event in group) or
        max((event.confidence for event in group), default=0.0) >= .78
    )


def _neighbor_anchor(groups, index: int, direction: int):
    stop = max(-1, index - 4) if direction < 0 else min(len(groups), index + 4)
    for candidate in range(index + direction, stop, direction):
        if 0 <= candidate < len(groups) and _group_anchor(groups[candidate]):
            return candidate, groups[candidate]
    return None, None


def _reject(event, reason: str) -> dict:
    return {"event": event.to_dict(), "reason": reason}


def _beat_grid_context(beat_map, timestamp: float):
    """Measure distance to a local sixteenth-note grid without quantizing MIDI."""
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

    # Allow the intro/tail to extrapolate the nearest measured beat interval.
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
    # Tolerance scales with tempo and remains loose enough for humanized attacks.
    tolerance = max(.042, min(.078, interval * .11))
    return {
        "distance": distance,
        "interval": interval,
        "nearest": nearest,
        "tolerance": tolerance,
        "off_grid": distance > tolerance,
    }


def _local_pitch_context(groups, index: int):
    previous_index, previous = _neighbor_anchor(groups, index, -1)
    next_index, following = _neighbor_anchor(groups, index, 1)
    if previous is None or following is None:
        return None
    return {
        "previous_index": previous_index,
        "next_index": next_index,
        "previous": previous,
        "next": following,
        "previous_pitch": _group_pitch(previous),
        "next_pitch": _group_pitch(following),
    }


def _rhythm_orphan(event, current_group, context, beat_map) -> bool:
    if len(current_group) != 1 or _supported(event) or event.source not in _GUARDED_SOURCES:
        return False
    grid = _beat_grid_context(beat_map, event.start)
    if not grid or not grid["off_grid"]:
        return False

    previous = context["previous"]
    following = context["next"]
    previous_grid = _beat_grid_context(beat_map, previous[0].start)
    next_grid = _beat_grid_context(beat_map, following[0].start)
    if not previous_grid or not next_grid or previous_grid["off_grid"] or next_grid["off_grid"]:
        return False

    interval = grid["interval"]
    max_context = max(1.0, interval * 3.0)
    if event.start - previous[0].start > max_context or following[0].start - event.start > max_context:
        return False

    raw = _raw_confidence(event)
    duration = event.end - event.start
    spectral = float(event.evidence.get("spectral_confidence", .65))
    leakage = float(event.evidence.get("stem_leakage", .35) or 0.0)

    # Transkun is the piano authority, so require a clearly orphaned/moderate
    # event rather than treating every expressive attack as suspicious.
    if event.engine == "transkun":
        return (
            event.confidence < .82 and
            (duration < .30 or spectral < .62 or leakage > .42 or raw < .70)
        )

    # Basic Pitch guitar/other false positives are commonly brief single-engine
    # activations. Keep strong sustained notes even when played ahead/behind.
    if event.engine == "basic_pitch":
        return event.confidence < .82 and (raw < .72 or duration < .36 or spectral < .58)
    return event.confidence < .76 and (duration < .28 or spectral < .55)


def guard_events(events, beat_map=None):
    """Return (kept, rejected), favoring precision for isolated piano/guitar notes."""
    by_source = defaultdict(list)
    passthrough = []
    for event in events:
        if event.pitch is None or event.source == "drums":
            passthrough.append(event)
        else:
            by_source[event.source].append(event)

    kept = list(passthrough)
    rejected = []

    for source, source_events in by_source.items():
        groups = _onset_groups(source_events)
        group_lookup = {id(event): index for index, group in enumerate(groups) for event in group}
        group_pitches = [_group_pitch(group) for group in groups]

        for event in source_events:
            group_index = group_lookup[id(event)]
            current_group = groups[group_index]
            supported = _supported(event)
            raw = _raw_confidence(event)
            duration = event.end - event.start

            # Require more activation evidence for a lone Basic Pitch guitar
            # note than for a note that belongs to a chord or has another judge.
            basic_floor = .54 if source == "guitar" else .50 if source in {"piano", "other"} else .48
            if (
                event.engine == "basic_pitch" and raw < basic_floor and not supported and
                (len(current_group) == 1 or raw < .44)
            ):
                rejected.append(_reject(event, "unsupported_basic_pitch_activation"))
                continue

            fragment_floor = .10 if source in {"guitar", "other"} else .085 if source == "piano" else .075
            if duration < fragment_floor and event.confidence < .70 and not supported:
                rejected.append(_reject(event, "unsupported_pitch_fragment"))
                continue

            previous_pitch = group_pitches[group_index - 1] if group_index > 0 else None
            next_pitch = group_pitches[group_index + 1] if group_index + 1 < len(groups) else None
            previous_time = groups[group_index - 1][0].start if group_index > 0 else None
            next_time = groups[group_index + 1][0].start if group_index + 1 < len(groups) else None
            close_context = (
                previous_pitch is not None and next_pitch is not None and
                previous_time is not None and next_time is not None and
                event.start - previous_time <= .75 and next_time - event.start <= .75
            )

            if source in {"vocals", "bass"} and close_context and not supported:
                if abs(previous_pitch - next_pitch) <= 5:
                    anchor = (previous_pitch + next_pitch) / 2.0
                    distance = abs(event.pitch - anchor)
                    candidates = [event.pitch + shift for shift in (-24, -12, 12, 24)]
                    candidates = [pitch for pitch in candidates if 0 <= pitch <= 127]
                    corrected = min(candidates, key=lambda pitch: abs(pitch - anchor)) if candidates else event.pitch
                    corrected_distance = abs(corrected - anchor)
                    if distance >= 11 and corrected_distance <= 4 and event.confidence < .88:
                        kept.append(replace(
                            event,
                            pitch=int(corrected),
                            tags=event.tags | {"local_octave_glitch_corrected"},
                            evidence={
                                **event.evidence,
                                "pre_pitch_guard_pitch": event.pitch,
                                "pitch_guard_anchor": anchor,
                                "pitch_guard_reason": "neighbor_consensus_octave",
                            },
                        ))
                        continue
                    if distance >= 12 and event.confidence < .70:
                        rejected.append(_reject(event, "isolated_monophonic_pitch_outlier"))
                        continue

            context = _local_pitch_context(groups, group_index) if source in _GUARDED_SOURCES else None
            if context and len(current_group) == 1 and not supported:
                previous_pitch = context["previous_pitch"]
                next_pitch = context["next_pitch"]
                local_anchor = None
                local_distance = 0.0
                if previous_pitch is not None and next_pitch is not None and abs(previous_pitch - next_pitch) <= 7:
                    local_anchor = (previous_pitch + next_pitch) / 2.0
                    local_distance = abs(event.pitch - local_anchor)
                    if local_distance >= 11 and event.confidence < .82 and (duration < .40 or raw < .72):
                        rejected.append(_reject(event, "isolated_polyphonic_pitch_outlier"))
                        continue

                # A weak singleton foreign to both neighboring chords is a
                # likely bleed/harmonic only when pitch or rhythm also disagrees.
                # This explicitly preserves legitimate on-grid passing tones.
                previous_pcs = _group_pitch_classes(context["previous"])
                next_pcs = _group_pitch_classes(context["next"])
                neighbor_pcs = previous_pcs | next_pcs
                grid = _beat_grid_context(beat_map, event.start)
                chord_context = len(previous_pcs) >= 2 and len(next_pcs) >= 2
                extra_disagreement = bool(grid and grid["off_grid"]) or local_distance >= 8
                if (
                    chord_context and event.pitch % 12 not in neighbor_pcs and extra_disagreement and
                    event.confidence < .80 and
                    (duration < .34 or raw < .68 or (grid and grid["off_grid"]))
                ):
                    rejected.append(_reject(event, "unsupported_harmonic_orphan"))
                    continue

                if _rhythm_orphan(event, current_group, context, beat_map):
                    rejected.append(_reject(event, "off_rhythm_singleton"))
                    continue

            kept.append(event)

    return sorted(kept, key=lambda event: (event.start, event.source, event.pitch or 0)), rejected


def apply_pitch_guard() -> None:
    global _APPLIED
    if _APPLIED:
        return
    from . import fusion, pipeline

    # Apply after beta.9 build_master so repeated motifs and instrument-presence
    # decisions are already available as evidence. This is still before BPSR
    # range fitting, so a hallucinated note cannot be made plausible by octave
    # remapping later in the arranger.
    original_build_master = fusion.build_master

    def build_master(digest, duration, beats, primary, reference, provenance, warnings):
        master = original_build_master(
            digest, duration, beats, primary, reference, provenance, warnings
        )
        guarded, extra = guard_events(master.events, master.beat_map)
        master.events = guarded
        master.rejected.extend(extra)
        reasons = Counter(item["reason"] for item in extra)
        master.provenance["pitch_guard"] = {
            "version": 2,
            "removed": len(extra),
            "reasons": dict(sorted(reasons.items())),
            "policy": "precision-first unsupported pitch/rhythm orphan rejection",
        }
        return master

    fusion.build_master = build_master
    # pipeline imported build_master by value; keep the active conversion path in sync.
    pipeline.build_master = build_master
    _APPLIED = True
