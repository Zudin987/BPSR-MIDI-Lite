"""Tiny worker executed inside Studio's isolated spotDL runtime.

Search intentionally uses Spotify's raw search payload instead of hydrating each
result through ``Song.from_url``.  Hydrating ten results can fan one title search
out into dozens of track/artist/album requests and makes the desktop look hung.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _clean(value: Any, maximum: int = 300) -> str:
    return " ".join(str(value or "").split())[:maximum]


def _raw_track_payload(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one Spotify search item using data already in that response."""
    if not isinstance(item, dict):
        raise TypeError("Spotify returned malformed track metadata")
    track_id = _clean(item.get("id"), 100)
    title = _clean(item.get("name"))
    if not track_id or not title:
        raise ValueError("Spotify returned a track without an id or title")

    artists_raw = item.get("artists")
    artists = []
    if isinstance(artists_raw, list):
        for artist in artists_raw:
            if isinstance(artist, dict):
                name = _clean(artist.get("name"), 120)
            else:
                name = _clean(artist, 120)
            if name:
                artists.append(name)

    album = item.get("album") if isinstance(item.get("album"), dict) else {}
    external_urls = item.get("external_urls") if isinstance(item.get("external_urls"), dict) else {}
    external_ids = item.get("external_ids") if isinstance(item.get("external_ids"), dict) else {}
    duration_ms = item.get("duration_ms")
    try:
        duration = max(0.0, float(duration_ms) / 1000.0) if duration_ms is not None else None
    except (TypeError, ValueError):
        duration = None

    return {
        "song_id": track_id,
        "name": title,
        "artists": artists,
        "artist": artists[0] if artists else "",
        "album_name": _clean(album.get("name")),
        "duration": duration,
        "isrc": _clean(external_ids.get("isrc"), 32),
        "date": _clean(album.get("release_date"), 32),
        "url": _clean(external_urls.get("spotify"), 1000)
        or f"https://open.spotify.com/track/{track_id}",
    }


def _track_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    tracks = value.get("tracks")
    if not isinstance(tracks, dict):
        return []
    items = tracks.get("items")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: spotdl_worker.py REQUEST.json RESPONSE.json", file=sys.stderr)
        return 2
    request_path, response_path = map(Path, args)
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        query = " ".join(str(request.get("query", "")).split())[:240]
        limit = max(1, min(20, int(request.get("limit", 10))))
        if len(query) < 2:
            raise ValueError("Type at least two characters to search for a song.")

        from spotdl.types.song import Song
        from spotdl.utils.spotify import SpotifyClient

        # spotDL 4.5+ defaults to its no-user-login SpotipyFree metadata path
        # when client credentials are empty. No Spotify account is required for
        # normal track search.
        SpotifyClient.init(client_id="", client_secret="")
        client = SpotifyClient()
        if query.startswith("https://open.spotify.com/track/"):
            raw = client.track(query)
            items = [raw] if isinstance(raw, dict) else []
        else:
            # One Spotify request is enough. Song.list_from_search_term() would
            # re-fetch track + artist + album data for every result and was the
            # source of the long beta.4 search delay.
            items = _track_items(Song.search(query))

        payload = []
        for item in items:
            try:
                payload.append(_raw_track_payload(item))
            except (TypeError, ValueError):
                continue
            if len(payload) >= limit:
                break
        response = {"ok": True, "tracks": payload}
    except Exception as exc:  # worker boundary: return a compact user-facing error
        response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    temporary = response_path.with_suffix(response_path.suffix + ".tmp")
    temporary.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
    temporary.replace(response_path)
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
