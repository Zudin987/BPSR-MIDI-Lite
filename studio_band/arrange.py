"""Musical reduction feeding the project's existing Band v4 and physical mapper."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path

import midi_engine as me
import playback_adaptive as adaptive
import playback_overhaul as playback
from .fusion import reject
from .music import DRUM_ROLES, MasterSong, MusicEvent
from .storage import read_json

ARRANGER_VERSION = "band4-audio1"
PARTS = ("piano", "guitar", "bass", "drums")
ENGINE_PART = {"piano": "keyboard", "guitar": "guitar", "bass": "bass"}
PRIORITY = {"MAIN_MELODY": 1000, "MELODY": 850, "RIFF": 750, "BASS": 650,
            "KICK": 600, "SNARE": 580, "RHYTHM": 550, "HARMONY": 350, "DECORATION": 100}


@dataclass
class ArrangementSettings:
    main_melody: str = "auto"
    tiers: dict[str, str] = field(default_factory=lambda: {"piano": "tier4", "guitar": "tier3", "bass": "tier2"})
    polyphony: dict[str, int] = field(default_factory=lambda: {"piano": 4, "guitar": 3, "bass": 1})

    def validate(self):
        if self.main_melody not in {"auto", "piano", "guitar"}:
            raise ValueError("Main Melody must be Auto, Piano or Guitar")
        for part, engine in ENGINE_PART.items():
            if self.tiers.get(part) not in me.INSTRUMENT_UNLOCK_PROFILES[engine]:
                raise ValueError(f"Invalid {part} unlock category")
            if not isinstance(self.polyphony.get(part), int) or not 1 <= self.polyphony[part] <= 6:
                raise ValueError("Polyphony must be an integer from 1 to 6")
        if self.polyphony["bass"] != 1:
            raise ValueError("The bass arrangement must remain monophonic")


def load_drum_profile(path: Path | None = None) -> dict:
    profile = read_json(path or Path(__file__).resolve().parent.parent / "profiles" / "bpsr_drums.json")
    if (profile.get("schema_version"), profile.get("min_pitch"), profile.get("max_pitch"), profile.get("slot_count")) != (1, 60, 83, 24):
        raise ValueError("Drum profile must describe the verified 24 C4-B5 slots")
    if any(profile.get(k) for k in ("high_octave", "low_octave", "page_switching")):
        raise ValueError("Drums cannot use octave or page controls")
    if set(profile.get("mapping", {})) != DRUM_ROLES:
        raise ValueError("Drum profile is missing semantic roles")
    if any(not isinstance(p, int) or not 60 <= p <= 83 for p in profile["mapping"].values()):
        raise ValueError("Drum mapping contains an invalid pad")
    if not .025 <= profile.get("minimum_retrigger_seconds", 0) <= .3:
        raise ValueError("Invalid drum retrigger constraint")
    if not .025 <= profile.get("hit_duration_seconds", 0) <= .3:
        raise ValueError("Invalid drum hit duration")
    if not 1 <= profile.get("max_polyphony", 0) <= 12:
        raise ValueError("Invalid drum polyphony")
    return profile


def _range(part, settings):
    profile = me.get_unlock_profile(settings.tiers[part], ENGINE_PART[part])
    return max(profile.low, 36) if part == "piano" else profile.low, profile.high


def _importance(event):
    return PRIORITY.get(event.role, 500 if event.role in DRUM_ROLES else 200) + event.confidence*30


def melody_assignment(melody: list[MusicEvent], parts: dict[str, list[MusicEvent]], settings: ArrangementSettings) -> dict:
    scores = {}
    for part in ("piano", "guitar"):
        low, high = _range(part, settings)
        shift, conflict, riff, pressure = 0.0, 0.0, 0.0, 0.0
        for event in melody:
            pitches = list(range(low + (event.pitch-low) % 12, high+1, 12))
            displacement = min(abs(p-event.pitch) for p in pitches)
            shift += displacement / 12
            overlapping = [e for e in parts[part] if e.start < event.end and e.end > event.start]
            conflict += len(overlapping)
            riff += sum(e.role == "RIFF" for e in overlapping)
            pressure += max(0, len(overlapping)+1-settings.polyphony[part])
        count = max(1, len(melody))
        scores[part] = round(max(0, min(100, 95 - shift/count*12 - conflict/count*2 - riff/count*7 - pressure/count*5)), 2)
    selected = settings.main_melody if settings.main_melody != "auto" else max(scores, key=scores.get)
    return {"part": selected if melody else None, "requested": settings.main_melody,
            "scores": scores, "policy": "one owner for the song to protect phrase continuity",
            "melody_notes": len(melody)}


def _to_source(events):
    return [me.SourceNote(e.start, e.end, e.pitch, e.velocity, i) for i,e in enumerate(events)]


def fit_contour(events: list[MusicEvent], low: int, high: int) -> list[MusicEvent]:
    source = _to_source(events)
    fitted, _ = me._fit_bass_contour_notes(source, low, high)
    by_serial = {n.serial: n.pitch for n in fitted}
    return [replace(e, pitch=by_serial[i], evidence={**e.evidence, "pre_range_pitch": e.pitch})
            if by_serial[i] != e.pitch else e for i,e in enumerate(events)]


def simplify_chords(events: list[MusicEvent], limit: int, part: str) -> tuple[list[MusicEvent], list[dict]]:
    groups, kept, removed = [], [], []
    for e in sorted(events, key=lambda e: (e.start, -_importance(e), e.pitch or 0)):
        if not groups or e.start-groups[-1][0].start > .030:
            groups.append([])
        groups[-1].append(e)
    for group in groups:
        if len(group) <= limit:
            kept.extend(group)
            continue
        root = adaptive._infer_root_pitch_class(_to_source(group))
        candidates, selected, selected_pcs = list(group), [], set()
        while candidates and len(selected) < limit:
            def score(e):
                interval = (e.pitch-root) % 12
                function = {0: 24, 3: 18, 4: 18, 10: 15, 11: 15, 7: 7}.get(interval, 2)
                return _importance(e) + function - (45 if e.pitch % 12 in selected_pcs else 0)
            chosen = max(candidates, key=score)
            selected.append(chosen)
            selected_pcs.add(chosen.pitch % 12)
            candidates.remove(chosen)
        kept.extend(selected)
        removed.extend(reject(e, "chord_simplification") for e in candidates)
    return sorted(kept, key=lambda e: e.start), removed


def limit_sustained(events: list[MusicEvent], limit: int, gap: float) -> tuple[list[MusicEvent], list[dict]]:
    kept, removed, active = [], [], []
    for event in sorted(events, key=lambda e: (e.start, -_importance(e))):
        active = [i for i in active if kept[i].end > event.start]
        collisions = [i for i in active if kept[i].pitch == event.pitch]
        if collisions:
            index = collisions[0]
            previous = kept[index]
            if event.start-previous.start < gap:
                if _importance(event) <= _importance(previous):
                    removed.append(reject(event, "duplicate_or_impossible_retrigger"))
                    continue
                removed.append(reject(previous, "duplicate_replaced_by_protected_note"))
                kept[index] = event
                continue
            kept[index] = replace(previous, end=max(previous.start+.001, event.start-gap))
            active.remove(index)
        if len(active) >= limit:
            weakest = min(active, key=lambda i: _importance(kept[i]))
            if _importance(kept[weakest]) >= _importance(event):
                removed.append(reject(event, "sustained_polyphony"))
                continue
            previous = kept[weakest]
            if previous.start >= event.start-.001:
                removed.append(reject(previous, "sustained_polyphony"))
                kept[weakest] = event
                continue
            kept[weakest] = replace(previous, end=event.start,
                                    evidence={**previous.evidence, "tail_shortened_for": event.event_id})
            active.remove(weakest)
        active.append(len(kept))
        kept.append(event)
    return sorted(kept, key=lambda e: e.start), removed


def clean_drums(events: list[MusicEvent], profile: dict, beats=None) -> tuple[list[MusicEvent], list[dict]]:
    kept, removed = [], []
    by_role = defaultdict(list)
    for e in sorted(events, key=lambda e: e.start):
        by_role[e.role].append(e)
    for role, notes in by_role.items():
        previous = None
        for event in notes:
            if previous and event.start-previous.start < profile["minimum_retrigger_seconds"]:
                chosen = event if event.confidence > previous.confidence else previous
                kept[-1] = replace(chosen, pitch=profile["mapping"][role], start=min(event.start, previous.start),
                                   end=min(event.start, previous.start)+profile["hit_duration_seconds"],
                                   tags=chosen.tags | {"merged_drum_hit"})
                removed.append(reject(previous if chosen is event else event, "duplicate_drum_hit"))
                previous = kept[-1]
                continue
            if event.confidence < .36:
                removed.append(reject(event, "weak_drum_bleed"))
                continue
            previous = replace(event, pitch=profile["mapping"][role], end=event.start+profile["hit_duration_seconds"])
            kept.append(previous)
    # Shared pads and incompatible simultaneous cymbals must not double-trigger.
    final, more = limit_sustained(kept, profile["max_polyphony"], profile["minimum_retrigger_seconds"])
    return final, removed + more


def physical_fit(events: list[MusicEvent], part: str, settings: ArrangementSettings) -> tuple[list[MusicEvent], dict, list[dict]]:
    if not events:
        return [], {"range_shifted": 0, "control_changes": 0}, []
    low, high = _range(part, settings)
    original = {e.event_id: e.pitch for e in events}
    contours = [e for e in events if part == "bass" or e.role in {"MAIN_MELODY", "MELODY", "RIFF"}]
    fitted_contours = {e.event_id: e for e in fit_contour(contours, low, high)}
    fitted = [fitted_contours.get(e.event_id, e) for e in events]
    source = _to_source(fitted)
    options = playback.EnhancedPlanOptions(instrument=ENGINE_PART[part], mode="stable",
                                           unlock_tier=settings.tiers[part], mapping_method="octave",
                                           max_notes_per_chord=0, sustain_mode="off", articulation_mode="raw")
    # Reuse the existing sustained-note-aware DP and physical key map. The
    # exported timestamps stay on the audio clock; initial control lead is a
    # playback concern, not an independent offset for each instrument's MIDI.
    groups = me._group_notes_by_start(source)
    mapped = playback._enhanced_choose_group_states(groups, options)
    result, removed, changes, previous_state = [], [], 0, None
    for group, mapping in zip(groups, mapped):
        if mapping.state.page != 1:
            raise ValueError("Studio arrangement unexpectedly required a page key")
        changes += int(previous_state is not None and previous_state != mapping.state)
        previous_state = mapping.state
        for note, pitch in zip(group, mapping.pitches):
            e = fitted[note.serial]
            if pitch is None:
                removed.append(reject(e, "physical_mapping"))
                continue
            evidence = {**e.evidence, "physical_key": me.key_for_pitch(pitch, mapping.state),
                        "octave_mode": mapping.state.octave, "page": 1}
            if original[e.event_id] != pitch:
                evidence["pre_range_pitch"] = original[e.event_id]
            result.append(replace(e, pitch=pitch, evidence=evidence))
    gap = playback.TIMING_PROFILES[ENGINE_PART[part]].retrigger_gap_ms / 1000
    result, more = limit_sustained(result, settings.polyphony[part], gap)
    return result, {"range_shifted": sum(e.pitch != original[e.event_id] for e in result),
                    "control_changes": changes}, removed + more


def arrange(master: MasterSong, settings: ArrangementSettings, drum_profile: dict) -> dict:
    settings.validate()
    parts = {part: [e for e in master.events if e.source == part] for part in PARTS}
    # Use Band v4's phrase classifier for ambiguous "Other" accompaniment.
    # Explicit separated instrument stems retain ownership. No A/B alternation.
    import band_musical_sharing as band4
    other = [e for e in master.events if e.source == "other" and e.pitch is not None]
    if other:
        notes = _to_source(other)
        metadata = {n.serial: adaptive.SourceMeta(n.serial, n.start, n.pitch, n.velocity, 0, "Other accompaniment", 0, 48, "harmony") for n in notes}
        decisions = [band4._decision(phrase, metadata) for phrase in band4._segment_stream(notes)]
        states = band4._viterbi_states(decisions, ("keyboard", "guitar", "bass", "drums"))
        owners = {}
        band4._apply_decisions(decisions, states, owners, ("keyboard", "guitar", "bass", "drums"))
        for serial, targets in owners.items():
            for target in targets:
                if target != "drums":
                    parts["piano" if target == "keyboard" else target].append(other[serial])
    melody = [e for e in master.events if e.role == "MAIN_MELODY"]
    assignment = melody_assignment(melody, parts, settings)
    if assignment["part"]:
        parts[assignment["part"]].extend(melody)
    stats, removed = {}, list(master.rejected)
    for part in PARTS:
        source_count = len(parts[part])
        if part == "drums":
            selected, discarded = clean_drums(parts[part], drum_profile, master.beat_map)
            summary = {"range_shifted": 0}
        else:
            selected, discarded = simplify_chords(parts[part], settings.polyphony[part], part)
            selected, summary, dropped = physical_fit(selected, part, settings)
            discarded.extend(dropped)
        parts[part] = [replace(e, end=min(master.duration, e.end)) for e in selected if e.start < master.duration]
        removed.extend({**r, "part": part} for r in discarded)
        stats[part] = {"notes": len(parts[part]), "input_notes": source_count,
                       "main_melody": assignment["part"] == part,
                       "low_confidence_rejected": sum(r["reason"] == "low_confidence" and r["event"]["source"] == part for r in master.rejected),
                       "simplified": len(discarded), **summary}
    return {"parts": parts, "melody_assignment": assignment, "summary": stats, "removed": removed,
            "arranger_version": ARRANGER_VERSION, "drum_profile": drum_profile}
