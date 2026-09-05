"""Tiny worker executed inside Studio's isolated spotDL runtime."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _song_payload(song) -> dict:
    value = song.json
    if not isinstance(value, dict):
        raise TypeError("spotDL returned malformed song metadata")
    return value


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
        if query.startswith("https://open.spotify.com/track/"):
            songs = [Song.from_url(query)]
        else:
            songs = Song.list_from_search_term(query)
        payload = [_song_payload(song) for song in list(songs)[:limit]]
        response = {"ok": True, "tracks": payload}
    except Exception as exc:  # worker boundary: return a compact user-facing error
        response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    temporary = response_path.with_suffix(response_path.suffix + ".tmp")
    temporary.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
    temporary.replace(response_path)
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
