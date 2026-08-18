from __future__ import annotations

import html
import json
import re
import shutil
import struct
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

import mido


BASE_URL = "https://onlinesequencer.net"
SEARCH_URL = BASE_URL + "/sequences?search={query}"
PROTO_URL = BASE_URL + "/app/api/get_proto.php?id={sequence_id}"
SEQUENCE_URL = BASE_URL + "/{sequence_id}"
USER_AGENT = "BPSR-MIDI-Lite/3.0 (+https://github.com/Zudin987/BPSR-MIDI-Lite)"

MAX_SEARCH_RESULTS = 12
MAX_SEARCH_BYTES = 2 * 1024 * 1024
MAX_PROTO_BYTES = 16 * 1024 * 1024
MAX_SEQUENCE_NOTES = 75_000
CACHE_MAX_AGE_SECONDS = 3 * 24 * 60 * 60
CACHE_MAX_BYTES = 96 * 1024 * 1024

# Online Sequencer instrument IDs treated as drum kits by its official
# SequencePlayer implementation. Writing them to MIDI channel 10 lets the
# existing BPSR planner's normal "ignore percussion" behavior keep working.
DRUM_INSTRUMENT_IDS = {2, 31, 36, 39, 40, 42, 53}

_SEQUENCE_LINK_RE = re.compile(
    r'href=["\'](?:https?://onlinesequencer\.net)?/(\d+)(?:[?#][^"\']*)?["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_NOTE_COUNT_RE = re.compile(r"([\d,]+)\s+notes?\b", re.IGNORECASE)
_AUTHOR_RE = re.compile(r"\bby\s*<a[^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_INVALID_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class OnlineSequencerError(RuntimeError):
    """A friendly failure from the optional Online Sequencer integration."""


class SequenceTooLargeError(OnlineSequencerError):
    def __init__(self, note_count: int) -> None:
        self.note_count = note_count
        super().__init__(
            f"This sequence has {note_count:,} notes and is too large for safe automatic BPSR analysis."
        )


@dataclass(frozen=True, slots=True)
class SearchResult:
    sequence_id: int
    title: str
    author: str = ""
    note_count: int | None = None

    @property
    def url(self) -> str:
        return sequence_url(self.sequence_id)


@dataclass(frozen=True, slots=True)
class CachedSequence:
    sequence_id: int
    path: Path
    title: str
    author: str
    note_count: int
    percussion_notes: int
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class _ProtoNote:
    type_value: int
    time: float
    length: float
    instrument: int
    volume: float


@dataclass(frozen=True, slots=True)
class _TempoMarker:
    time: float
    bpm: float


def sequence_url(sequence_id: int) -> str:
    return SEQUENCE_URL.format(sequence_id=int(sequence_id))


def cache_directory() -> Path:
    root = Path(tempfile.gettempdir()) / "BPSR-MIDI-Lite" / "OnlineSequencer"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _clean_text(fragment: str) -> str:
    text = _TAG_RE.sub(" ", fragment)
    text = html.unescape(text)
    return " ".join(text.split()).strip()


def parse_sequence_reference(text: str) -> int | None:
    """Return an Online Sequencer ID from a pasted ID/URL, otherwise None."""
    value = text.strip()
    if value.isdigit():
        sequence_id = int(value)
        return sequence_id if sequence_id > 0 else None

    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    if parsed.netloc.casefold() not in {"onlinesequencer.net", "www.onlinesequencer.net"}:
        return None
    match = re.fullmatch(r"/(\d+)/?", parsed.path)
    if not match:
        return None
    sequence_id = int(match.group(1))
    return sequence_id if sequence_id > 0 else None


def parse_search_results(page_html: str, limit: int = MAX_SEARCH_RESULTS) -> list[SearchResult]:
    """Parse public sequence cards without depending on one CSS class name."""
    results: list[SearchResult] = []
    seen: set[int] = set()

    for match in _SEQUENCE_LINK_RE.finditer(page_html):
        sequence_id = int(match.group(1))
        if sequence_id in seen:
            continue
        title = _clean_text(match.group(2))
        if not title or title.casefold() in {"play", "open", "sequence"}:
            continue

        # Metadata sits close to the sequence link on the public browser page.
        # Keep this deliberately best-effort; title + ID are sufficient to use
        # a result even if Online Sequencer changes the surrounding markup.
        nearby = page_html[match.end() : match.end() + 1200]
        author_match = _AUTHOR_RE.search(nearby)
        author = _clean_text(author_match.group(1)) if author_match else ""
        count_match = _NOTE_COUNT_RE.search(_clean_text(nearby))
        note_count = int(count_match.group(1).replace(",", "")) if count_match else None

        seen.add(sequence_id)
        results.append(SearchResult(sequence_id, title[:160], author[:80], note_count))
        if len(results) >= max(1, int(limit)):
            break

    return results


def _request_bytes(url: str, *, timeout: float, max_bytes: int) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Encoding": "identity",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS host
            length = response.headers.get("Content-Length")
            if length:
                try:
                    if int(length) > max_bytes:
                        raise OnlineSequencerError("Online Sequencer returned a file that is too large.")
                except ValueError:
                    pass
            data = response.read(max_bytes + 1)
    except HTTPError as exc:
        if exc.code == 404:
            raise OnlineSequencerError("That Online Sequencer sequence was not found.") from exc
        raise OnlineSequencerError(f"Online Sequencer returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise OnlineSequencerError("Could not reach Online Sequencer. Check your internet connection and try again.") from exc

    if len(data) > max_bytes:
        raise OnlineSequencerError("Online Sequencer returned a file that is too large.")
    return data


def search_sequences(query: str, limit: int = MAX_SEARCH_RESULTS) -> list[SearchResult]:
    value = query.strip()
    direct_id = parse_sequence_reference(value)
    if direct_id is not None:
        title, author = fetch_sequence_page_metadata(direct_id)
        return [SearchResult(direct_id, title or f"Sequence #{direct_id}", author)]
    if len(value) < 3:
        raise OnlineSequencerError("Enter at least 3 characters, or paste an Online Sequencer link / sequence ID.")

    data = _request_bytes(
        SEARCH_URL.format(query=quote_plus(value)),
        timeout=8.0,
        max_bytes=MAX_SEARCH_BYTES,
    )
    page = data.decode("utf-8", errors="replace")
    results = parse_search_results(page, limit=limit)
    if not results:
        raise OnlineSequencerError("No public Online Sequencer songs matched that search.")
    return results


def fetch_sequence_page_metadata(sequence_id: int) -> tuple[str, str]:
    """Best-effort title/author lookup for a directly pasted sequence ID."""
    try:
        data = _request_bytes(sequence_url(sequence_id), timeout=6.0, max_bytes=MAX_SEARCH_BYTES)
    except OnlineSequencerError:
        return f"Sequence #{sequence_id}", ""
    page = data.decode("utf-8", errors="replace")

    title = ""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", page, re.IGNORECASE | re.DOTALL)
    if title_match:
        title = _clean_text(title_match.group(1))
        title = re.sub(r"\s*-\s*Online Sequencer\s*$", "", title, flags=re.IGNORECASE).strip()

    author = ""
    # Sequence pages commonly render "<title> by <username>" near the heading.
    author_match = re.search(r"\bby\s*<a[^>]*>(.*?)</a>", page, re.IGNORECASE | re.DOTALL)
    if author_match:
        author = _clean_text(author_match.group(1))

    return (title or f"Sequence #{sequence_id}")[:160], author[:80]


def _read_varint(data: bytes, index: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while index < len(data) and shift <= 63:
        byte = data[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, index
        shift += 7
    raise OnlineSequencerError("Online Sequencer returned malformed sequence data.")


def _wire_fields(data: bytes) -> Iterable[tuple[int, int, object]]:
    index = 0
    while index < len(data):
        key, index = _read_varint(data, index)
        field = key >> 3
        wire = key & 7
        if field <= 0:
            raise OnlineSequencerError("Online Sequencer returned malformed sequence data.")

        if wire == 0:
            value, index = _read_varint(data, index)
            yield field, wire, value
        elif wire == 1:
            if index + 8 > len(data):
                raise OnlineSequencerError("Online Sequencer returned truncated sequence data.")
            value = data[index : index + 8]
            index += 8
            yield field, wire, value
        elif wire == 2:
            length, index = _read_varint(data, index)
            if length < 0 or index + length > len(data):
                raise OnlineSequencerError("Online Sequencer returned truncated sequence data.")
            value = data[index : index + length]
            index += length
            yield field, wire, value
        elif wire == 5:
            if index + 4 > len(data):
                raise OnlineSequencerError("Online Sequencer returned truncated sequence data.")
            value = data[index : index + 4]
            index += 4
            yield field, wire, value
        else:
            raise OnlineSequencerError(f"Unsupported protobuf wire type {wire} in Online Sequencer data.")


def _as_float(raw: object) -> float:
    if not isinstance(raw, (bytes, bytearray)) or len(raw) != 4:
        raise OnlineSequencerError("Online Sequencer returned an invalid floating-point field.")
    return float(struct.unpack("<f", bytes(raw))[0])


def _parse_note(payload: bytes) -> _ProtoNote:
    type_value = 0
    note_time = 0.0
    length = 1.0
    instrument = 0
    volume = 1.0
    for field, wire, value in _wire_fields(payload):
        if field == 1 and wire == 0:
            type_value = int(value)
        elif field == 2 and wire == 5:
            note_time = _as_float(value)
        elif field == 3 and wire == 5:
            length = _as_float(value)
        elif field == 4 and wire == 0:
            instrument = int(value)
        elif field == 5 and wire == 5:
            volume = _as_float(value)
    return _ProtoNote(type_value, max(0.0, note_time), max(0.001, length), instrument, volume)


def _parse_settings_bpm(payload: bytes) -> float:
    bpm = 120.0
    for field, wire, value in _wire_fields(payload):
        if field == 1 and wire == 0:
            bpm = float(int(value))
            break
    return bpm if bpm > 0 else 120.0


def _parse_marker(payload: bytes) -> _TempoMarker | None:
    marker_time = 0.0
    setting = -1
    instrument = -1
    marker_value = 0.0
    for field, wire, value in _wire_fields(payload):
        if field == 1 and wire == 5:
            marker_time = _as_float(value)
        elif field == 2 and wire == 0:
            setting = int(value)
        elif field == 3 and wire == 0:
            instrument = int(value)
        elif field == 4 and wire == 5:
            marker_value = _as_float(value)
    if setting == 0 and instrument == 0 and marker_value > 0:
        return _TempoMarker(max(0.0, marker_time), marker_value)
    return None


def parse_sequence_proto(data: bytes) -> tuple[float, list[_ProtoNote], list[_TempoMarker]]:
    """Decode only the public sequence fields needed to produce a standard MIDI.

    Online Sequencer's sequence.proto stores Settings in field 1, repeated Notes
    in field 2, and repeated Markers in field 3. Unknown fields are ignored so
    the reader stays tolerant of unrelated sound/effect settings.
    """
    bpm = 120.0
    notes: list[_ProtoNote] = []
    tempo_markers: list[_TempoMarker] = []
    for field, wire, value in _wire_fields(data):
        if wire != 2 or not isinstance(value, bytes):
            continue
        if field == 1:
            bpm = _parse_settings_bpm(value)
        elif field == 2:
            notes.append(_parse_note(value))
            if len(notes) > MAX_SEQUENCE_NOTES:
                raise SequenceTooLargeError(len(notes))
        elif field == 3:
            marker = _parse_marker(value)
            if marker is not None:
                tempo_markers.append(marker)

    if not notes:
        raise OnlineSequencerError("This Online Sequencer sequence does not contain playable notes.")
    tempo_markers.sort(key=lambda marker: marker.time)
    return bpm, notes, tempo_markers


def _safe_bpm(value: float) -> float:
    # MIDI set_tempo has a finite 24-bit microseconds-per-beat range. These
    # bounds cover practical Online Sequencer songs while rejecting corruption.
    return min(1000.0, max(4.0, float(value)))


def sequence_proto_to_midi(data: bytes, destination: str | Path) -> tuple[int, int, float]:
    """Convert public Online Sequencer protobuf bytes to a standard MIDI file."""
    bpm, notes, tempo_markers = parse_sequence_proto(data)
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)

    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    ticks_per_sequence_unit = midi.ticks_per_beat / 4.0

    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage("track_name", name="Online Sequencer tempo", time=0))
    tempo_points: dict[int, float] = {0: _safe_bpm(bpm)}
    for marker in tempo_markers:
        tempo_points[max(0, round(marker.time * ticks_per_sequence_unit))] = _safe_bpm(marker.bpm)

    last_tick = 0
    for tick, point_bpm in sorted(tempo_points.items()):
        tempo_track.append(
            mido.MetaMessage(
                "set_tempo",
                tempo=mido.bpm2tempo(point_bpm),
                time=max(0, tick - last_tick),
            )
        )
        last_tick = tick
    tempo_track.append(mido.MetaMessage("end_of_track", time=0))
    midi.tracks.append(tempo_track)

    by_instrument: dict[int, list[_ProtoNote]] = {}
    for note in notes:
        midi_pitch = note.type_value + 12
        if not 0 <= midi_pitch <= 127:
            continue
        by_instrument.setdefault(note.instrument, []).append(note)

    written_notes = 0
    percussion_notes = 0
    for instrument, instrument_notes in sorted(by_instrument.items()):
        track = mido.MidiTrack()
        track.append(
            mido.MetaMessage(
                "track_name",
                name=f"Online Sequencer instrument {instrument}",
                time=0,
            )
        )
        channel = 9 if instrument in DRUM_INSTRUMENT_IDS else 0
        events: list[tuple[int, int, mido.Message]] = []
        for note in instrument_notes:
            pitch = note.type_value + 12
            if not 0 <= pitch <= 127:
                continue
            start_tick = max(0, round(note.time * ticks_per_sequence_unit))
            end_tick = max(start_tick + 1, round((note.time + note.length) * ticks_per_sequence_unit))
            if note.volume <= 0.0001:
                continue
            velocity = max(1, min(127, round(note.volume * 127)))
            events.append((start_tick, 1, mido.Message("note_on", note=pitch, velocity=velocity, channel=channel, time=0)))
            events.append((end_tick, 0, mido.Message("note_off", note=pitch, velocity=0, channel=channel, time=0)))
            written_notes += 1
            if channel == 9:
                percussion_notes += 1

        events.sort(key=lambda item: (item[0], item[1]))
        previous_tick = 0
        for tick, _priority, message in events:
            message.time = max(0, tick - previous_tick)
            track.append(message)
            previous_tick = tick
        track.append(mido.MetaMessage("end_of_track", time=0))
        midi.tracks.append(track)

    if written_notes == 0:
        raise OnlineSequencerError("This sequence did not contain MIDI-range notes that BPSR can analyze.")

    midi.save(target)
    # mido computes length using the tempo map we just generated.
    duration = float(mido.MidiFile(target).length)
    return written_notes, percussion_notes, duration


def _cache_paths(sequence_id: int, root: Path) -> tuple[Path, Path]:
    return root / f"os_{sequence_id}.mid", root / f"os_{sequence_id}.json"


def cleanup_cache(root: str | Path | None = None) -> None:
    cache = Path(root) if root is not None else cache_directory()
    try:
        cache.mkdir(parents=True, exist_ok=True)
        files = [path for path in cache.iterdir() if path.is_file()]
    except OSError:
        return

    now = time.time()
    for path in files:
        try:
            if now - path.stat().st_mtime > CACHE_MAX_AGE_SECONDS:
                path.unlink(missing_ok=True)
        except OSError:
            pass

    try:
        files = sorted(
            (path for path in cache.iterdir() if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return
    total = 0
    for path in files:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        total += size
        if total > CACHE_MAX_BYTES:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def _load_cached_metadata(meta_path: Path, midi_path: Path) -> CachedSequence | None:
    try:
        if not meta_path.exists() or not midi_path.exists():
            return None
        if time.time() - midi_path.stat().st_mtime > CACHE_MAX_AGE_SECONDS:
            return None
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return CachedSequence(
            sequence_id=int(data["sequence_id"]),
            path=midi_path,
            title=str(data.get("title") or f"Sequence #{data['sequence_id']}"),
            author=str(data.get("author") or ""),
            note_count=int(data.get("note_count", 0)),
            percussion_notes=int(data.get("percussion_notes", 0)),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def fetch_sequence_to_cache(
    sequence_id: int,
    *,
    title: str = "",
    author: str = "",
    root: str | Path | None = None,
    force: bool = False,
) -> CachedSequence:
    sequence_id = int(sequence_id)
    if sequence_id <= 0:
        raise OnlineSequencerError("Invalid Online Sequencer sequence ID.")
    cache = Path(root) if root is not None else cache_directory()
    cache.mkdir(parents=True, exist_ok=True)
    cleanup_cache(cache)
    midi_path, meta_path = _cache_paths(sequence_id, cache)

    if not force:
        cached = _load_cached_metadata(meta_path, midi_path)
        if cached is not None:
            if title and cached.title.startswith("Sequence #"):
                cached = CachedSequence(
                    cached.sequence_id,
                    cached.path,
                    title,
                    author or cached.author,
                    cached.note_count,
                    cached.percussion_notes,
                    cached.duration_seconds,
                )
            return cached

    proto = _request_bytes(
        PROTO_URL.format(sequence_id=sequence_id),
        timeout=10.0,
        max_bytes=MAX_PROTO_BYTES,
    )
    note_count, percussion_notes, duration = sequence_proto_to_midi(proto, midi_path)

    if not title:
        title, looked_up_author = fetch_sequence_page_metadata(sequence_id)
        if not author:
            author = looked_up_author
    resolved_title = title or f"Sequence #{sequence_id}"
    cached = CachedSequence(
        sequence_id=sequence_id,
        path=midi_path,
        title=resolved_title,
        author=author,
        note_count=note_count,
        percussion_notes=percussion_notes,
        duration_seconds=duration,
    )
    try:
        meta_path.write_text(
            json.dumps(
                {
                    "sequence_id": sequence_id,
                    "title": resolved_title,
                    "author": author,
                    "note_count": note_count,
                    "percussion_notes": percussion_notes,
                    "duration_seconds": duration,
                    "cached_at": time.time(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass
    return cached


def _safe_filename(title: str, sequence_id: int) -> str:
    stem = _INVALID_FILENAME_RE.sub("_", title).strip(" .")
    stem = re.sub(r"\s+", " ", stem)
    if not stem:
        stem = f"Online Sequencer {sequence_id}"
    stem = stem[:96].rstrip(" .")
    if stem.casefold() in {"con", "prn", "aux", "nul", "com1", "lpt1"}:
        stem = "_" + stem
    return f"{stem} [OS {sequence_id}].mid"


def save_cached_sequence(
    cached: CachedSequence,
    destination_folder: str | Path,
    *,
    title: str | None = None,
) -> Path:
    destination = Path(destination_folder)
    destination.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(title or cached.title, cached.sequence_id)
    target = destination / filename
    counter = 2
    while target.exists():
        target = destination / f"{Path(filename).stem} ({counter}).mid"
        counter += 1
    shutil.copy2(cached.path, target)
    return target
