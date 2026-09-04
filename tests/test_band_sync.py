from __future__ import annotations

from pathlib import Path

import band_sync


def _state(
    player_id: str,
    role: str,
    *,
    ready: bool = True,
    midi_hash: str = "abc",
    version: str = "3.4.0",
    speed: int = 100,
    synced: bool = True,
    host: bool = False,
) -> dict[str, object]:
    return {
        "proto": band_sync.BAND_PROTOCOL_VERSION,
        "event": "state",
        "player_id": player_id,
        "name": player_id,
        "role": role,
        "ready": ready,
        "midi_sha256": midi_hash,
        "app_version": version,
        "speed_percent": speed,
        "clock_synced": synced,
        "clock_rtt_ms": 12.5 if synced else -1.0,
        "host": host,
    }


def test_room_codes_are_human_shareable_and_topic_is_deterministic() -> None:
    code = band_sync.generate_room_code()
    assert len(code) == band_sync.ROOM_CODE_LENGTH
    assert band_sync.normalize_room_code(code.lower()) == code
    assert band_sync.topic_for_room(code) == f"bpsr-band-{code.lower()}"


def test_midi_hash_is_content_based(tmp_path: Path) -> None:
    first = tmp_path / "a.mid"
    second = tmp_path / "renamed.mid"
    first.write_bytes(b"same-midi-bytes")
    second.write_bytes(b"same-midi-bytes")
    assert band_sync.midi_sha256(first) == band_sync.midi_sha256(second)


def test_roster_accepts_matching_ready_players() -> None:
    roster = band_sync.BandRoster()
    roster.apply(_state("host", "keyboard", host=True), now=10.0)
    roster.apply(_state("guitar", "guitar"), now=10.0)
    assert roster.compatibility_issues(
        expected_hash="abc",
        expected_version="3.4.0",
        expected_speed=100,
        now=10.0,
    ) == []


def test_roster_blocks_mismatch_unready_duplicate_and_unsynced() -> None:
    roster = band_sync.BandRoster()
    roster.apply(_state("host", "keyboard", host=True), now=10.0)
    roster.apply(
        _state(
            "other",
            "keyboard",
            ready=False,
            midi_hash="different",
            version="old",
            speed=90,
            synced=False,
        ),
        now=10.0,
    )
    issues = roster.compatibility_issues(
        expected_hash="abc",
        expected_version="3.4.0",
        expected_speed=100,
        now=10.0,
    )
    assert "Everyone must be Ready" in issues
    assert "Every player needs a synchronized clock" in issues
    assert "MIDI files do not all match" in issues
    assert "Everyone must use the same BPSR MIDI version" in issues
    assert "Song speed does not match between players" in issues
    assert "Two players selected the same band part" in issues


def test_roster_blocks_drums_until_mapping_is_verified() -> None:
    roster = band_sync.BandRoster()
    roster.apply(_state("host", "keyboard", host=True), now=10.0)
    roster.apply(_state("drummer", "drums"), now=10.0)
    issues = roster.compatibility_issues(
        expected_hash="abc",
        expected_version="3.4.0",
        expected_speed=100,
        drums_supported=False,
        now=10.0,
    )
    assert "BPSR drum mapping is not configured yet" in issues


def test_stale_players_are_pruned_on_the_same_injected_clock() -> None:
    roster = band_sync.BandRoster()
    roster.apply(_state("old", "keyboard"), now=10.0)
    roster.prune(now=40.1)
    assert roster.players == {}


def test_start_delay_uses_clock_offset(monkeypatch) -> None:
    monkeypatch.setattr(band_sync.time, "time", lambda: 1000.0)
    sample = band_sync.ClockSample(server="test", offset_ms=25.0, rtt_ms=10.0)
    assert band_sync.delay_until_utc_ms(1_006_025, sample) == 6.0


def test_ntfy_transport_is_zero_account_non_cached_and_start_redundant() -> None:
    source = Path("band_sync.py").read_text(encoding="utf-8")
    assert 'DEFAULT_NTFY_BASE_URL = "https://ntfy.sh"' in source
    assert '"Cache": "no"' in source
    assert '"Firebase": "no"' in source
    assert "/json" in source
    assert "requests" not in source
    assert "START_PUBLISH_ATTEMPTS = 3" in source
    assert 'payload.get("event") == "start"' in source
