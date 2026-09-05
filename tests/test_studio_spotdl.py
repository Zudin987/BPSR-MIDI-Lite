from __future__ import annotations

from pathlib import Path

import pytest

import studio_spotdl_fallback as fallback
import studio_youtube
from studio_band.resolver import AcquisitionStore
from studio_band.spotdl_worker import _raw_track_payload
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


def test_raw_spotify_search_item_needs_no_per_result_hydration():
    payload = _raw_track_payload({
        "id": "love123",
        "name": "Love Story (Taylor's Version)",
        "artists": [{"name": "Taylor Swift"}],
        "album": {"name": "Fearless (Taylor's Version)", "release_date": "2021-04-09"},
        "duration_ms": 235766,
        "external_ids": {"isrc": "USUG12100659"},
        "external_urls": {"spotify": "https://open.spotify.com/track/love123?si=test"},
    })
    assert payload["song_id"] == "love123"
    assert payload["name"] == "Love Story (Taylor's Version)"
    assert payload["artists"] == ["Taylor Swift"]
    assert payload["album_name"] == "Fearless (Taylor's Version)"
    assert payload["duration"] == pytest.approx(235.766)
    assert payload["url"].startswith("https://open.spotify.com/track/love123")


def test_spotdl_search_uses_spotify_results_when_primary_succeeds(tmp_path, monkeypatch):
    resolver = SpotDLResolver(runtime=_FakeRuntime(), store=AcquisitionStore(tmp_path / "audio"))
    monkeypatch.setattr(resolver, "_run_search_worker", lambda *_args, **_kwargs: [_payload("one"), _payload("two")])
    report = resolver.search("WOODZ Drowning", limit=10)
    assert [track.provider_id for track in report.tracks] == ["one", "two"]
    assert all(track.provider == "spotdl" for track in report.tracks)
    assert report.warnings == []


def test_spotdl_search_failure_returns_direct_ytdlp_results(tmp_path, monkeypatch):
    resolver = SpotDLResolver(runtime=_FakeRuntime(), store=AcquisitionStore(tmp_path / "audio"))

    def primary(_self, _query, **_kwargs):
        raise SpotDLError("spotDL could not search Spotify metadata.", "temporary Spotify failure")

    monkeypatch.setattr(
        fallback,
        "_search_ytdlp",
        lambda *_args, **_kwargs: [
            studio_youtube.YouTubeResult("yt123", "Love Story", "Taylor Swift", 236),
        ],
    )
    report = fallback._fallback_search(resolver, primary, "love story", limit=5)
    assert len(report.tracks) == 1
    assert report.tracks[0].provider == fallback.YTDLP_PROVIDER
    assert report.tracks[0].provider_id == "yt123"
    assert report.tracks[0].acquisition == "ytdlp_direct_download"
    assert any("fallback" in warning.casefold() for warning in report.warnings)


def test_direct_fallback_prefers_metadata_and_duration_match():
    track = _track_from_payload(_payload())
    results = [
        studio_youtube.YouTubeResult("wrong", "Drowning cover karaoke", "Random", 245),
        studio_youtube.YouTubeResult("right", "WOODZ - Drowning", "WOODZ", 244),
        studio_youtube.YouTubeResult("long", "WOODZ Drowning reaction", "Fan Channel", 900),
    ]
    assert fallback._pick_youtube_match(track, results).video_id == "right"


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


def test_ytdlp_fallback_download_command_is_argument_list_not_shell():
    result = studio_youtube.YouTubeResult("yt123", "Love Story", "Taylor Swift", 236)
    command = fallback._download_command(
        Path("yt-dlp.exe"),
        Path("deno.exe"),
        Path("ffmpeg.exe"),
        Path("work/source.%(ext)s"),
        result,
    )
    assert command[0] == "yt-dlp.exe"
    assert "--js-runtimes" in command and "deno:deno.exe" in command
    assert "--audio-format" in command and "mp3" in command
    assert "--ffmpeg-location" in command and "ffmpeg.exe" in command
    assert command[-1] == "https://www.youtube.com/watch?v=yt123"
    assert all(isinstance(value, str) for value in command)
