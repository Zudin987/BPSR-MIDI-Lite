from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from statistics import median
from typing import Any, Iterable, Literal

import band_arranger
import midi_engine as me
import playback_adaptive as adaptive


# Arrangement v4 replaces the v3 post-split sharing rule with a deterministic
# phrase-aware ownership model. Every client derives the same result locally.
BAND_SHARED_ARRANGEMENT_VERSION = 4

OwnerState = Literal["keyboard", "guitar", "shared", "bass", "drums"]

_DRUM_NAME_WORDS = (
    "drum",
    "drums",
    "drumkit",
    "drum kit",
    "percussion",
    "perc.",
    "perc ",
    "kick",
    "snare",
    "hi-hat",
    "hihat",
    "hi hat",
    "cymbal",
    "tom tom",
    "toms",
)
_GUITAR_NAME_WORDS = (
    "guitar",
    "acoustic guitar",
    "electric guitar",
)
_KEYBOARD_ONLY_NAME_WORDS = (
    "melody",
    "lead",
    "solo",
    "vocal",
    "voice",
    "soprano",
    "theme",
)
_BASS_NAME_WORDS = (
    "bass",
    "contrabass",
    "bassline",
    "low end",
)
_HARMONY_NAME_WORDS = (
    "chord",
    "harmony",
    "accomp",
    "accompaniment",
    "pad",
    "strings",
    "piano",
    "keys",
    "keyboard",
    "rhythm",
)

# Broad no-page safe ranges used only as an arrangement preference. Final
# playback still applies the player's real BPSR unlock/mapping profile.
_KEYBOARD_SAFE_RANGE = (36, 95)  # C2-B6
_GUITAR_SAFE_RANGE = (40, 86)  # E2-D6
_PHRASE_REST_SECONDS = 0.60
_PHRASE_MAX_SECONDS = 4.5

_original_split: Any = None
_original_role_from_source: Any = None


@dataclass(frozen=True, slots=True)
class PhraseFeatures:
    median_pitch: float
    pitch_span: int
    chord_ratio: float
    density: float
    short_ratio: float
    unique_ratio: float
    gm_drum_ratio: float
    common_drum_ratio: float
    median_duration: float
    keyboard_fit: float
    guitar_fit: float
    melodicness: float


@dataclass(frozen=True, slots=True)
class PhraseDecision:
    notes: tuple[me.SourceNote, ...]
    features: PhraseFeatures
    scores: dict[str, float]
    lock: OwnerState | None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _name_has(name: str, words: tuple[str, ...]) -> bool:
    folded = str(name).casefold()
    return any(word in folded for word in words)


def enhanced_role_from_source(track_name: str, channel: int, program: int) -> adaptive.Role:
    """Recognize authored percussion even when an exporter did not use channel 10."""
    if int(channel) == 9 or _name_has(track_name, _DRUM_NAME_WORDS):
        return "drums"
    assert _original_role_from_source is not None
    return _original_role_from_source(track_name, channel, program)


def _stream_key(meta: adaptive.SourceMeta | None) -> tuple[int, int, int]:
    if meta is None:
        return (-1, -1, -1)
    return (int(meta.track_index), int(meta.channel), int(meta.program))


def _attack_groups(notes: Iterable[me.SourceNote]) -> list[list[me.SourceNote]]:
    groups: list[list[me.SourceNote]] = []
    anchor: float | None = None
    for note in sorted(notes, key=lambda item: (item.start, item.serial)):
        if anchor is None or note.start - anchor > me.CHORD_ONSET_WINDOW_SECONDS:
            groups.append([])
            anchor = note.start
        groups[-1].append(note)
    return groups


def _segment_stream(notes: list[me.SourceNote]) -> list[list[me.SourceNote]]:
    """Split a stream at rests and conservative phrase-length boundaries."""
    ordered = sorted(notes, key=lambda note: (note.start, note.serial))
    if not ordered:
        return []

    phrases: list[list[me.SourceNote]] = []
    current: list[me.SourceNote] = []
    phrase_start = ordered[0].start
    previous_end = ordered[0].start
    previous_start = ordered[0].start

    for note in ordered:
        rest = note.start - previous_end
        elapsed = note.start - phrase_start
        same_attack = abs(note.start - previous_start) <= me.CHORD_ONSET_WINDOW_SECONDS
        should_break = bool(
            current
            and not same_attack
            and (
                rest >= _PHRASE_REST_SECONDS
                or (elapsed >= _PHRASE_MAX_SECONDS and len(current) >= 4)
            )
        )
        if should_break:
            phrases.append(current)
            current = []
            phrase_start = note.start
        current.append(note)
        previous_end = max(previous_end, note.end)
        previous_start = note.start

    if current:
        phrases.append(current)
    return phrases


def _fit_score(pitches: list[int], low: int, high: int) -> float:
    if not pitches:
        return 0.0
    direct = sum(low <= pitch <= high for pitch in pitches) / len(pitches)
    displacement = 0.0
    for pitch in pitches:
        if low <= pitch <= high:
            continue
        candidates = [value for value in range(low, high + 1) if value % 12 == pitch % 12]
        if candidates:
            displacement += min(abs(value - pitch) for value in candidates)
        else:
            displacement += min(abs(pitch - low), abs(pitch - high))
    average_displacement = displacement / len(pitches)
    octave_fit = 1.0 - min(1.0, average_displacement / 24.0)
    return _clamp(direct * 0.72 + octave_fit * 0.28)


def _features(notes: list[me.SourceNote]) -> PhraseFeatures:
    pitches = [int(note.pitch) for note in notes]
    durations = [max(0.001, float(note.end - note.start)) for note in notes]
    groups = _attack_groups(notes)
    chord_notes = sum(len(group) for group in groups if len(group) > 1)
    chord_ratio = chord_notes / max(1, len(notes))
    start = min(note.start for note in notes)
    end = max(note.end for note in notes)
    density = len(notes) / max(0.25, end - start)
    short_ratio = sum(duration <= 0.18 for duration in durations) / len(durations)
    unique = len(set(pitches))
    unique_ratio = unique / len(pitches)
    gm_drum_ratio = sum(35 <= pitch <= 81 for pitch in pitches) / len(pitches)
    # Most useful GM kit hits (kick/snare/toms/hats/cymbals) cluster in 35-59.
    # This narrower signal sharply reduces false positives on fast piano lines.
    common_drum_ratio = sum(35 <= pitch <= 59 for pitch in pitches) / len(pitches)
    melodicness = _clamp(
        (1.0 - chord_ratio)
        * min(1.0, unique_ratio * 1.8)
        * (0.55 + 0.45 * (1.0 - short_ratio))
    )
    return PhraseFeatures(
        median_pitch=float(median(pitches)),
        pitch_span=max(pitches) - min(pitches),
        chord_ratio=chord_ratio,
        density=density,
        short_ratio=short_ratio,
        unique_ratio=unique_ratio,
        gm_drum_ratio=gm_drum_ratio,
        common_drum_ratio=common_drum_ratio,
        median_duration=float(median(durations)),
        keyboard_fit=_fit_score(pitches, *_KEYBOARD_SAFE_RANGE),
        guitar_fit=_fit_score(pitches, *_GUITAR_SAFE_RANGE),
        melodicness=melodicness,
    )


def _meta_lock(meta: adaptive.SourceMeta | None) -> OwnerState | None:
    if meta is None:
        return None
    name = str(meta.track_name)
    program = int(meta.program)
    if meta.channel == 9 or meta.role == "drums" or _name_has(name, _DRUM_NAME_WORDS):
        return "drums"
    if meta.role == "bass" or 32 <= program <= 39 or _name_has(name, _BASS_NAME_WORDS):
        return "bass"
    if 24 <= program <= 31 or _name_has(name, _GUITAR_NAME_WORDS):
        return "guitar"
    if meta.role == "melody" or 80 <= program <= 87 or _name_has(name, _KEYBOARD_ONLY_NAME_WORDS):
        return "keyboard"
    return None


def _phrase_lock(
    notes: list[me.SourceNote], metadata: dict[int, adaptive.SourceMeta]
) -> OwnerState | None:
    locks = [
        lock
        for note in notes
        if (lock := _meta_lock(metadata.get(note.serial))) is not None
    ]
    if not locks:
        return None
    counts = Counter(locks)
    state, amount = counts.most_common(1)[0]
    if amount >= max(1, int(len(notes) * 0.60 + 0.999)):
        return state
    return None


def _role_ratios(
    notes: list[me.SourceNote], metadata: dict[int, adaptive.SourceMeta]
) -> dict[str, float]:
    counts = Counter(
        str(metadata[note.serial].role)
        for note in notes
        if note.serial in metadata
    )
    total = max(1, sum(counts.values()))
    return {
        name: counts.get(name, 0) / total
        for name in ("melody", "harmony", "bass", "drums", "unknown")
    }


def _phrase_scores(
    notes: list[me.SourceNote],
    metadata: dict[int, adaptive.SourceMeta],
    features: PhraseFeatures,
) -> dict[str, float]:
    roles = _role_ratios(notes, metadata)
    metas = [metadata.get(note.serial) for note in notes]
    names = " ".join(str(meta.track_name) for meta in metas if meta is not None)
    programs = [int(meta.program) for meta in metas if meta is not None]

    keyboard = 0.30
    guitar = 0.28
    bass = 0.04
    drums = 0.01

    keyboard += roles["melody"] * 0.62
    guitar += roles["harmony"] * 0.34
    keyboard += roles["harmony"] * 0.24
    bass += roles["bass"] * 0.90
    drums += roles["drums"] * 0.95

    pitched_name = False
    if _name_has(names, _HARMONY_NAME_WORDS):
        keyboard += 0.13
        guitar += 0.17
        pitched_name = True
    if _name_has(names, _GUITAR_NAME_WORDS):
        guitar += 0.55
        pitched_name = True
    if _name_has(names, _KEYBOARD_ONLY_NAME_WORDS):
        keyboard += 0.55
        pitched_name = True
    if _name_has(names, _BASS_NAME_WORDS):
        bass += 0.68
        pitched_name = True
    if _name_has(names, _DRUM_NAME_WORDS):
        drums += 0.78
        pitched_name = False

    if programs:
        guitar_program_ratio = sum(24 <= program <= 31 for program in programs) / len(programs)
        bass_program_ratio = sum(32 <= program <= 39 for program in programs) / len(programs)
        lead_program_ratio = sum(80 <= program <= 87 for program in programs) / len(programs)
        guitar += guitar_program_ratio * 0.55
        bass += bass_program_ratio * 0.72
        keyboard += lead_program_ratio * 0.52

    keyboard += features.chord_ratio * 0.13
    guitar += features.chord_ratio * 0.17
    keyboard += features.melodicness * 0.17
    if features.median_pitch >= 68.0:
        keyboard += 0.08
    if features.median_pitch <= 50.0:
        bass += 0.16
        guitar += 0.05

    # BPSR playability is part of the preference score, but hard physical
    # constraints remain in the normal playback mapper.
    keyboard += features.keyboard_fit * 0.12
    guitar += features.guitar_fit * 0.12

    # Rescue badly-exported percussion only with several independent signals.
    # A clearly named pitched track is never converted by this heuristic.
    repeated_pitch_signal = _clamp((0.55 - features.unique_ratio) / 0.45)
    rhythmic_signal = (
        not pitched_name
        and features.short_ratio >= 0.78
        and features.density >= 4.5
        and features.gm_drum_ratio >= 0.85
        and features.common_drum_ratio >= 0.65
        and repeated_pitch_signal >= 0.25
    )
    if rhythmic_signal:
        drums += (
            0.30
            + features.short_ratio * 0.18
            + repeated_pitch_signal * 0.22
            + min(0.12, features.chord_ratio * 0.16)
        )
    if pitched_name:
        drums -= 0.18
    if features.median_duration >= 0.45:
        drums -= 0.22
    if features.melodicness >= 0.68:
        drums -= 0.20

    return {
        "keyboard": _clamp(keyboard),
        "guitar": _clamp(guitar),
        "bass": _clamp(bass),
        "drums": _clamp(drums),
    }


def _decision(
    notes: list[me.SourceNote], metadata: dict[int, adaptive.SourceMeta]
) -> PhraseDecision:
    features = _features(notes)
    return PhraseDecision(
        notes=tuple(notes),
        features=features,
        scores=_phrase_scores(notes, metadata, features),
        lock=_phrase_lock(notes, metadata),
    )


def _emission(decision: PhraseDecision, state: OwnerState) -> float:
    if decision.lock is not None:
        return 3.0 if state == decision.lock else -3.0

    scores = decision.scores
    if state == "shared":
        keyboard = scores["keyboard"]
        guitar = scores["guitar"]
        if min(keyboard, guitar) < 0.43 or abs(keyboard - guitar) > 0.28:
            return -0.40
        return (
            min(keyboard, guitar)
            + 0.12
            + decision.features.chord_ratio * 0.10
            - decision.features.melodicness * 0.10
        )
    return float(scores[state])


def _transition(previous: OwnerState, current: OwnerState) -> float:
    if previous == current:
        return 0.16
    if "shared" in {previous, current} and {previous, current} & {"keyboard", "guitar"}:
        return 0.05
    if {previous, current} <= {"keyboard", "guitar"}:
        return -0.07
    return -0.18


def _allowed_states(active_parts: tuple[band_arranger.BandPart, ...]) -> tuple[OwnerState, ...]:
    # Classification remains independent of who is present. A missing authored
    # role is redirected only after classification, preserving musical intent.
    states: list[OwnerState] = ["keyboard", "guitar"]
    if "keyboard" in active_parts and "guitar" in active_parts:
        states.append("shared")
    states.extend(("bass", "drums"))
    return tuple(states)


def _viterbi_states(
    decisions: list[PhraseDecision],
    active_parts: tuple[band_arranger.BandPart, ...],
) -> list[OwnerState]:
    if not decisions:
        return []
    states = _allowed_states(active_parts)
    rows: list[dict[OwnerState, tuple[float, OwnerState | None]]] = []

    for index, decision in enumerate(decisions):
        row: dict[OwnerState, tuple[float, OwnerState | None]] = {}
        for state in states:
            emission = _emission(decision, state)
            if index == 0:
                row[state] = (emission, None)
                continue
            best: tuple[float, OwnerState | None] | None = None
            for previous, (previous_score, _) in rows[index - 1].items():
                score = previous_score + _transition(previous, state) + emission
                if best is None or score > best[0]:
                    best = (score, previous)
            if best is not None:
                row[state] = best
        rows.append(row)

    current = max(rows[-1], key=lambda state: rows[-1][state][0])
    result = [current]
    for index in range(len(rows) - 1, 0, -1):
        previous = rows[index][result[-1]][1]
        if previous is None:
            break
        result.append(previous)
    result.reverse()
    return result


def _redirect_state(
    state: OwnerState,
    active_parts: tuple[band_arranger.BandPart, ...],
) -> set[band_arranger.BandPart]:
    if state == "shared":
        return {part for part in ("keyboard", "guitar") if part in active_parts}
    if state in active_parts:
        return {state}  # type: ignore[return-value]
    target = band_arranger._redirect_inactive_part(state, active_parts)  # noqa: SLF001
    return {target} if target is not None else set()


def _assign_shared_phrase(
    notes: Iterable[me.SourceNote],
    owners: dict[int, set[band_arranger.BandPart]],
) -> None:
    """Share support while keeping dense piano chords reasonable on Guitar."""
    for group in _attack_groups(notes):
        guitar_notes = group if len(group) <= 3 else sorted(
            group,
            key=lambda note: (note.pitch, note.velocity, -note.serial),
            reverse=True,
        )[:3]
        guitar_serials = {note.serial for note in guitar_notes}
        for note in group:
            owner_set: set[band_arranger.BandPart] = {"keyboard"}
            if note.serial in guitar_serials:
                owner_set.add("guitar")
            owners[note.serial] = owner_set


def _apply_decisions(
    decisions: list[PhraseDecision],
    states: list[OwnerState],
    owners: dict[int, set[band_arranger.BandPart]],
    active_parts: tuple[band_arranger.BandPart, ...],
) -> None:
    for decision, state in zip(decisions, states):
        if state == "shared" and "keyboard" in active_parts and "guitar" in active_parts:
            _assign_shared_phrase(decision.notes, owners)
            continue
        target = _redirect_state(state, active_parts)
        for note in decision.notes:
            owners[note.serial] = set(target)


def _base_owner_map(
    split: dict[band_arranger.BandPart, list[me.SourceNote]],
) -> dict[int, set[band_arranger.BandPart]]:
    owners: dict[int, set[band_arranger.BandPart]] = defaultdict(set)
    for part, part_notes in split.items():
        for note in part_notes:
            owners[note.serial].add(part)
    return owners


def split_band_notes_shared(
    notes: list[me.SourceNote],
    metadata: dict[int, adaptive.SourceMeta],
    active_parts: Iterable[str] | None = None,
) -> dict[band_arranger.BandPart, list[me.SourceNote]]:
    """Phrase-aware Band ownership with confidence, continuity and safe sharing.

    The v2 deterministic split remains the safety baseline. v4 revisits material
    routed to Piano/Guitar and can rescue high-confidence Bass/Drum material.
    """
    assert _original_split is not None
    active = band_arranger.normalize_active_parts(active_parts)
    baseline = _original_split(notes, metadata, active)
    if not notes:
        return baseline

    owners = _base_owner_map(baseline)
    candidates_by_stream: dict[tuple[int, int, int], list[me.SourceNote]] = defaultdict(list)

    for note in notes:
        current = owners.get(note.serial, set())
        meta = metadata.get(note.serial)
        lock = _meta_lock(meta)
        if current & {"keyboard", "guitar"} or (not current and lock in {"bass", "drums"}):
            candidates_by_stream[_stream_key(meta)].append(note)

    for stream_notes in candidates_by_stream.values():
        phrases = _segment_stream(stream_notes)
        decisions = [_decision(phrase, metadata) for phrase in phrases]
        states = _viterbi_states(decisions, active)
        _apply_decisions(decisions, states, owners, active)

    result: dict[band_arranger.BandPart, list[me.SourceNote]] = {
        part: [] for part in band_arranger.PART_ORDER
    }
    for note in notes:
        for part in band_arranger.PART_ORDER:
            if part not in owners.get(note.serial, set()):
                continue
            if part == "drums":
                result[part].append(replace(note, pitch=band_arranger.normalize_drum_pitch(note.pitch)))
            else:
                result[part].append(note)

    for part in band_arranger.PART_ORDER:
        result[part].sort(key=lambda note: (note.start, note.serial))
    return result


def install_shared_band_arrangement(app_module: Any) -> None:
    global _original_split, _original_role_from_source
    if getattr(app_module, "_shared_band_arrangement_installed", False):
        return
    if not getattr(app_module, "_band_arranger_installed", False):
        raise RuntimeError("Band arranger must be installed before shared Band arrangement.")

    _original_split = band_arranger.split_band_notes
    _original_role_from_source = adaptive._role_from_source

    adaptive._role_from_source = enhanced_role_from_source
    band_arranger.split_band_notes = split_band_notes_shared
    band_arranger.BAND_ARRANGEMENT_VERSION = BAND_SHARED_ARRANGEMENT_VERSION

    app_module._shared_band_arrangement_installed = True
