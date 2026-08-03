from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class SuitabilityPlan(Protocol):
    note_count: int
    duration: float
    source_note_count: int
    source_track_count: int
    source_percussion_notes: int
    max_source_chord: int
    max_planned_chord: int
    folded_notes: int
    skipped_notes: int
    chord_removed_notes: int
    page_switches: int


@dataclass(frozen=True, slots=True)
class SuitabilityResult:
    code: str
    label: str
    summary: str
    score: int
    notes_per_second: float
    changed_ratio: float
    reasons: tuple[str, ...]


def evaluate_song_suitability(plan: SuitabilityPlan) -> SuitabilityResult:
    """Estimate how naturally a MIDI should translate to the selected profile.

    This is intentionally a simple, explainable heuristic rather than a music-
    theory judgement. It focuses on density, chord size, remapping/filtering,
    tracks, percussion, and page-switch pressure.
    """

    duration = max(float(plan.duration), 0.001)
    source_count = max(int(plan.source_note_count), 1)
    notes_per_second = float(plan.note_count) / duration
    changed_notes = min(
        source_count,
        max(0, int(plan.folded_notes))
        + max(0, int(plan.skipped_notes))
        + max(0, int(plan.chord_removed_notes)),
    )
    changed_ratio = changed_notes / source_count
    page_rate = float(plan.page_switches) / max(duration / 60.0, 0.001)

    score = 0
    reasons: list[str] = []

    if notes_per_second >= 10.0:
        score += 3
        reasons.append(f"very fast note density ({notes_per_second:.1f} notes/sec)")
    elif notes_per_second >= 6.0:
        score += 2
        reasons.append(f"fast note density ({notes_per_second:.1f} notes/sec)")
    elif notes_per_second >= 3.5:
        score += 1
        reasons.append(f"moderate note density ({notes_per_second:.1f} notes/sec)")

    max_chord = max(int(plan.max_source_chord), int(plan.max_planned_chord))
    if max_chord >= 12:
        score += 3
        reasons.append(f"very large chords (up to {max_chord} notes together)")
    elif max_chord >= 7:
        score += 2
        reasons.append(f"large chords (up to {max_chord} notes together)")
    elif max_chord >= 4:
        score += 1
        reasons.append(f"some {max_chord}-note chords")

    if changed_ratio >= 0.50:
        score += 3
        reasons.append(f"{changed_ratio:.0%} of notes need remapping or removal")
    elif changed_ratio >= 0.25:
        score += 2
        reasons.append(f"{changed_ratio:.0%} of notes need remapping or removal")
    elif changed_ratio >= 0.10:
        score += 1
        reasons.append(f"{changed_ratio:.0%} of notes need remapping or removal")

    if int(plan.source_track_count) >= 10:
        score += 2
        reasons.append(f"many MIDI tracks ({plan.source_track_count})")
    elif int(plan.source_track_count) >= 5:
        score += 1
        reasons.append(f"multiple MIDI tracks ({plan.source_track_count})")

    percussion = max(0, int(plan.source_percussion_notes))
    if percussion >= max(250, round(source_count * 0.35)):
        score += 1
        reasons.append(f"drum-heavy source ({percussion} percussion notes)")

    if page_rate >= 20.0:
        score += 2
        reasons.append(f"frequent page switching ({page_rate:.1f}/min)")
    elif page_rate >= 8.0:
        score += 1
        reasons.append(f"some page switching ({page_rate:.1f}/min)")

    forced_complex = (
        notes_per_second >= 12.0
        or max_chord >= 14
        or changed_ratio >= 0.60
    )

    if forced_complex or score >= 7:
        return SuitabilityResult(
            code="complex",
            label="Very complex",
            summary="Likely to sound messy; find a simpler piano, melody, or solo version.",
            score=score,
            notes_per_second=notes_per_second,
            changed_ratio=changed_ratio,
            reasons=tuple(reasons),
        )
    if score >= 3:
        return SuitabilityResult(
            code="busy",
            label="Busy",
            summary="May sound crowded in-game, but it can still be worth trying.",
            score=score,
            notes_per_second=notes_per_second,
            changed_ratio=changed_ratio,
            reasons=tuple(reasons),
        )
    return SuitabilityResult(
        code="good",
        label="Good fit",
        summary="Should translate cleanly with the selected instrument and profile.",
        score=score,
        notes_per_second=notes_per_second,
        changed_ratio=changed_ratio,
        reasons=tuple(reasons),
    )
