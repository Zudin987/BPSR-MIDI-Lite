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


FIXED_PROFILES: dict[InstrumentCode, dict[str, PlaybackProfile]] = {
    "keyboard": {
        "tier1": PlaybackProfile(
            instrument="keyboard", code="tier1", label="Tier 1 — C3–B4",
            summary=(
                "For the first keyboard unlock. Uses only C3–B4 with no Ctrl, Shift, "
                "or page keys. The song is automatically fitted to the available notes."
            ),
            mode="stable", unlock_tier="tier1", mapping="transpose", chord_limit=2,
            minimum_note=130,
        ),
        "tier2": PlaybackProfile(
            instrument="keyboard", code="tier2", label="Tier 2 — C3–B6",
            summary=(
                "Uses C3–B6 with Default + Shift. It never presses < or > and keeps "
                "a balanced amount of chord detail."
            ),
            mode="stable", unlock_tier="tier2", mapping="octave", chord_limit=3,
        ),
        "tier3": PlaybackProfile(
            instrument="keyboard", code="tier3", label="Tier 3 — C2–B6 (Recommended)",
            summary=(
                "Uses the complete safe middle-page range with Ctrl / Default / Shift. "
                "It guarantees zero < or > page presses."
            ),
            mode="stable", unlock_tier="tier3", mapping="octave", chord_limit=0,
        ),
    },
    "guitar": {
        "tier1": PlaybackProfile(
            instrument="guitar", code="tier1", label="Tier 1 — C3–B4",
            summary=(
                "For the first guitar unlock. Uses C3–B4 in Default mode and never "
                "presses Ctrl, Shift, < or >."
            ),
            mode="stable", unlock_tier="tier1", mapping="transpose", chord_limit=2,
            minimum_note=130,
        ),
        "tier2": PlaybackProfile(
            instrument="guitar", code="tier2", label="Tier 2 — E2–B4",
            summary=(
                "Uses Guitar Low Octave (Ctrl) plus Default to cover E2–B4. "
                "It never changes keyboard pages."
            ),
            mode="stable", unlock_tier="tier2", mapping="octave", chord_limit=3,
        ),
        "tier3": PlaybackProfile(
            instrument="guitar", code="tier3", label="Tier 3 — E2–D6",
            summary=(
                "Uses Guitar Low Octave, Default and High Octave to cover E2–D6. "
                "It stays on the middle page and never presses < or >."
            ),
            mode="stable", unlock_tier="tier3", mapping="octave", chord_limit=0,
        ),
    },
    "bass": {
        "tier1": PlaybackProfile(
            instrument="bass", code="tier1", label="Tier 1 — E1–B2",
            summary=(
                "Uses the Bass Default layout from E1–B2. Dense MIDI chords are reduced "
                "to the lowest bass note so the line remains clean."
            ),
            mode="stable", unlock_tier="tier1", mapping="transpose", chord_limit=1,
            note_length=135, minimum_note=130,
        ),
        "tier2": PlaybackProfile(
            instrument="bass", code="tier2", label="Tier 2 — E1–B3",
            summary=(
                "Uses Bass High Octave (Shift) to expose E1–B3. The app presses Shift "
                "at playback start and resets it afterward. Bass has no Low Octave mode."
            ),
            mode="stable", unlock_tier="tier2", mapping="octave", chord_limit=1,
            note_length=135, minimum_note=130,
        ),
    },
}

CUSTOM_LABEL = "Custom — advanced settings"


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
    # Only keyboard/guitar Custom full range can use page switching.
    if instrument in {"keyboard", "guitar"} and unlock_tier == "tier4":
        return ("stable", "full", "ensemble")
    return ("stable", "ensemble")
