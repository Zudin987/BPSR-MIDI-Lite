"""Final BPSR-audibility reduction for Studio arrangements.

A desktop MIDI preview can rely on velocity and a normal synth envelope to keep
accompaniment behind the melody. BPSR is driven by digital keyboard presses, so
those dynamics are not a safe mixing tool: every retained accompaniment note can
become prominent in-game. This pass therefore protects musical foreground while
reducing only the material most likely to turn into audible mud.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import replace
from typing import Any

from .fusion import reject
from .music import MusicEvent

PROTECTED_ROLES = {"MAIN_MELODY", "MELODY", "RIFF", "BASS"}
ACCOMPANIMENT_ROLES = {"HARMONY", "RHYTHM", "DECORATION"}
_SOFT_BACKGROUND_ROLES = {"HARMONY", "DECORATION"}
_ROLE_WEIGHT = {
    "MAIN_MELODY": 1000.0,
    "MELODY": 850.0,
    "RIFF": 760.0,
    "BASS": 680.0,
    "RHYTHM": 560.0,
    "HARMONY": 360.0,
    "DECORATION": 100.0,
}


def choose_other_phrase_owner(decision: Any, state: str) -> str:
    """Collapse Band-v4's shared Piano+Guitar state to one Studio owner.

    Studio exports already have dedicated parts. Duplicating the same ambiguous
    accompaniment onto Piano and Guitar is useful for generic MIDI sharing but
    makes a real BPSR band much louder/denser because both players reproduce it.
    Chordal accompaniment slightly prefers Guitar; melodic material prefers Piano.
    """
    if state != "shared":
        return state
    scores = getattr(decision, "scores", {}) or {}
    features = getattr(decision, "features", None)
    keyboard = float(scores.get("keyboard", 0.0))
    guitar = float(scores.get("guitar", 0.0))
    chord_ratio = float(getattr(features, "chord_ratio", 0.0))
    melodicness = float(getattr(features, "melodicness", 0.0))
    if chord_ratio >= 0.30 and melodicness < 0.72 and guitar >= keyboard - 0.08:
        return "guitar"
    return "keyboard"


def _groups(events: list[MusicEvent], window: float = 0.035) -> list[list[MusicEvent]]:
    groups: list[list[MusicEvent]] = []
    anchor: float | None = None
    for event in sorted(events, key=lambda item: (item.start, item.event_id, item.pitch or -1)):
        if anchor is None or event.start - anchor > window:
            groups.append([])
            anchor = event.start
        groups[-1].append(event)
    return groups


def _local_attack_rate(anchors: list[float], value: float) -> float:
    if not anchors:
        return 0.0
    # One second centered window is stable enough not to overreact to one chord.
    left = bisect_left(anchors, value - 0.50)
    right = bisect_right(anchors, value + 0.50)
    return float(right - left)


def _dynamic_chord_limit(part: str, requested: int, attack_rate: float) -> int:
    """Lower accompaniment chord width gradually as BPSR attack pressure rises."""
    requested = max(1, int(requested))
    if part == "piano":
        if attack_rate >= 9.0:
            return min(requested, 2)
        if attack_rate >= 5.5:
            return min(requested, 3)
    elif part == "guitar" and attack_rate >= 5.5:
        return min(requested, 2)
    return requested


def _score(event: MusicEvent) -> float:
    # Velocity is only a source-mix hint here. A low-velocity MIDI note cannot be
    # trusted to remain quiet once converted to a BPSR keyboard press.
    return (
        _ROLE_WEIGHT.get(event.role, 250.0)
        + float(event.confidence) * 35.0
        + float(event.velocity) * 0.12
    )


def _select_dense_group(group: list[MusicEvent], limit: int) -> tuple[list[MusicEvent], list[MusicEvent]]:
    if len(group) <= limit:
        return list(group), []
    protected = sorted(
        (event for event in group if event.role in PROTECTED_ROLES),
        key=_score,
        reverse=True,
    )
    # Never remove a foreground line just to satisfy an accompaniment budget.
    selected = list(protected)
    remaining = [event for event in group if event not in selected]
    selected_pcs = {event.pitch % 12 for event in selected if event.pitch is not None}
    while remaining and len(selected) < max(limit, len(protected)):
        def candidate_score(event: MusicEvent) -> float:
            repeated_pc = event.pitch is not None and event.pitch % 12 in selected_pcs
            return _score(event) - (30.0 if repeated_pc else 0.0)

        chosen = max(remaining, key=candidate_score)
        selected.append(chosen)
        if chosen.pitch is not None:
            selected_pcs.add(chosen.pitch % 12)
        remaining.remove(chosen)
    return selected, remaining


def _trim_background_detail(
    selected: list[MusicEvent], attack_rate: float
) -> tuple[list[MusicEvent], list[MusicEvent]]:
    """Drop expendable decoration before removing useful harmony/rhythm notes."""
    if attack_rate < 6.5 or len(selected) <= 1:
        return selected, []
    if any(event.role in PROTECTED_ROLES for event in selected):
        return selected, []

    # At moderate density, decoration is the first thing a digital-key arranger
    # can sacrifice. Keep at least one note so the accompaniment pulse remains.
    decorations = sorted(
        (event for event in selected if event.role == "DECORATION"),
        key=_score,
    )
    if not decorations:
        return selected, []
    removable = decorations[: max(0, len(selected) - 1)]
    removed_ids = {id(event) for event in removable}
    return [event for event in selected if id(event) not in removed_ids], removable


def _minimum_background_gap(part: str, attack_rate: float) -> float | None:
    """Return a conservative minimum spacing for soft background-only attacks."""
    if part == "guitar":
        if attack_rate >= 13.0:
            return 0.160
        if attack_rate >= 10.0:
            return 0.140
        if attack_rate >= 8.0:
            return 0.115
    else:
        if attack_rate >= 13.0:
            return 0.150
        if attack_rate >= 10.0:
            return 0.125
        if attack_rate >= 8.0:
            return 0.105
    return None


def clarify_part(
    events: list[MusicEvent],
    part: str,
    requested_polyphony: int,
) -> tuple[list[MusicEvent], list[dict], dict[str, int]]:
    """Make a fitted Studio part sound clearer through BPSR's digital input.

    Sparse passages are intentionally left alone. Dense accompaniment gets a
    smaller instantaneous chord budget, expendable decoration is removed first,
    very close low-priority re-attacks may be removed, and accompaniment tails
    are shortened before the next attack.
    """
    if part not in {"piano", "guitar"} or not events:
        return list(events), [], {"ingame_clarity_removed": 0, "ingame_tails_shortened": 0}

    groups = _groups(events)
    anchors = [min(event.start for event in group) for group in groups]
    selected_groups: list[tuple[float, list[MusicEvent], float]] = []
    removed: list[dict] = []
    removed_count = 0
    last_soft_background_anchor: float | None = None

    for anchor, group in zip(anchors, groups):
        rate = _local_attack_rate(anchors, anchor)
        limit = _dynamic_chord_limit(part, requested_polyphony, rate)
        selected, discarded = _select_dense_group(group, limit)
        for event in discarded:
            removed.append(reject(event, "ingame_dense_chord"))
        removed_count += len(discarded)

        selected, detail_removed = _trim_background_detail(selected, rate)
        for event in detail_removed:
            removed.append(reject(event, "ingame_background_detail"))
        removed_count += len(detail_removed)

        has_foreground = any(event.role in PROTECTED_ROLES for event in selected)
        only_soft_background = bool(selected) and all(
            event.role in _SOFT_BACKGROUND_ROLES for event in selected
        )
        max_velocity = max((event.velocity for event in selected), default=127)
        min_gap = _minimum_background_gap(part, rate)
        if (
            min_gap is not None
            and not has_foreground
            and only_soft_background
            and max_velocity <= 105
        ):
            if (
                last_soft_background_anchor is not None
                and anchor - last_soft_background_anchor < min_gap
            ):
                for event in selected:
                    removed.append(reject(event, "ingame_accompaniment_attack_pressure"))
                removed_count += len(selected)
                continue
            last_soft_background_anchor = anchor
        elif selected and not has_foreground and only_soft_background:
            last_soft_background_anchor = anchor
        selected_groups.append((anchor, selected, rate))

    kept: list[MusicEvent] = []
    shortened = 0
    kept_anchors = [item[0] for item in selected_groups]
    for index, (anchor, group, rate) in enumerate(selected_groups):
        next_anchor = kept_anchors[index + 1] if index + 1 < len(kept_anchors) else None
        for event in group:
            if event.role in PROTECTED_ROLES or event.role not in ACCOMPANIMENT_ROLES:
                kept.append(event)
                continue
            max_tail = None
            if rate >= 9.0:
                max_tail = 0.14
            elif rate >= 7.5:
                max_tail = 0.18
            elif rate >= 5.5:
                max_tail = 0.24
            if max_tail is None:
                kept.append(event)
                continue
            end = min(event.end, event.start + max_tail)
            if next_anchor is not None:
                end = min(end, max(event.start + 0.055, next_anchor - 0.018))
            end = max(event.start + 0.045, end)
            if end < event.end - 0.004:
                shortened += 1
                kept.append(replace(
                    event,
                    end=end,
                    tags=event.tags | {"ingame_clarity_gated"},
                    evidence={
                        **event.evidence,
                        "ingame_clarity": {
                            "attack_rate": round(rate, 3),
                            "original_end": event.end,
                            "reason": "digital_input_velocity_collapse",
                        },
                    },
                ))
            else:
                kept.append(event)

    kept.sort(key=lambda event: (event.start, event.event_id, event.pitch or -1))
    return kept, removed, {
        "ingame_clarity_removed": removed_count,
        "ingame_tails_shortened": shortened,
    }
