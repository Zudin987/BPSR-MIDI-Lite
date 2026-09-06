from __future__ import annotations

import json
from pathlib import Path

import pytest

import studio_band.resolver as resolver_module
from studio_band.export import source_record
from studio_band.resolver import (AcquisitionStore, MusicResolver, ResolverConfig, ResolverError,
                                  ResolverTrack, oauth1_signed_url, parse_apple_music,
                                  parse_bandcamp, parse_itunes, parse_massive, query_from_signed_url)


def test_apple_discovery_keeps_isrc_but_never_exposes_preview_audio():
    tracks = parse_apple_music({"results": {"songs": {"data": [{
        "id": "apple-1",
        "attributes": {
            "name": "Mangu", "artistName": "Fourtwnty", "albumName": "Single",
            "durationInMillis": 252000, "isrc": "IDABC2600001", "releaseDate": "2026-01-02",
            "url": "https://music.apple.com/my/song/mangu/123", "previews": [{"url": "https://audio.example/clip.m4a"}],
        },
    }]}}})
    assert len(tracks) == 1
    track = tracks[0]
    assert track.isrc == "IDABC2600001" and track.duration_seconds == 252
    assert not track.can_acquire and track.acquisition == "metadata_only"
    assert "preview" not in json.dumps(track.public_metadata()).lower()


def test_public_apple_catalog_is_metadata_only_and_sanitises_store_url():
    tracks = parse_itunes({"results": [{
        "kind": "song", "trackId": 7, "trackName": "Latest Song", "artistName": "Artist",
        "collectionName": "Album", "trackTimeMillis": 180500,
        "trackViewUrl": "https://music.apple.com/id/album/example/7", "previewUrl": "https://example/preview.m4a",
    }]})
    assert tracks[0].provider == "apple_catalog" and tracks[0].duration_seconds == 180.5
    assert tracks[0].store_url.startswith("https://music.apple.com/")
    assert "preview" not in json.dumps(tracks[0].public_metadata()).lower()


def test_massive_catalogue_selects_best_format_and_requires_entitlement_credentials():
    payload = {"results": [{
        "id": 44, "title": "Song", "artist": {"name": "Singer"}, "isrc": "MYABC2600001",
        "release": {"id": 55, "title": "Album"}, "duration": 201,
        "availableFor": ["download"],
        "packages": [{"formats": [{"id": 17, "name": "MP3 320"},
                                      {"id": 52, "name": "FLAC 24-bit 44.1kHz"}]}],
    }]}
    catalogue = parse_massive(payload, ResolverConfig(massive_consumer_key="key"))[0]
    entitled = parse_massive(payload, ResolverConfig(massive_consumer_key="key",
                                                       massive_consumer_secret="secret",
                                                       massive_user_id="user"))[0]
    assert catalogue.format_id == "52" and catalogue.suffix == ".flac" and not catalogue.can_acquire
    assert entitled.can_acquire and entitled.acquisition == "entitled_partner_download"


def test_bandcamp_subsonic_results_are_owned_collection_downloads():
    tracks = parse_bandcamp({"subsonic-response": {"status": "ok", "searchResult3": {"song": [{
        "id": "bc-1", "title": "Owned Track", "artist": "Indie Artist", "album": "Owned Album",
        "duration": 191, "suffix": "flac", "contentType": "audio/flac",
    }]}}})
    assert len(tracks) == 1 and tracks[0].can_acquire
    assert tracks[0].provider == "bandcamp_collection" and tracks[0].suffix == ".flac"


def test_subsonic_challenge_and_config_repr_never_expose_password(tmp_path):
    config = ResolverConfig(bandcamp_username="fan", bandcamp_password="very-secret-password",
                            massive_consumer_secret="massive-secret", apple_token="apple-secret")
    auth = MusicResolver(config, AcquisitionStore(tmp_path))._subsonic_auth()
    assert auth["u"] == "fan" and len(auth["t"]) == 32 and auth["s"]
    assert "very-secret-password" not in urlencode_for_test(auth)
    rendered = repr(config)
    assert "very-secret-password" not in rendered and "massive-secret" not in rendered and "apple-secret" not in rendered


def urlencode_for_test(value):
    return "&".join(f"{key}={item}" for key, item in value.items())


def test_massive_oauth_signature_is_deterministic_and_contains_no_secrets():
    config = ResolverConfig(massive_consumer_key="consumer", massive_consumer_secret="consumer-secret",
                            massive_user_id="user", massive_user_token="token",
                            massive_user_token_secret="token-secret")
    url = oauth1_signed_url("https://media.geo.7digital.com/media/user/downloadtrack",
                            {"trackId": "1", "releaseId": "2", "formatId": "17", "country": "MY", "userId": "user"},
                            config, nonce="fixed", timestamp=1234567890)
    query = query_from_signed_url(url)
    assert query["oauth_consumer_key"] == ["consumer"] and query["oauth_token"] == ["token"]
    assert query["oauth_signature"] and query["oauth_signature_method"] == ["HMAC-SHA1"]
    assert "consumer-secret" not in url and "token-secret" not in url


def test_no_key_search_uses_apple_storefront_and_reports_optional_source_setup(tmp_path, monkeypatch):
    calls = []
    def fake_json(url, **_kwargs):
        calls.append(url)
        return {"results": [{"kind": "song", "trackId": 1, "trackName": "Mangu", "artistName": "Fourtwnty"}]}
    monkeypatch.setattr(resolver_module, "_json_get", fake_json)
    report = MusicResolver(ResolverConfig(storefront="MY"), AcquisitionStore(tmp_path)).search("Mangu Fourtwnty")
    assert len(report.tracks) == 1 and report.tracks[0].provider == "apple_catalog"
    assert "country=MY" in calls[0] and any("MassiveMusic" in note for note in report.warnings)
    assert any("Bandcamp" in note for note in report.warnings)


def test_invalid_apple_developer_token_falls_back_to_public_metadata(tmp_path, monkeypatch):
    calls = []
    def fake_json(url, **_kwargs):
        calls.append(url)
        if "api.music.apple.com" in url:
            raise ResolverError("The provider rejected the request (HTTP 401).")
        return {"results": [{"kind": "song", "trackId": 2, "trackName": "Fallback", "artistName": "Artist"}]}
    monkeypatch.setattr(resolver_module, "_json_get", fake_json)
    report = MusicResolver(ResolverConfig(storefront="ID", apple_token="private-token"),
                           AcquisitionStore(tmp_path)).search("Fallback")
    assert [track.title for track in report.tracks] == ["Fallback"]
    assert len(calls) == 2 and "country=ID" in calls[1]
    assert any("developer-token search failed" in note for note in report.warnings)
    assert "private-token" not in json.dumps(report.warnings)


class _Headers(dict):
    pass


class _Response:
    def __init__(self, data: bytes, content_type="audio/mpeg"):
        self.data, self.offset = data, 0
        self.headers = _Headers({"Content-Type": content_type, "Content-Length": str(len(data))})

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return "https://bandcamp.com/api/subsonic/rest/download.view?id=owned"

    def read(self, size=-1):
        if self.offset >= len(self.data):
            return b""
        end = len(self.data) if size < 0 else min(len(self.data), self.offset + size)
        chunk, self.offset = self.data[self.offset:end], end
        return chunk


def test_entitled_download_is_atomic_hashed_and_reused(tmp_path, monkeypatch):
    audio = b"ID3" + b"\x00" * 256
    calls = []
    monkeypatch.setattr(resolver_module, "urlopen", lambda request, timeout: (calls.append(request.full_url), _Response(audio))[1])
    track = ResolverTrack("bandcamp_collection", "owned", "Owned", can_acquire=True,
                          acquisition="owned_collection_download", suffix=".mp3")
    service = MusicResolver(ResolverConfig(bandcamp_api_key="key"), AcquisitionStore(tmp_path))
    url = "https://bandcamp.com/api/subsonic/rest/download.view?id=owned"
    first = service._download(track, url)
    acquired = service.acquire(track)
    assert first == acquired.path and first.read_bytes() == audio and len(calls) == 1
    assert acquired.metadata["audio_sha256"] == resolver_module.file_hash(first)
    record = json.loads(next((tmp_path / "records").glob("*.json")).read_text())
    assert record["sha256"] == resolver_module.file_hash(first)
    assert not list(tmp_path.glob("*.part"))


def test_download_rejects_non_audio_provider_response(tmp_path, monkeypatch):
    monkeypatch.setattr(resolver_module, "urlopen", lambda request, timeout: _Response(b"<html>login</html>", "text/html"))
    track = ResolverTrack("bandcamp_collection", "not-owned", "No", can_acquire=True,
                          acquisition="owned_collection_download", suffix=".mp3")
    service = MusicResolver(ResolverConfig(bandcamp_api_key="key"), AcquisitionStore(tmp_path))
    with pytest.raises(ResolverError, match="entitled"):
        service._download(track, "https://bandcamp.com/api/subsonic/rest/download.view?id=no")
    assert not list((tmp_path / "audio").iterdir())


def test_manifest_source_filter_removes_paths_credentials_and_unknown_fields():
    value = source_record({
        "input_mode": "provider", "provider": "bandcamp_collection", "title": "Song",
        "audio_sha256": "a" * 64, "password": "never-store", "token": "never-store",
        "local_path": "C:/private/song.flac", "unexpected": {"secret": True},
    })
    assert value["provider"] == "bandcamp_collection" and value["audio_sha256"] == "a" * 64
    assert "never-store" not in json.dumps(value) and "local_path" not in value and "unexpected" not in value


def test_ui_keeps_manual_audio_first_class_and_soundcloud_out_of_ai_acquisition():
    ui = Path("studio_band_ui.py").read_text(encoding="utf-8")
    resolver = Path("studio_band/resolver.py").read_text(encoding="utf-8").casefold()
    assert "Choose local audio…" in ui and "Acquire & Analyze" in ui
    assert "_fit_toplevel(self.workspace, 980, 780)" in ui
    assert "self.workspace_canvas" in ui and "self.workspace_scrollbar" in ui
    assert "self.source_scrollbar" in ui and "yscrollcommand=self.source_scrollbar.set" in ui
    assert "apple" in resolver and "bandcamp" in resolver and "massive" in resolver
    assert "soundcloud" not in resolver
