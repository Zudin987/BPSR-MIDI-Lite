"""Conservative post-fusion pitch sanity guard for Audio -> Band.

Separation quality cannot fix a transcription engine that hears a harmonic or
brief bleed as a real note.  This layer runs after beta.9 evidence fusion and
before melody/bass contouring and physical BPSR octave mapping.  It removes only
unsupported, locally implausible events and corrects a narrow class of isolated
monophonic octave glitches when both neighboring phrases agree.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from statistics import median

_APPLIED = False


def _supported(event) -> bool:
    if event.tags & {"independent_agreement", "repeated_motif", "targeted_repair"}:
        return True
    for key in ("beta9_support_engines", "agreement_engines"):
        value = event.evidence.get(key)
        if value:
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


def _reject(event, reason: str) -> dict:
    return {"event": event.to_dict(), "reason": reason}


def guard_events(events):
    """Return (kept, rejected) without changing supported musical leaps/chords."""
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
            supported = _supported(event)
            raw = _raw_confidence(event)
            duration = event.end - event.start

            # Basic Pitch activation amplitude is useful evidence, but beta.9's
            # old generic .33 fusion floor was too permissive for unsupported
            # single-engine detections. Keep weak notes only when another engine
            # or a repeated motif independently corroborates them.
            if event.engine == "basic_pitch" and raw < .48 and not supported:
                rejected.append(_reject(event, "unsupported_basic_pitch_activation"))
                continue
            if duration < .075 and event.confidence < .66 and not supported:
                rejected.append(_reject(event, "unsupported_pitch_fragment"))
                continue

            group_index = group_lookup[id(event)]
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
                # Monophonic lines should not contain one isolated octave spike
                # between two nearby notes that agree on the surrounding contour.
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

            if source in {"piano", "guitar", "other"} and close_context and not supported:
                # Chords can legitimately span several octaves, so only judge a
                # singleton onset against the immediately surrounding phrases.
                current_group = groups[group_index]
                if len(current_group) == 1 and abs(previous_pitch - next_pitch) <= 7:
                    anchor = (previous_pitch + next_pitch) / 2.0
                    distance = abs(event.pitch - anchor)
                    if distance >= 11 and event.confidence < .80 and (duration < .32 or raw < .68):
                        rejected.append(_reject(event, "isolated_polyphonic_pitch_outlier"))
                        continue

            kept.append(event)

    return sorted(kept, key=lambda event: (event.start, event.source, event.pitch or 0)), rejected


def apply_pitch_guard() -> None:
    global _APPLIED
    if _APPLIED:
        return
    from . import fusion

    original_fuse = fusion.fuse

    def fuse(primary, reference, beat_map, stem_metrics=None):
        events, rejected = original_fuse(primary, reference, beat_map, stem_metrics)
        guarded, extra = guard_events(events)
        rejected.extend(extra)
        return guarded, rejected

    fusion.fuse = fuse
    _APPLIED = True
