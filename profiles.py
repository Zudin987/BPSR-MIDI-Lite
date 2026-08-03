from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ProfileCode = Literal["tier1", "tier2", "tier3", "custom"]


@dataclass(frozen=True, slots=True)
class PlaybackProfile:
    code: ProfileCode
    label: str
    summary: str
    mode: str
    unlock_tier: str
    mapping: str
    chord_limit: int
    speed: int = 85
    note_length: int = 150
    minimum_note: int = 120
    page_delay: int = 220
    modifier_lead: int = 55
    use_pedal: bool = False
    ignore_percussion: bool = True

    def settings(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "unlock_tier": self.unlock_tier,
            "mapping": self.mapping,
            "chord_limit": self.chord_limit,
            "speed": self.speed,
            "length": self.note_length,
            "minimum_note": self.minimum_note,
            "page_delay": self.page_delay,
            "modifier_lead": self.modifier_lead,
            "pedal": self.use_pedal,
            "ignore_percussion": self.ignore_percussion,
        }


FIXED_PROFILES: dict[str, PlaybackProfile] = {
    "tier1": PlaybackProfile(
        code="tier1",
        label="Tier 1 — C3–B4 (Beginner)",
        summary=(
            "For newly unlocked instruments. Uses only C3–B4, never uses Ctrl, Shift, < or >, "
            "auto-transposes the song, and keeps bass + melody for clean playback."
        ),
        mode="stable",
        unlock_tier="tier1",
        mapping="transpose",
        chord_limit=2,
        speed=85,
        note_length=150,
        minimum_note=130,
    ),
    "tier2": PlaybackProfile(
        code="tier2",
        label="Tier 2 — C3–B6",
        summary=(
            "Uses C3–B6 with Default + Shift. It never presses < or > and keeps bass, melody, "
            "and one harmony note in dense chords."
        ),
        mode="stable",
        unlock_tier="tier2",
        mapping="octave",
        chord_limit=3,
    ),
    "tier3": PlaybackProfile(
        code="tier3",
        label="Tier 3 — C2–B6 (Recommended)",
        summary=(
            "Uses the full safe middle-page range C2–B6 with Ctrl / Default / Shift. "
            "It guarantees no < or > page presses and keeps all chord notes."
        ),
        mode="stable",
        unlock_tier="tier3",
        mapping="octave",
        chord_limit=0,
    ),
}

PROFILE_LABELS: dict[str, str] = {
    profile.label: code for code, profile in FIXED_PROFILES.items()
}
PROFILE_LABELS["Custom — advanced / full range"] = "custom"
PROFILE_LABELS_REVERSE = {code: label for label, code in PROFILE_LABELS.items()}


def get_fixed_profile(code: str) -> PlaybackProfile:
    try:
        return FIXED_PROFILES[code]
    except KeyError as exc:
        raise ValueError(f"Unknown fixed profile: {code}") from exc


def allowed_modes_for_unlock(unlock_tier: str) -> tuple[str, ...]:
    """Return meaningful modes for a Custom unlock range.

    Tier 1, Tier 2 and Tier 3 are all fixed to the middle keyboard page. Full
    range solo is only useful for the Custom A0–C8 range, where < / > page
    switching is available.
    """
    if unlock_tier in {"tier1", "tier2", "tier3"}:
        return ("stable", "ensemble")
    return ("stable", "full", "ensemble")
