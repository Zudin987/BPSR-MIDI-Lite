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
    speed: int = 100
    note_length: int = 100
    minimum_note: int = 70
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


# Beginner-facing names are intentionally independent from the technical note
# ranges. Fixed profiles use conservative BPSR-safe articulation defaults.
FIXED_PROFILES: dict[InstrumentCode, dict[str, PlaybackProfile]] = {
    "keyboard": {
        "tier1": PlaybackProfile(
            instrument="keyboard", code="tier1", label="First unlock",
            summary="Choose this if you only have the first Keyboard range. Larger songs are fitted automatically.",
            mode="stable", unlock_tier="tier1", mapping="transpose", chord_limit=2,
        ),
        "tier2": PlaybackProfile(
            instrument="keyboard", code="tier2", label="Second unlock",
            summary="Choose this after unlocking the second Keyboard range. Extra high notes are handled automatically.",
            mode="stable", unlock_tier="tier2", mapping="octave", chord_limit=3,
        ),
        "tier3": PlaybackProfile(
            instrument="keyboard", code="tier3", label="Fully unlocked (Recommended)",
            summary="Best normal Keyboard choice when all regular ranges are unlocked. No page changes are needed.",
            mode="stable", unlock_tier="tier3", mapping="octave", chord_limit=0,
        ),
    },
    "guitar": {
        "tier1": PlaybackProfile(
            instrument="guitar", code="tier1", label="First unlock",
            summary="Choose this if you only have the first Guitar range. Larger songs are fitted automatically.",
            mode="stable", unlock_tier="tier1", mapping="transpose", chord_limit=2,
        ),
        "tier2": PlaybackProfile(
            instrument="guitar", code="tier2", label="Second unlock",
            summary="Choose this after unlocking the second Guitar range. Extra low notes are handled automatically.",
            mode="stable", unlock_tier="tier2", mapping="octave", chord_limit=3,
        ),
        "tier3": PlaybackProfile(
            instrument="guitar", code="tier3", label="Fully unlocked (Recommended)",
            summary="Best normal Guitar choice when all regular ranges are unlocked. No page changes are needed.",
            mode="stable", unlock_tier="tier3", mapping="octave", chord_limit=0,
        ),
    },
    "bass": {
        "tier1": PlaybackProfile(
            instrument="bass", code="tier1", label="First unlock",
            summary="Choose this for the first Bass range. Large chords are simplified into a clean bass line automatically.",
            mode="stable", unlock_tier="tier1", mapping="transpose", chord_limit=1,
        ),
        "tier2": PlaybackProfile(
            instrument="bass", code="tier2", label="Fully unlocked (Recommended)",
            summary="Best Bass choice when the regular Bass range is fully unlocked. The extra range is handled automatically.",
            mode="stable", unlock_tier="tier2", mapping="octave", chord_limit=1,
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
