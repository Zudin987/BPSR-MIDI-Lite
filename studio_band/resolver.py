"""Legal music discovery and entitled-audio acquisition for Studio.

Discovery metadata and audio delivery are deliberately separate. Apple results
never expose preview audio to the analysis pipeline. Full audio is accepted only
from a user's Bandcamp collection or a MassiveMusic/7digital partner download
endpoint that verifies the user's entitlement. Local files remain the default.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, quote_plus, urlencode, urlsplit
from urllib.request import Request, urlopen

from .protocol import check_cancel
from .storage import atomic_json, data_root, file_hash, file_lock, read_json

USER_AGENT = "BPSR-MIDI-Studio/0.5"
APPLE_API = "https://api.music.apple.com"
APPLE_PUBLIC_SEARCH = "https://itunes.apple.com/search"
MASSIVE_SEARCH = "https://api.7digital.com/track/search"
MASSIVE_DOWNLOAD = "https://media.geo.7digital.com/media/user/downloadtrack"
BANDCAMP_SUBSONIC = "https://bandcamp.com/api/subsonic"
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_AUDIO_BYTES = 2 * 1024**3
SUPPORTED_SUFFIXES = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}
CONTENT_SUFFIXES = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/flac": ".flac",
    "audio/x-flac": ".flac",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/wav": ".wav",
    "audio/wave": ".wav",
    "audio/x-wav": ".wav",
    "audio/ogg": ".ogg",
    "application/ogg": ".ogg",
}


class ResolverError(RuntimeError):
    """A user-actionable discovery or acquisition failure."""


def _clean(value: Any, maximum: int = 240) -> str:
    return " ".join(str(value or "").split())[:maximum]


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("track", "song", "package", "format"):
            if key in value:
                return _as_list(value[key])
        return [value]
    return []


def _safe_store_url(value: Any, hosts: tuple[str, ...]) -> str:
    url = _clean(value, 1000)
    try:
        parsed = urlsplit(url)
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not any(host == item or host.endswith("." + item) for item in hosts):
        return ""
    return url


def _audio_signature_matches(path: Path, suffix: str) -> bool:
    try:
        with path.open("rb") as stream:
            head = stream.read(16)
    except OSError:
        return False
    if suffix == ".mp3":
        return head.startswith(b"ID3") or len(head) >= 2 and head[0] == 0xff and head[1] & 0xe0 == 0xe0
    if suffix == ".flac":
        return head.startswith(b"fLaC")
    if suffix == ".wav":
        return head.startswith(b"RIFF") and head[8:12] == b"WAVE"
    if suffix == ".ogg":
        return head.startswith(b"OggS")
    if suffix == ".m4a":
        return len(head) >= 8 and head[4:8] == b"ftyp"
    return False


@dataclass(slots=True)
class ResolverConfig:
    storefront: str = "MY"
    apple_token: str = field(default="", repr=False)
    massive_consumer_key: str = field(default="", repr=False)
    massive_consumer_secret: str = field(default="", repr=False)
    massive_user_id: str = field(default="", repr=False)
    massive_user_token: str = field(default="", repr=False)
    massive_user_token_secret: str = field(default="", repr=False)
    bandcamp_username: str = field(default="", repr=False)
    bandcamp_password: str = field(default="", repr=False)
    bandcamp_api_key: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        country = _clean(self.storefront, 2).upper()
        if len(country) != 2 or not country.isalpha():
            raise ValueError("Storefront must be a two-letter country code such as MY or ID")
        self.storefront = country

    @classmethod
    def from_environment(cls, storefront: str | None = None) -> "ResolverConfig":
        return cls(
            storefront=storefront or os.environ.get("BPSR_MUSIC_STOREFRONT", "MY"),
            apple_token=os.environ.get("BPSR_APPLE_MUSIC_TOKEN", "").strip(),
            massive_consumer_key=os.environ.get("BPSR_MASSIVEMUSIC_CONSUMER_KEY", "").strip(),
            massive_consumer_secret=os.environ.get("BPSR_MASSIVEMUSIC_CONSUMER_SECRET", "").strip(),
            massive_user_id=os.environ.get("BPSR_MASSIVEMUSIC_USER_ID", "").strip(),
            massive_user_token=os.environ.get("BPSR_MASSIVEMUSIC_USER_TOKEN", "").strip(),
            massive_user_token_secret=os.environ.get("BPSR_MASSIVEMUSIC_USER_TOKEN_SECRET", "").strip(),
            bandcamp_username=os.environ.get("BPSR_BANDCAMP_USERNAME", "").strip(),
            bandcamp_password=os.environ.get("BPSR_BANDCAMP_PASSWORD", "").strip(),
            bandcamp_api_key=os.environ.get("BPSR_BANDCAMP_API_KEY", "").strip(),
        )

    @property
    def bandcamp_ready(self) -> bool:
        return bool(self.bandcamp_api_key or self.bandcamp_username and self.bandcamp_password)

    @property
    def massive_download_ready(self) -> bool:
        return bool(self.massive_consumer_key and self.massive_consumer_secret and self.massive_user_id)


@dataclass(frozen=True, slots=True)
class ResolverTrack:
    provider: str
    provider_id: str
    title: str
    artist: str = ""
    album: str = ""
    duration_seconds: float | None = None
    isrc: str = ""
    release_date: str = ""
    store_url: str = ""
    acquisition: str = "metadata_only"
    can_acquire: bool = False
    release_id: str = ""
    format_id: str = ""
    suffix: str = ".mp3"

    def public_metadata(self) -> dict[str, Any]:
        """Return manifest-safe provenance; credentials and preview URLs never enter it."""
        return {
            "input_mode": "provider",
            "provider": self.provider,
            "provider_id": self.provider_id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration_seconds": self.duration_seconds,
            "isrc": self.isrc or None,
            "release_date": self.release_date or None,
            "store_url": self.store_url or None,
            "acquisition": self.acquisition,
        }


@dataclass(slots=True)
class SearchReport:
    tracks: list[ResolverTrack]
    warnings: list[str]


@dataclass(slots=True)
class AcquiredAudio:
    path: Path
    metadata: dict[str, Any]


class AcquisitionStore:
    """Small verified cache for entitled downloads; no credentials are stored."""

    def __init__(self, root: Path | None = None):
        self.root = root or data_root() / "acquired-audio"
        self.audio = self.root / "audio"
        self.records = self.root / "records"
        self.audio.mkdir(parents=True, exist_ok=True)
        self.records.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(track: ResolverTrack) -> str:
        value = "\0".join((track.provider, track.provider_id, track.release_id, track.format_id))
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def cached(self, track: ResolverTrack) -> Path | None:
        try:
            record = read_json(self.records / (self.key(track) + ".json"))
            path = (self.audio / record["file"]).resolve()
            if not path.is_relative_to(self.audio.resolve()) or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                return None
            if not path.is_file() or path.stat().st_size != record["size"] or file_hash(path) != record["sha256"]:
                return None
            os.utime(path, None)
            return path
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def commit(self, track: ResolverTrack, temporary: Path, suffix: str, digest: str, size: int) -> Path:
        if suffix not in SUPPORTED_SUFFIXES or size <= 0 or len(digest) != 64:
            raise ResolverError("The provider returned an unsupported audio file.")
        target = self.audio / (digest + suffix)
        if target.exists() and (target.stat().st_size != size or file_hash(target) != digest):
            raise ResolverError("The local acquisition cache contains a conflicting file.")
        if target.exists():
            temporary.unlink(missing_ok=True)
        else:
            os.replace(temporary, target)
        atomic_json(self.records / (self.key(track) + ".json"), {
            "file": target.name,
            "sha256": digest,
            "size": size,
            "source": track.public_metadata(),
        })
        return target

    def cleanup(self, days: int = 14, max_bytes: int = 20 * 1024**3) -> int:
        files = sorted((p for p in self.audio.iterdir() if p.is_file() and not p.is_symlink()),
                       key=lambda p: p.stat().st_mtime)
        total, removed = sum(p.stat().st_size for p in files), 0
        cutoff = time.time() - days * 86400
        for path in files:
            if path.stat().st_mtime >= cutoff and total <= max_bytes:
                continue
            size = path.stat().st_size
            try:
                path.unlink()
                total -= size
                removed += 1
            except OSError:
                continue
        for record in self.records.glob("*.json"):
            try:
                value = read_json(record)
                if not (self.audio / value["file"]).is_file():
                    record.unlink()
            except (OSError, ValueError, KeyError, TypeError):
                record.unlink(missing_ok=True)
        return removed


def _json_get(url: str, *, headers: dict[str, str] | None = None, timeout: float = 25) -> dict[str, Any]:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ResolverError("Music providers must use HTTPS.")
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                                    "Accept-Encoding": "identity", **(headers or {})})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed provider endpoints
            data = response.read(MAX_JSON_BYTES + 1)
    except HTTPError as exc:
        raise ResolverError(f"The provider rejected the request (HTTP {exc.code}).") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ResolverError("The music provider could not be reached.") from exc
    if len(data) > MAX_JSON_BYTES:
        raise ResolverError("The provider response was unexpectedly large.")
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResolverError("The provider returned an invalid response.") from exc
    if not isinstance(value, dict):
        raise ResolverError("The provider returned an invalid response.")
    return value


def parse_apple_music(value: dict[str, Any]) -> list[ResolverTrack]:
    results = value.get("results")
    songs_container = results.get("songs") if isinstance(results, dict) else {}
    songs = songs_container.get("data", []) if isinstance(songs_container, dict) else []
    tracks: list[ResolverTrack] = []
    for item in _as_list(songs):
        attributes = item.get("attributes", {}) if isinstance(item, dict) else {}
        title, artist = _clean(attributes.get("name")), _clean(attributes.get("artistName"))
        if not title:
            continue
        duration = _number(attributes.get("durationInMillis"))
        tracks.append(ResolverTrack(
            "apple_music", _clean(item.get("id"), 100), title, artist,
            _clean(attributes.get("albumName")), duration / 1000 if duration is not None else None,
            _clean(attributes.get("isrc"), 32).upper(), _clean(attributes.get("releaseDate"), 32),
            _safe_store_url(attributes.get("url"), ("music.apple.com",)),
            "metadata_only", False,
        ))
    return tracks


def parse_itunes(value: dict[str, Any]) -> list[ResolverTrack]:
    tracks: list[ResolverTrack] = []
    for item in _as_list(value.get("results")):
        if not isinstance(item, dict) or item.get("kind") not in (None, "song"):
            continue
        title, artist = _clean(item.get("trackName")), _clean(item.get("artistName"))
        if not title:
            continue
        duration = _number(item.get("trackTimeMillis"))
        tracks.append(ResolverTrack(
            "apple_catalog", _clean(item.get("trackId"), 100), title, artist,
            _clean(item.get("collectionName")), duration / 1000 if duration is not None else None,
            "", _clean(item.get("releaseDate"), 32),
            _safe_store_url(item.get("trackViewUrl"), ("apple.com", "itunes.apple.com")),
            "metadata_only", False,
        ))
    return tracks


def _massive_formats(item: dict[str, Any]) -> list[tuple[int, str]]:
    download = item.get("download")
    packages = item.get("packages") or (download.get("packages") if isinstance(download, dict) else None)
    formats: list[tuple[int, str]] = []
    for package in _as_list(packages):
        if not isinstance(package, dict):
            continue
        for value in _as_list(package.get("formats")):
            if not isinstance(value, dict):
                continue
            try:
                format_id = int(value.get("id"))
            except (TypeError, ValueError):
                continue
            formats.append((format_id, _clean(value.get("name") or value.get("description"), 80)))
    return formats


def _preferred_format(formats: list[tuple[int, str]]) -> tuple[str, str]:
    ranked = []
    for format_id, name in formats:
        lower = name.casefold()
        suffix = ".flac" if "flac" in lower else ".mp3" if "mp3" in lower else ""
        if not suffix:
            continue
        score = (400 if "24" in lower and suffix == ".flac" else
                 300 if suffix == ".flac" else
                 220 if "320" in lower else 200)
        ranked.append((score, str(format_id), suffix))
    if not ranked:
        return "", ".mp3"
    _, format_id, suffix = max(ranked)
    return format_id, suffix


def parse_massive(value: dict[str, Any], config: ResolverConfig) -> list[ResolverTrack]:
    container = value.get("response", value)
    if not isinstance(container, dict):
        return []
    results = container.get("results") or container.get("searchResults") or []
    if isinstance(results, dict) and "searchResult" in results:
        results = results["searchResult"]
    tracks: list[ResolverTrack] = []
    for item in _as_list(results):
        if not isinstance(item, dict):
            continue
        title = _clean(item.get("title"))
        artist_record = item.get("artist")
        artist = _clean(artist_record.get("name") if isinstance(artist_record, dict) else "")
        release = item.get("release") or {}
        if not isinstance(release, dict):
            release = {}
        if not title:
            continue
        available = {str(x).casefold() for x in _as_list(item.get("availableFor"))}
        format_id, suffix = _preferred_format(_massive_formats(item))
        downloadable = "download" in available or bool(_massive_formats(item))
        can_acquire = bool(downloadable and format_id and config.massive_download_ready)
        tracks.append(ResolverTrack(
            "massive_music", _clean(item.get("id"), 100), title, artist,
            _clean(release.get("title")), _number(item.get("duration")),
            _clean(item.get("isrc"), 32).upper(), _clean(item.get("releaseDate"), 32),
            "https://www.7digital.com/search?q=" + quote_plus(" ".join(x for x in (artist, title) if x)),
            "entitled_partner_download" if can_acquire else "catalogue_only",
            can_acquire, _clean(release.get("id"), 100), format_id, suffix,
        ))
    return tracks


def _subsonic_response(value: dict[str, Any]) -> dict[str, Any]:
    response = value.get("subsonic-response")
    if not isinstance(response, dict):
        raise ResolverError("Bandcamp returned an invalid Subsonic response.")
    if response.get("status") != "ok":
        error = response.get("error") or {}
        message = _clean(error.get("message") if isinstance(error, dict) else error, 160) or "the credentials or request were rejected"
        raise ResolverError("Bandcamp: " + message + ".")
    return response


def parse_bandcamp(value: dict[str, Any]) -> list[ResolverTrack]:
    response = _subsonic_response(value)
    search = response.get("searchResult3") or {}
    songs = (search.get("song") if isinstance(search, dict) else []) or []
    tracks: list[ResolverTrack] = []
    for song in _as_list(songs):
        if not isinstance(song, dict):
            continue
        title, provider_id = _clean(song.get("title")), _clean(song.get("id"), 200)
        if not title or not provider_id:
            continue
        suffix = "." + _clean(song.get("suffix"), 8).lower().lstrip(".")
        if suffix not in SUPPORTED_SUFFIXES:
            suffix = CONTENT_SUFFIXES.get(_clean(song.get("contentType"), 80).lower(), ".flac")
        artist = _clean(song.get("artist"))
        tracks.append(ResolverTrack(
            "bandcamp_collection", provider_id, title, artist, _clean(song.get("album")),
            _number(song.get("duration")), _clean(song.get("isrc"), 32).upper(),
            _clean(song.get("created"), 32),
            "https://bandcamp.com/search?q=" + quote_plus(" ".join(x for x in (artist, title) if x)),
            "owned_collection_download", True, suffix=suffix,
        ))
    return tracks


def _oauth_quote(value: Any) -> str:
    return quote(str(value), safe="~-._")


def oauth1_signed_url(base_url: str, parameters: dict[str, Any], config: ResolverConfig,
                      *, nonce: str | None = None, timestamp: int | None = None) -> str:
    """Create a MassiveMusic OAuth 1.0 HMAC-SHA1 query without exposing secrets."""
    if not config.massive_consumer_key or not config.massive_consumer_secret:
        raise ResolverError("MassiveMusic download credentials are incomplete.")
    values = {str(key): str(value) for key, value in parameters.items()}
    values.update({
        "oauth_consumer_key": config.massive_consumer_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(timestamp or int(time.time())),
        "oauth_version": "1.0",
    })
    if config.massive_user_token and config.massive_user_token_secret:
        values["oauth_token"] = config.massive_user_token
    normalized = "&".join(f"{_oauth_quote(key)}={_oauth_quote(value)}" for key, value in sorted(values.items()))
    base = "&".join((_oauth_quote("GET"), _oauth_quote(base_url), _oauth_quote(normalized)))
    key = _oauth_quote(config.massive_consumer_secret) + "&" + _oauth_quote(config.massive_user_token_secret)
    signature = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    values["oauth_signature"] = signature
    return base_url + "?" + urlencode(values)


class MusicResolver:
    def __init__(self, config: ResolverConfig | None = None, store: AcquisitionStore | None = None):
        self.config = config or ResolverConfig.from_environment()
        self.store = store or AcquisitionStore()
        self._search_cache: dict[tuple[str, str], tuple[float, SearchReport]] = {}

    def search(self, query: str, *, limit: int = 10, cancel=None,
               progress: Callable[[str], None] | None = None) -> SearchReport:
        query = _clean(query, 160)
        if len(query) < 2:
            raise ResolverError("Type at least two characters to search for a song.")
        limit = max(1, min(20, int(limit)))
        cache_key = (self.config.storefront, query.casefold())
        cached = self._search_cache.get(cache_key)
        if cached and time.time() - cached[0] < 10 * 60:
            return cached[1]
        check_cancel(cancel)
        if progress:
            progress(f"Searching {self.config.storefront} music sources…")
        warnings: list[str] = []
        jobs: list[tuple[str, Callable[[], tuple[list[ResolverTrack], list[str]]]]] = [
            ("Apple", lambda: self._search_apple(query, limit)),
        ]
        if self.config.massive_consumer_key:
            jobs.append(("MassiveMusic", lambda: (self._search_massive(query, limit), [])))
        else:
            warnings.append("MassiveMusic catalogue search needs a commercial consumer key.")
        if self.config.bandcamp_ready:
            jobs.append(("Bandcamp", lambda: (self._search_bandcamp(query, limit), [])))
        else:
            warnings.append("Bandcamp collection search needs Subsonic credentials from Fan Settings.")
        results: dict[str, list[ResolverTrack]] = {}
        with ThreadPoolExecutor(max_workers=len(jobs), thread_name_prefix="music-source") as pool:
            futures = {name: pool.submit(action) for name, action in jobs}
            for name, _ in jobs:
                try:
                    tracks, provider_warnings = futures[name].result()
                    results[name] = tracks
                    warnings.extend(provider_warnings)
                except (ResolverError, ValueError, KeyError, TypeError, AttributeError) as exc:
                    warnings.append(f"{name}: {exc}")
        check_cancel(cancel)
        combined: list[ResolverTrack] = []
        seen: set[tuple[str, str]] = set()
        for name, _ in jobs:
            for track in results.get(name, []):
                identity = (track.provider, track.provider_id)
                if identity in seen:
                    continue
                seen.add(identity)
                combined.append(track)
        if not combined:
            raise ResolverError("No songs matched. Try the exact title and artist, or choose a local audio file.")
        report = SearchReport(combined, warnings)
        self._search_cache[cache_key] = (time.time(), report)
        return report

    def _search_apple(self, query: str, limit: int) -> tuple[list[ResolverTrack], list[str]]:
        if self.config.apple_token:
            url = APPLE_API + f"/v1/catalog/{self.config.storefront.lower()}/search?" + urlencode({
                "term": query, "types": "songs", "limit": limit, "l": "en-GB",
            })
            try:
                return parse_apple_music(_json_get(url, headers={
                    "Authorization": "Bearer " + self.config.apple_token,
                })), []
            except ResolverError as exc:
                fallback = self._search_itunes(query, limit)
                return fallback, [f"Apple Music developer-token search failed ({exc}); used public Apple catalogue metadata."]
        return self._search_itunes(query, limit), [
            "Apple public catalogue metadata is active; add a developer token for MusicKit ISRC metadata."
        ]

    def _search_itunes(self, query: str, limit: int) -> list[ResolverTrack]:
        url = APPLE_PUBLIC_SEARCH + "?" + urlencode({
            "term": query, "country": self.config.storefront, "media": "music",
            "entity": "song", "limit": limit,
        })
        return parse_itunes(_json_get(url))

    def _search_massive(self, query: str, limit: int) -> list[ResolverTrack]:
        url = MASSIVE_SEARCH + "?" + urlencode({
            "q": query, "oauth_consumer_key": self.config.massive_consumer_key,
            "country": self.config.storefront, "pageSize": limit,
            "usageTypes": "download", "format": "json",
        })
        return parse_massive(_json_get(url), self.config)

    def _subsonic_auth(self) -> dict[str, str]:
        common = {"v": "1.16.1", "c": "BPSRMIDIStudio"}
        if self.config.bandcamp_api_key:
            return {**common, "apiKey": self.config.bandcamp_api_key}
        if not self.config.bandcamp_username or not self.config.bandcamp_password:
            raise ResolverError("Bandcamp Subsonic credentials are incomplete.")
        salt = secrets.token_hex(8)
        token = hashlib.md5((self.config.bandcamp_password + salt).encode(), usedforsecurity=False).hexdigest()  # noqa: S324 - required Subsonic challenge
        return {**common, "u": self.config.bandcamp_username, "t": token, "s": salt}

    def _search_bandcamp(self, query: str, limit: int) -> list[ResolverTrack]:
        params = {**self._subsonic_auth(), "f": "json", "query": query,
                  "songCount": limit, "albumCount": 0, "artistCount": 0}
        url = BANDCAMP_SUBSONIC + "/rest/search3.view?" + urlencode(params)
        return parse_bandcamp(_json_get(url))

    def acquire(self, track: ResolverTrack, *, cancel=None,
                progress: Callable[[str], None] | None = None) -> AcquiredAudio:
        if not track.can_acquire:
            raise ResolverError("This result is discovery-only. Open its provider, obtain an authorised audio file, then choose it locally.")
        cached = self.store.cached(track)
        if cached:
            if progress:
                progress("Using verified cached audio…")
            metadata = track.public_metadata()
            metadata["audio_sha256"] = file_hash(cached)
            return AcquiredAudio(cached, metadata)
        check_cancel(cancel)
        if track.provider == "bandcamp_collection":
            params = {**self._subsonic_auth(), "id": track.provider_id}
            url = BANDCAMP_SUBSONIC + "/rest/download.view?" + urlencode(params)
        elif track.provider == "massive_music":
            if not self.config.massive_download_ready:
                raise ResolverError("MassiveMusic purchased-download credentials are incomplete.")
            url = oauth1_signed_url(MASSIVE_DOWNLOAD, {
                "trackId": track.provider_id,
                "releaseId": track.release_id,
                "formatId": track.format_id,
                "country": self.config.storefront,
                "userId": self.config.massive_user_id,
                "errorUrl": "https://github.com/Zudin987/BPSR-MIDI-Lite",
            }, self.config)
        else:
            raise ResolverError("This provider does not permit automatic audio acquisition.")
        if progress:
            progress("Downloading authorised full audio…")
        path = self._download(track, url, cancel=cancel)
        metadata = track.public_metadata()
        metadata["audio_sha256"] = file_hash(path)
        return AcquiredAudio(path, metadata)

    def _download(self, track: ResolverTrack, url: str, *, cancel=None) -> Path:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in {"bandcamp.com", "media.geo.7digital.com"}:
            raise ResolverError("The audio provider endpoint is not trusted.")
        with file_lock(self.store.root / "download.lock"):
            cached = self.store.cached(track)
            if cached:
                return cached
            temporary = self.store.root / ("." + uuid.uuid4().hex + ".part")
            digest, size = hashlib.sha256(), 0
            request = Request(url, headers={"User-Agent": USER_AGENT,
                                            "Accept": "audio/*, application/octet-stream",
                                            "Accept-Encoding": "identity"})
            try:
                try:
                    response = urlopen(request, timeout=60)  # noqa: S310 - trusted endpoints above
                except HTTPError as exc:
                    raise ResolverError(f"The audio provider rejected the download (HTTP {exc.code}).") from exc
                except (URLError, TimeoutError, OSError) as exc:
                    raise ResolverError("The authorised audio download could not be reached.") from exc
                with response:
                    final = urlsplit(response.geturl())
                    if final.scheme != "https":
                        raise ResolverError("The provider redirected to an insecure download.")
                    length = response.headers.get("Content-Length")
                    if length:
                        try:
                            if int(length) > MAX_AUDIO_BYTES:
                                raise ResolverError("The provider audio is larger than 2 GB.")
                        except ValueError:
                            pass
                    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                    if content_type.startswith("text/") or content_type in {"application/json", "application/xml"}:
                        raise ResolverError("The account does not have an entitled audio download for this result.")
                    suffix = CONTENT_SUFFIXES.get(content_type, track.suffix.lower())
                    if suffix not in SUPPORTED_SUFFIXES:
                        raise ResolverError("The provider's original format is not supported; download it manually and convert it to WAV.")
                    with temporary.open("wb") as output:
                        while True:
                            check_cancel(cancel)
                            chunk = response.read(1024 * 1024)
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > MAX_AUDIO_BYTES:
                                raise ResolverError("The provider audio is larger than 2 GB.")
                            digest.update(chunk)
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
                if size <= 0:
                    raise ResolverError("The provider returned an empty audio file.")
                if not _audio_signature_matches(temporary, suffix):
                    raise ResolverError("The provider response was not a valid supported audio file.")
                return self.store.commit(track, temporary, suffix, digest.hexdigest(), size)
            finally:
                temporary.unlink(missing_ok=True)


def query_from_signed_url(url: str) -> dict[str, list[str]]:
    """Testing/diagnostic helper that never decodes or returns secret keys."""
    return parse_qs(urlsplit(url).query, keep_blank_values=True)
