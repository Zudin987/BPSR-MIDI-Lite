from __future__ import annotations

from pathlib import Path

import pytest

from studio_band.resolver import AcquisitionStore
from studio_spotdl import (
    SPOTDL_VERSION,
    SpotDLError,
    SpotDLResolver,
    _spotify_track_url,
    _track_from_payload,
)


class _FakeRuntime:
    def ensure(self, **_kwargs):
        return {"ready": True, "deno_ready": True, "version": SPOTDL_VERSION}


def _payload(track_id: str = "abc123") -> dict:
    return {
        "song_id": track_id,
        "name": "Drowning",
        "artists": ["WOODZ"],
        "album_name": "OO-LI",
        "duration": 244.5,
        "isrc": "KRA382301234",
        "url": f"https://open.spotify.com/track/{track_id}?si=test",
    }


def test_spotdl_payload_becomes_downloadable_track():
    track = _track_from_payload(_payload())
    assert track.provider == "spotdl"
    assert track.provider_id == "abc123"
    assert track.title == "Drowning"
    assert track.artist == "WOODZ"
    assert track.store_url == "https://open.spotify.com/track/abc123"
    assert track.can_acquire is True
    assert track.acquisition == "spotdl_youtube_download"


def test_spotdl_search_uses_only_spotify_results(tmp_path, monkeypatch):
    resolver = SpotDLResolver(runtime=_FakeRuntime(), store=AcquisitionStore(tmp_path / "audio"))
    monkeypatch.setattr(resolver, "_run_search_worker", lambda *_args, **_kwargs: [_payload("one"), _payload("two")])
    report = resolver.search("WOODZ Drowning", limit=10)
    assert [track.provider_id for track in report.tracks] == ["one", "two"]
    assert all(track.provider == "spotdl" for track in report.tracks)
    assert report.warnings == []


def test_spotdl_rejects_non_spotify_download_target():
    with pytest.raises(SpotDLError):
        _spotify_track_url("https://example.com/track/abc123")


def test_spotdl_download_command_is_argument_list_not_shell():
    track = _track_from_payload(_payload())
    command = SpotDLResolver._download_command(
        track,
        Path("python.exe"),
        Path("ffmpeg.exe"),
        Path("work/{track-id}.{output-ext}"),
    )
    assert command[:4] == ["python.exe", "-m", "spotdl", "download"]
    assert "youtube-music" in command and "youtube" in command
    assert "--ffmpeg" in command and "ffmpeg.exe" in command
    assert command[-1] == "https://open.spotify.com/track/abc123"
    assert all(isinstance(value, str) for value in command)
