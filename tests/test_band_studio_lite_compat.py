from __future__ import annotations

from types import SimpleNamespace

import band_arranger
import band_runtime_hardening
import band_sync


ROOM = "ABCDEFGH2345"
MIDI_HASH = "a" * 64
SPEED = 100
ACTIVE_PARTS = ("keyboard", "guitar")


def _client(product_version: str):
    # Product versions are intentionally different between Lite and Studio.
    # Band compatibility must not depend on these user-facing version strings.
    return SimpleNamespace(
        _modern_module=SimpleNamespace(APP_VERSION=product_version),
    )


def test_studio_and_lite_share_the_same_band_compatibility_token() -> None:
    lite = _client("3.4.0")
    studio = _client("Studio 0.5.0-band-accurate-beta.9")

    lite_token = band_runtime_hardening._band_compatibility_version(lite)
    studio_token = band_runtime_hardening._band_compatibility_version(studio)

    assert lite_token == studio_token
    assert lite_token == (
        f"band-proto-{band_sync.BAND_PROTOCOL_VERSION}"
        f"-arr-{band_arranger.BAND_ARRANGEMENT_VERSION}"
    )
    assert "Studio" not in lite_token
    assert "3.4.0" not in lite_token


def test_lite_host_and_studio_client_pass_room_compatibility() -> None:
    lite = _client("3.4.0")
    studio = _client("Studio 0.5.0-band-accurate-beta.9")
    token = band_runtime_hardening._band_compatibility_version(lite)
    assert token == band_runtime_hardening._band_compatibility_version(studio)

    clock = band_sync.ClockSample("test", offset_ms=0.0, rtt_ms=5.0)
    roster = band_sync.BandRoster()

    roster.apply(
        band_sync.make_state_payload(
            room_code=ROOM,
            player_id="lite-host",
            name="Lite host",
            role="keyboard",
            ready=True,
            midi_hash=MIDI_HASH,
            app_version=token,
            speed_percent=SPEED,
            clock_sample=clock,
            host=True,
            active_parts=ACTIVE_PARTS,
        ),
        now=1.0,
    )
    roster.apply(
        band_sync.make_state_payload(
            room_code=ROOM,
            player_id="studio-client",
            name="Studio client",
            role="guitar",
            ready=True,
            midi_hash=MIDI_HASH,
            app_version=token,
            speed_percent=SPEED,
            clock_sample=clock,
            host=False,
            active_parts=ACTIVE_PARTS,
        ),
        now=1.0,
    )

    assert roster.compatibility_issues(
        expected_hash=MIDI_HASH,
        expected_version=token,
        expected_speed=SPEED,
        expected_active_parts=ACTIVE_PARTS,
        minimum_players=2,
        now=1.0,
    ) == []


def test_cross_edition_start_payload_uses_shared_band_token() -> None:
    lite = _client("3.4.0")
    studio = _client("Studio 0.5.0-band-accurate-beta.9")
    token = band_runtime_hardening._band_compatibility_version(lite)
    assert token == band_runtime_hardening._band_compatibility_version(studio)

    payload = band_sync.make_start_payload(
        room_code=ROOM,
        player_id="lite-host",
        start_utc_ms=1_800_000_000_000,
        midi_hash=MIDI_HASH,
        app_version=token,
        speed_percent=SPEED,
        active_parts=ACTIVE_PARTS,
    )

    assert payload["proto"] == band_sync.BAND_PROTOCOL_VERSION
    assert payload["app_version"] == token
    assert tuple(payload["active_parts"]) == ACTIVE_PARTS
    assert payload["midi_sha256"] == MIDI_HASH
    assert payload["speed_percent"] == SPEED
