from __future__ import annotations

import re

import band_sync
from band_audit_hardening import anonymous_band_name, install_band_audit_hardening
from studio_audit_hardening import clear_studio_thread_state, sanitize_manifest_record


def test_saved_manifest_drops_machine_local_cache_and_model_directories():
    record = {
        "schema_version": 1,
        "cache_job": r"C:\Users\alice\AppData\Roaming\BPSR MIDI Lite\studio\jobs\secret",
        "providers": {
            "engines": [{
                "provider": "example",
                "model_sha256": {
                    r"C:\Users\alice\AppData\Roaming\BPSR MIDI Lite\models\weights.bin": "abc123",
                },
            }],
        },
        "master_song": {
            "provenance": {
                "engines": [{
                    "model_sha256": {
                        "/home/alice/.cache/bpsr/model.ckpt": "def456",
                    },
                }],
            },
        },
    }
    clean = sanitize_manifest_record(record)
    assert "cache_job" not in clean
    assert clean["providers"]["engines"][0]["model_sha256"] == {"weights.bin": "abc123"}
    assert clean["master_song"]["provenance"]["engines"][0]["model_sha256"] == {"model.ckpt": "def456"}
    text = repr(clean)
    assert "Users\\\\alice" not in text
    assert "/home/alice" not in text


def test_default_band_name_is_anonymous_not_an_os_account_name():
    assert re.fullmatch(r"Player-[0-9A-F]{4}", anonymous_band_name())


def test_roster_ignores_malformed_remote_state_without_throwing():
    install_band_audit_hardening()
    roster = band_sync.BandRoster()
    good = {
        "proto": band_sync.BAND_PROTOCOL_VERSION,
        "event": "state",
        "player_id": "p1",
        "name": "  Test   Player  ",
        "role": "keyboard",
        "active_parts": ["keyboard", "guitar"],
        "ready": True,
        "midi_sha256": "abc",
        "app_version": "test",
        "speed_percent": 100,
        "clock_synced": True,
        "clock_rtt_ms": 12.0,
        "host": True,
    }
    roster.apply(good, now=1.0)
    assert roster.players["p1"].name == "Test Player"

    for payload in (
        {**good, "player_id": "bad-role", "role": "kazoo"},
        {**good, "player_id": "bad-speed", "speed_percent": "NaN"},
        {**good, "player_id": "bad-rtt", "clock_rtt_ms": float("nan")},
        {**good, "player_id": "x" * 1000},
    ):
        roster.apply(payload, now=1.0)
    assert set(roster.players) == {"p1"}


def test_failed_conversion_reviewer_state_can_be_cleared_for_retry():
    from studio_band import fast_precision, precision_judges

    fast_precision._STATE.context = {"job": "old"}
    precision_judges._STATE.review_context = {"job": "old"}
    precision_judges._STATE.review_regions = [{"start": 1, "end": 2}]
    clear_studio_thread_state()
    assert not hasattr(fast_precision._STATE, "context")
    assert not hasattr(precision_judges._STATE, "review_context")
    assert not hasattr(precision_judges._STATE, "review_regions")
