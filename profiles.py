from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


InstrumentCode = Literal["keyboard", "guitar", "bass"]
ProfileCode = Literal["tier1", "tier2", "tier3", "custom"]

INSTRUMENT_LABELS: dict[str, InstrumentCode] = {
    "Keyboard": "keyboard",
    "Guitar": "guitar",
    "Bass": "bass",
}
INSTRUMENT_LABELS_REVERSE = {code: label for label, code in INSTRUMENT_LABELS.items()}


@dataclass(frozen=True, slots=True)
class PlaybackProfile:
    instrument: InstrumentCode
    code: str
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


# The labels and summaries below are deliberately beginner-facing. The actual
# planner settings are unchanged from the established profiles.
FIXED_PROFILES: dict[InstrumentCode, dict[str, PlaybackProfile]] = {
    "keyboard": {
        "tier1": PlaybackProfile(
            instrument="keyboard", code="tier1", label="Basic — C3 to B4",
            summary="For the first Keyboard unlock. The app automatically fits larger songs into this range.",
            mode="stable", unlock_tier="tier1", mapping="transpose", chord_limit=2,
            minimum_note=130,
        ),
        "tier2": PlaybackProfile(
            instrument="keyboard", code="tier2", label="Expanded — C3 to B6",
            summary="For the second Keyboard unlock. Uses your extra high notes automatically and stays on one page.",
            mode="stable", unlock_tier="tier2", mapping="octave", chord_limit=3,
        ),
        "tier3": PlaybackProfile(
            instrument="keyboard", code="tier3", label="Full safe range — C2 to B6 (Recommended)",
            summary="Best normal Keyboard choice. Uses the full safe range automatically without changing pages.",
            mode="stable", unlock_tier="tier3", mapping="octave", chord_limit=0,
        ),
    },
    "guitar": {
        "tier1": PlaybackProfile(
            instrument="guitar", code="tier1", label="Basic — C3 to B4",
            summary="For the first Guitar unlock. The app automatically fits larger songs into this range.",
            mode="stable", unlock_tier="tier1", mapping="transpose", chord_limit=2,
            minimum_note=130,
        ),
        "tier2": PlaybackProfile(
            instrument="guitar", code="tier2", label="Expanded — E2 to B4",
            summary="For the second Guitar unlock. Low notes are handled automatically and the app stays on one page.",
            mode="stable", unlock_tier="tier2", mapping="octave", chord_limit=3,
        ),
        "tier3": PlaybackProfile(
            instrument="guitar", code="tier3", label="Full safe range — E2 to D6 (Recommended)",
            summary="Best normal Guitar choice. Uses the full safe range automatically without changing pages.",
            mode="stable", unlock_tier="tier3", mapping="octave", chord_limit=0,
        ),
    },
    "bass": {
        "tier1": PlaybackProfile(
            instrument="bass", code="tier1", label="Basic — E1 to B2",
            summary="For the first Bass unlock. Large chords are simplified into a clean bass line automatically.",
            mode="stable", unlock_tier="tier1", mapping="transpose", chord_limit=1,
            note_length=135, minimum_note=130,
        ),
        "tier2": PlaybackProfile(
            instrument="bass", code="tier2", label="Full range — E1 to B3 (Recommended)",
            summary="Best Bass choice when fully unlocked. The app switches to the extended Bass range automatically.",
            mode="stable", unlock_tier="tier2", mapping="octave", chord_limit=1,
            note_length=135, minimum_note=130,
        ),
    },
}

CUSTOM_LABEL = "Advanced setup…"


def profile_labels_for(instrument: InstrumentCode) -> dict[str, str]:
    labels = {
        profile.label: code
        for code, profile in FIXED_PROFILES[instrument].items()
    }
    labels[CUSTOM_LABEL] = "custom"
    return labels


def profile_label_for(instrument: InstrumentCode, code: str) -> str:
    for label, profile_code in profile_labels_for(instrument).items():
        if profile_code == code:
            return label
    return next(iter(profile_labels_for(instrument)))


def default_profile_code(instrument: InstrumentCode) -> str:
    return "tier2" if instrument == "bass" else "tier3"


def get_fixed_profile(instrument: InstrumentCode, code: str) -> PlaybackProfile:
    try:
        return FIXED_PROFILES[instrument][code]
    except KeyError as exc:
        raise ValueError(f"Unknown {instrument} fixed profile: {code}") from exc


def allowed_modes_for_unlock(instrument: InstrumentCode, unlock_tier: str) -> tuple[str, ...]:
    # Only keyboard/guitar Advanced full range can use page switching.
    if instrument in {"keyboard", "guitar"} and unlock_tier == "tier4":
        return ("stable", "full", "ensemble")
    return ("stable", "ensemble")
