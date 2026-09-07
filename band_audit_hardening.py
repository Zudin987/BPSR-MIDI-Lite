"""Small Band Mode privacy/network hardening found by the v3.4 audit."""
from __future__ import annotations

import math
import secrets
from typing import Any

AUDIT_RELEASE = "v3.5.0"
_INSTALLED = False

# In-game calibration capture (2026-09-07): only these C4-B5 transport
# positions actually produced Drum-instrument audio. Keep Band Mode off the
# remaining silent keyboard slots even when importing arbitrary GM percussion.
CALIBRATED_DRUM_PITCHES = (62, 63, 65, 69, 72, 74, 76, 77, 79, 81)
_GM_DRUM_TO_BPSR = {
    35: 65, 36: 65,                    # kick
    37: 72, 38: 72, 39: 72, 40: 72,    # snare / clap
    41: 69, 43: 69,                    # low toms
    45: 74, 47: 74,                    # mid toms
    48: 76, 50: 76,                    # high toms
    42: 62, 44: 62,                    # closed/pedal hat
    46: 79, 54: 79,                    # open hat / tambourine-like fallback
    49: 81, 52: 81, 55: 81, 57: 81, 58: 81,  # crash/effect cymbals
    51: 77, 53: 77, 59: 77,            # ride
    56: 76,                             # cowbell-like fallback -> audible high percussion
}


def anonymous_band_name() -> str:
    """Return a non-identifying default; users may still edit the room name."""
    return f"Player-{secrets.token_hex(2).upper()}"


def calibrated_drum_pitch(pitch: int) -> int:
    """Map percussion onto only BPSR Drum keys confirmed to make sound."""
    value = int(pitch)
    if value in CALIBRATED_DRUM_PITCHES:
        return value
    mapped = _GM_DRUM_TO_BPSR.get(value)
    if mapped is not None:
        return mapped
    # Preserve the old deterministic 24-slot transport shape for unusual notes,
    # then snap the result to the nearest confirmed-audible pad. This guarantees
    # a Drum part never intentionally presses one of the silent BPSR keys.
    wrapped = 60 + ((value - 35) % 24)
    return min(CALIBRATED_DRUM_PITCHES, key=lambda item: (abs(item - wrapped), item))


def _patch_band_identity() -> None:
    import band_ui

    if getattr(band_ui._safe_username, "_bpsr_anonymous_default", False):
        return

    def safe_username() -> str:
        return anonymous_band_name()

    safe_username._bpsr_anonymous_default = True
    band_ui._safe_username = safe_username


def _patch_band_roster() -> None:
    import band_sync

    original = band_sync.BandRoster.apply
    if getattr(original, "_bpsr_audit_hardened", False):
        return

    def apply(self, payload: dict[str, Any], *, now: float | None = None) -> None:
        if not isinstance(payload, dict):
            return
        event = str(payload.get("event", ""))
        player_id = str(payload.get("player_id", "")).strip()
        if not player_id or len(player_id) > 64:
            return

        cleaned = dict(payload)
        cleaned["player_id"] = player_id
        if event == "state":
            role = str(payload.get("role", ""))
            if role not in band_sync.PART_ORDER:
                return
            try:
                speed = int(payload.get("speed_percent", 100))
                rtt = float(payload.get("clock_rtt_ms", -1.0))
            except (TypeError, ValueError, OverflowError):
                return
            synced = bool(payload.get("clock_synced", False))
            if not 25 <= speed <= 200 or not math.isfinite(rtt):
                return
            if (synced and rtt < 0.0) or (not synced and rtt < -1.0) or rtt > 60_000.0:
                return

            cleaned.update({
                "role": role,
                "name": " ".join(str(payload.get("name", "Player")).split())[:32] or "Player",
                "midi_sha256": str(payload.get("midi_sha256", ""))[:128],
                "app_version": str(payload.get("app_version", ""))[:128],
                "speed_percent": speed,
                "clock_rtt_ms": rtt,
            })
        elif event != "leave":
            return
        return original(self, cleaned, now=now)

    apply._bpsr_audit_hardened = True
    band_sync.BandRoster.apply = apply


def _patch_drum_transport() -> None:
    import band_arranger

    current = band_arranger.normalize_drum_pitch
    if getattr(current, "_bpsr_calibrated_drums", False):
        return

    def normalize_drum_pitch(pitch: int) -> int:
        return calibrated_drum_pitch(pitch)

    normalize_drum_pitch._bpsr_calibrated_drums = True
    band_arranger.normalize_drum_pitch = normalize_drum_pitch


def install_band_audit_hardening() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _patch_band_identity()
    _patch_band_roster()
    _patch_drum_transport()
    _INSTALLED = True