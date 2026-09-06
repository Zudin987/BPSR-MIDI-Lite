from __future__ import annotations

import hashlib
from pathlib import Path

import band_share


ROOM = "ABCDEFGHJKLM"


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self, _limit: int = -1) -> bytes:
        return self._data


def _midi_bytes() -> bytes:
    return (
        b"MThd"
        + (6).to_bytes(4, "big")
        + (0).to_bytes(2, "big")
        + (1).to_bytes(2, "big")
        + (480).to_bytes(2, "big")
        + b"MTrk"
        + (4).to_bytes(4, "big")
        + b"\x00\xff\x2f\x00"
    )


def _share_payload(data: bytes) -> dict[str, object]:
    digest = hashlib.sha256(data).hexdigest()
    return {
        "proto": 2,
        "share_proto": band_share.SHARE_PROTOCOL_VERSION,
        "event": "midi_share",
        "room": ROOM,
        "player_id": "host",
        "midi_sha256": digest,
        "filename": "../Blue Bird.mid",
        "size": len(data),
        "expires": 1234567890,
        "url": "https://ntfy.sh/file/abc123.mid",
    }


def test_share_filename_is_sanitized_and_kept_as_midi() -> None:
    assert band_share.sanitize_midi_filename("../../Blue:Bird?.mid") == "Blue_Bird_.mid"
    assert band_share.sanitize_midi_filename("song.exe").endswith(".mid")


def test_cache_path_is_collision_safe_and_inside_band_cache(tmp_path: Path) -> None:
    digest = "a" * 64
    path = band_share.cache_path_for_share("../Song.mid", digest, root=tmp_path)
    assert path.parent == tmp_path
    assert path.name == "Song-aaaaaaaa.mid"


def test_share_payload_rejects_non_ntfy_attachment() -> None:
    data = _midi_bytes()
    payload = _share_payload(data)
    payload["url"] = "https://example.com/evil.mid"
    try:
        band_share.validate_midi_share_payload(payload, room_code=ROOM)
    except ValueError as exc:
        assert "configured Band relay" in str(exc)
    else:
        raise AssertionError("foreign attachment host should be rejected")


def test_download_verifies_sha256_and_writes_only_verified_midi(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data = _midi_bytes()
    payload = _share_payload(data)
    monkeypatch.setattr(
        band_share.urllib.request,
        "urlopen",
        lambda request, timeout: _FakeResponse(data),
    )
    path = band_share.download_shared_midi(payload, room_code=ROOM, cache_root=tmp_path)
    assert path.exists()
    assert path.read_bytes() == data
    assert path.name.endswith(f"-{hashlib.sha256(data).hexdigest()[:8]}.mid")


def test_download_rejects_tampered_midi(tmp_path: Path, monkeypatch) -> None:
    data = _midi_bytes()
    payload = _share_payload(data)
    tampered = data[:-1] + b"\x01"
    monkeypatch.setattr(
        band_share.urllib.request,
        "urlopen",
        lambda request, timeout: _FakeResponse(tampered),
    )
    try:
        band_share.download_shared_midi(payload, room_code=ROOM, cache_root=tmp_path)
    except OSError as exc:
        assert "SHA-256" in str(exc)
    else:
        raise AssertionError("tampered MIDI should be rejected")
    assert list(tmp_path.iterdir()) == []


def test_upload_uses_temporary_ntfy_attachment_and_returns_verified_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data = _midi_bytes()
    midi = tmp_path / "Blue Bird.mid"
    midi.write_bytes(data)
    captured = {}
    response = (
        b'{"attachment":{"name":"Blue Bird.mid","size":'
        + str(len(data)).encode("ascii")
        + b',"expires":2000000000,"url":"https://ntfy.sh/file/test.mid"}}'
    )

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["filename"] = request.headers.get("Filename")
        captured["body"] = request.data
        return _FakeResponse(response)

    monkeypatch.setattr(band_share.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(band_share, "_attachment_topic", lambda: "bpsr-band-file-test")
    attachment = band_share.upload_midi_attachment(midi)
    assert captured["url"] == "https://ntfy.sh/bpsr-band-file-test"
    assert captured["method"] == "PUT"
    assert captured["filename"] == "Blue Bird.mid"
    assert captured["body"] == data
    assert attachment["midi_sha256"] == hashlib.sha256(data).hexdigest()
    assert attachment["url"] == "https://ntfy.sh/file/test.mid"


def test_source_is_lazy_visible_and_has_no_heavy_dependencies() -> None:
    source = Path("band_share.py").read_text(encoding="utf-8")
    assert "Allow room members to download this MIDI" in source
    assert "_share_needs_upload" in source
    assert "MThd" in source
    assert "SHA-256" in source
    assert "requests" not in source
    assert "boto" not in source
