from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


InstrumentCode = Literal["keyboard", "guitar", "bass"]
ProfileCode = Literal["tier1", "tier2", "tier3", "tier4", "raw"]

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


# User-facing categories mirror the game's unlock progression. Every normal
# profile deliberately stays on the middle page and uses only Ctrl/Shift octave
# toggles; none of these profiles can emit < or > page changes.
FIXED_PROFILES: dict[InstrumentCode, dict[str, PlaybackProfile]] = {
    "keyboard": {
        "tier1": PlaybackProfile(
            instrument="keyboard", code="tier1", label="Category 1 — Starting notes",
            summary="Game starts with C3–B4. Notes outside that range are fitted automatically.",
            mode="stable", unlock_tier="tier1", mapping="transpose", chord_limit=2,
        ),
        "tier2": PlaybackProfile(
            instrument="keyboard", code="tier2", label="Category 2 — C5–B6 unlocked",
            summary="Uses the cumulative safe range C3–B6 and automatically fits anything outside it.",
            mode="stable", unlock_tier="tier2", mapping="octave", chord_limit=3,
        ),
        "tier3": PlaybackProfile(
            instrument="keyboard", code="tier3", label="Category 3 — A0–B2 unlocked",
            summary="Uses C2–B6 so playback can stay on the middle page and never press < or >.",
            mode="stable", unlock_tier="tier3", mapping="octave", chord_limit=0,
        ),
        "tier4": PlaybackProfile(
            instrument="keyboard", code="tier4", label="Category 4 — C7–C8 unlocked",
            summary="Still uses C2–B6 during playback to avoid page changes; extra outer notes are remapped safely.",
            mode="stable", unlock_tier="tier4", mapping="octave", chord_limit=0,
        ),
        "raw": PlaybackProfile(
            instrument="keyboard", code="raw", label="Raw MIDI — no remap",
            summary="Keeps original pitches and full chords. Notes outside the safe C2–B6 no-page range are skipped, not remapped.",
            mode="stable", unlock_tier="tier4", mapping="skip", chord_limit=0,
        ),
    },
    "guitar": {
        "tier1": PlaybackProfile(
            instrument="guitar", code="tier1", label="Category 1 — Starting notes",
            summary="Game starts with C3–B4. Notes outside that range are fitted automatically.",
            mode="stable", unlock_tier="tier1", mapping="transpose", chord_limit=2,
        ),
        "tier2": PlaybackProfile(
            instrument="guitar", code="tier2", label="Category 2 — E2–B2 unlocked",
            summary="Uses E2–B4 with stable whole-song fitting first, then only local octave adjustment when still needed.",
            mode="stable", unlock_tier="tier2", mapping="transpose", chord_limit=3,
        ),
        "tier3": PlaybackProfile(
            instrument="guitar", code="tier3", label="Category 3 — C5–D6 unlocked",
            summary="Uses the complete E2–D6 no-page range with stable whole-song fitting and automatic Ctrl/Shift switching.",
            mode="stable", unlock_tier="tier3", mapping="transpose", chord_limit=0,
        ),
        "raw": PlaybackProfile(
            instrument="guitar", code="raw", label="Raw MIDI — no remap",
            summary="Keeps original pitches and full chords. Notes outside E2–D6 are skipped, not remapped.",
            mode="stable", unlock_tier="tier3", mapping="skip", chord_limit=0,
        ),
    },
    "bass": {
        "tier1": PlaybackProfile(
            instrument="bass", code="tier1", label="Category 1 — Starting notes",
            summary="Game starts with E1–B2. Notes outside that range are fitted into the bass line automatically.",
            mode="stable", unlock_tier="tier1", mapping="transpose", chord_limit=1,
        ),
        "tier2": PlaybackProfile(
            instrument="bass", code="tier2", label="Category 2 — High range unlocked",
            summary="Uses E1–B3 with stable whole-song fitting and switches High Octave automatically when needed.",
            mode="stable", unlock_tier="tier2", mapping="transpose", chord_limit=1,
        ),
        "raw": PlaybackProfile(
            instrument="bass", code="raw", label="Raw MIDI — no remap",
            summary="Keeps original pitches and full chords. Notes outside E1–B3 are skipped, not remapped.",
            mode="stable", unlock_tier="tier2", mapping="skip", chord_limit=0,
        ),
    },
}


def profile_labels_for(instrument: InstrumentCode) -> dict[str, str]:
    return {
        profile.label: code
        for code, profile in FIXED_PROFILES[instrument].items()
    }


def profile_label_for(instrument: InstrumentCode, code: str) -> str:
    for label, profile_code in profile_labels_for(instrument).items():
        if profile_code == code:
            return label
    return next(iter(profile_labels_for(instrument)))


def default_profile_code(instrument: InstrumentCode) -> str:
    if instrument == "keyboard":
        return "tier4"
    if instrument == "guitar":
        return "tier3"
    return "tier2"


def get_fixed_profile(instrument: InstrumentCode, code: str) -> PlaybackProfile:
    try:
        return FIXED_PROFILES[instrument][code]
    except KeyError as exc:
        raise ValueError(f"Unknown {instrument} profile: {code}") from exc


def allowed_modes_for_unlock(instrument: InstrumentCode, unlock_tier: str) -> tuple[str, ...]:
    # Kept only for backwards compatibility with old controller code. The v2.3
    # product exposes no playback-style selector and every profile is stable.
    del instrument, unlock_tier
    return ("stable",)
