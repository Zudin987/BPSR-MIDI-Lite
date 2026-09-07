"""Small Band Mode privacy/network hardening found by the v3.4 audit."""
from __future__ import annotations

import math
import secrets
from typing import Any

_INSTALLED = False


def anonymous_band_name() -> str:
    """Return a non-identifying default; users may still edit the room name."""
    return f"Player-{secrets.token_hex(2).upper()}"


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


def install_band_audit_hardening() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _patch_band_identity()
    _patch_band_roster()
    _INSTALLED = True
