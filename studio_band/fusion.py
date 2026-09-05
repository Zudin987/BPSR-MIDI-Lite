"""Conservative evidence fusion; confidence is a heuristic, not a calibrated probability."""
from __future__ import annotations

from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import replace

from .music import BeatMap, DRUM_ROLES, MasterSong, MusicEvent

PLAUSIBLE = {"vocals": (36, 90), "piano": (21, 108), "guitar": (40, 88), "bass": (23, 60), "other": (36, 96)}


def reject(event: MusicEvent, reason: str) -> dict:
    return {"event": event.to_dict(), "reason": reason}


def _index(events):
    buckets = defaultdict(list)
    for event in events:
        key = (event.source, event.role if event.source == "drums" else event.pitch)
        buckets[key].append(event)
    return {key: (sorted(values, key=lambda e: e.start), sorted(e.start for e in values)) for key, values in buckets.items()}


def agreements(event, index):
    key = (event.source, event.role if event.source == "drums" else event.pitch)
    values, starts = index.get(key, ([], []))
    left, right = bisect_left(starts, event.start - .085), bisect_left(starts, event.start + .085)
    return [other for other in values[left:right] if other.engine != event.engine and
            min(event.end, other.end) > max(event.start, other.start) - .025]


def soft_align(event: MusicEvent, support: list[MusicEvent], beats: BeatMap) -> MusicEvent:
    shift = 0.0
    if support:
        # Only partially reconcile independent estimates, preserving most of the
        # specialist's microtiming. No cross-instrument onset clustering.
        weight = sum(x.confidence for x in support) + event.confidence * 2
        center = (sum(x.start*x.confidence for x in support) + event.start*event.confidence*2) / max(.01, weight)
        shift = max(-.012, min(.012, (center-event.start)*.4))
    if beats.beats and beats.confidence >= .65 and event.end-event.start >= .12:
        index = bisect_left(beats.beats, event.start)
        candidates = beats.beats[max(0, index-1):index+1]
        if candidates:
            target = min(candidates, key=lambda t: abs(t-event.start))
            residual = target - event.start
            if abs(residual) <= .025:
                shift += max(-.006, min(.006, residual * .2))
    shift = max(-min(.015, event.start), min(.015, shift))
    if not shift:
        return event
    return replace(event, start=event.start+shift, end=event.end+shift,
                   evidence={**event.evidence, "original_start": event.start, "original_end": event.end,
                             "timing_correction_seconds": shift})


def fuse(primary: list[MusicEvent], reference: list[MusicEvent], beat_map: BeatMap,
         stem_metrics: dict | None = None) -> tuple[list[MusicEvent], list[dict]]:
    index = _index(reference)
    available = {e.source for e in reference}
    kept, removed = [], []
    stem_metrics = stem_metrics or {}
    for event in primary:
        support = agreements(event, index)
        score = event.confidence
        evidence = {**event.evidence, "agreement_engines": sorted({e.engine for e in support})}
        if support:
            # Saturating corroboration: duplicates from one model do not vote.
            by_engine = {e.engine: e for e in sorted(support, key=lambda e: e.confidence)}
            score += (1-score) * min(.55, .25 + .12*sum(e.confidence for e in by_engine.values()))
        elif event.source in available:
            # Absence is only weak counter-evidence; MT3 itself misses notes.
            score -= .055 * (1-event.confidence)
        duration = event.end-event.start
        if duration < .055 and event.source != "drums":
            score -= .22
        if event.pitch is not None:
            low, high = PLAUSIBLE[event.source]
            distance = max(low-event.pitch, event.pitch-high, 0)
            score -= min(.4, distance*.018)
            evidence["register_distance"] = distance
        metric = stem_metrics.get(event.source, {})
        # Separation has no measured purity posterior. Use only a modest prior,
        # and expose this explicitly so it cannot be mistaken for a model score.
        prior = float(metric.get("confidence_prior", .7))
        score *= .85 + .15 * max(0, min(1, prior))
        evidence["separation_prior"] = prior
        if metric.get("rms", 1) < 1e-5:
            score *= .4
        score = max(0.0, min(.99, score))
        fused = replace(event, confidence=score, evidence=evidence)
        if score < (.39 if event.source == "vocals" else .33):
            removed.append(reject(fused, "low_confidence"))
        else:
            kept.append(soft_align(fused, support, beat_map))
    return sorted(kept, key=lambda e: (e.start, e.source, e.pitch or 0)), removed


def melody_contour(events: list[MusicEvent]) -> tuple[list[MusicEvent], list[dict]]:
    """Choose a continuous monophonic voice; preserve genuine repeated attacks."""
    ordered = sorted(events, key=lambda e: (e.start, -e.confidence))
    groups = []
    for e in ordered:
        if not groups or e.start-groups[-1][0].start > .04:
            groups.append([])
        groups[-1].append(e)
    kept, removed = [], []
    previous = None
    for group in groups:
        def score(e):
            interval = abs(e.pitch-previous.pitch) if previous and e.start-previous.end < .65 else 0
            return e.confidence - min(.28, interval*.011)
        event = max(group, key=score)
        removed.extend(reject(e, "vocal_duplicate_or_harmonic") for e in group if e is not event)
        if event.end-event.start < .075 and event.confidence < .7:
            removed.append(reject(event, "vocal_breath_or_fragment"))
            continue
        if previous and event.start-previous.end < .5:
            jump = event.pitch-previous.pitch
            # Correct isolated octave errors only with weak evidence and a much
            # smoother octave-equivalent contour. Strong real leaps survive.
            if abs(jump) >= 12 and event.confidence < .65:
                candidate = min((event.pitch-12, event.pitch, event.pitch+12), key=lambda p: abs(p-previous.pitch))
                if 36 <= candidate <= 90 and abs(candidate-previous.pitch) <= 4:
                    event = replace(event, pitch=candidate, tags=event.tags | {"octave_glitch_corrected"},
                                    evidence={**event.evidence, "pre_contour_pitch": event.pitch})
            if previous.pitch == event.pitch and -.02 <= event.start-previous.end <= .045:
                kept[-1] = replace(previous, end=max(previous.end, event.end),
                                   confidence=max(previous.confidence, event.confidence),
                                   tags=previous.tags | {"merged_fragment"})
                removed.append(reject(event, "vocal_split_fragment_merged"))
                previous = kept[-1]
                continue
            if previous.end > event.start:
                kept[-1] = replace(previous, end=max(previous.start+.001, event.start))
        event = replace(event, role="MAIN_MELODY")
        kept.append(event)
        previous = event
    return kept, removed


def bass_contour(events: list[MusicEvent]) -> tuple[list[MusicEvent], list[dict]]:
    groups, kept, removed = [], [], []
    for e in sorted(events, key=lambda e: (e.start, e.pitch)):
        if not groups or e.start-groups[-1][0].start > .045:
            groups.append([])
        groups[-1].append(e)
    previous = None
    for group in groups:
        def score(e):
            harmonic = any(x.pitch < e.pitch and (e.pitch-x.pitch) in {12, 19, 24} and x.confidence >= e.confidence*.65 for x in group)
            contour = min(.2, abs(e.pitch-previous.pitch)*.009) if previous and e.start-previous.end < .5 else 0
            return e.confidence - .30*harmonic - contour
        selected = max(group, key=score)
        removed.extend(reject(e, "bass_harmonic_or_polyphony") for e in group if e is not selected)
        if kept and kept[-1].end > selected.start:
            kept[-1] = replace(kept[-1], end=max(kept[-1].start+.001, selected.start))
        kept.append(replace(selected, role="BASS"))
        previous = selected
    return kept, removed


def mark_motifs(events: list[MusicEvent]) -> list[MusicEvent]:
    by_source = defaultdict(list)
    for event in events:
        if event.source in {"guitar", "piano", "other"}:
            by_source[event.source].append(event)
    protected = set()
    for source in by_source.values():
        line = sorted(source, key=lambda e: (e.start, e.pitch))
        windows = []
        for i in range(len(line)-3):
            run = line[i:i+4]
            if any(b.start-a.start < .075 or b.start-a.start > 1.2 for a,b in zip(run, run[1:])):
                continue
            key = tuple(b.pitch-a.pitch for a,b in zip(run, run[1:]))
            rhythm = tuple(round((b.start-a.start)/max(.01, run[-1].start-run[0].start), 1) for a,b in zip(run, run[1:]))
            windows.append(((key, rhythm), run))
        counts = Counter(key for key, _ in windows)
        for key, run in windows:
            if counts[key] >= 2:
                protected.update(e.event_id for e in run if e.confidence >= .55)
    return [replace(e, role="RIFF", tags=e.tags | {"repeated_motif"}) if e.event_id in protected else e for e in events]


def build_master(digest: str, duration: float, beats: BeatMap, primary: list[MusicEvent],
                 reference: list[MusicEvent], provenance: dict, warnings: list[str]) -> MasterSong:
    fused, rejected = fuse(primary, reference, beats, provenance.get("stem_metrics", {}))
    vocal, discarded = melody_contour([e for e in fused if e.source == "vocals"])
    rejected.extend(discarded)
    bass, discarded = bass_contour([e for e in fused if e.source == "bass"])
    rejected.extend(discarded)
    events = mark_motifs([e for e in fused if e.source not in {"vocals", "bass"}] + vocal + bass)
    # Neural decoders can extend the final note; clip only at the common song
    # boundary, never trim the leading silence of individual streams.
    events = [replace(e, end=min(duration, e.end)) for e in events if e.start < duration]
    if not vocal:
        warnings = [*warnings, "No reliable vocal melody was detected; instrumental material is retained."]
    return MasterSong(digest, duration, beats, sorted(events, key=lambda e: (e.start, e.source)),
                      provenance, rejected, warnings)
