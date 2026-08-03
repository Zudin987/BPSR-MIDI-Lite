from __future__ import annotations

import gzip
import html
import math
import re
import struct
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Iterator

import mido


SITE_ROOT = "https://onlinesequencer.net"
SEARCH_URL = SITE_ROOT + "/sequences?search={query}"
PROTO_URL = SITE_ROOT + "/app/api/get_proto.php?id={sequence_id}"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0 Safari/537.36 BPSR-MIDI-Lite/0.5.2"
)
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
TICKS_PER_BEAT = 480
# Online Sequencer's timing unit is one sixteenth note: its reference player
# waits 15000 / BPM milliseconds per unit, which is one quarter of a beat.
TICKS_PER_SEQUENCE_UNIT = TICKS_PER_BEAT // 4
DRUM_INSTRUMENTS = {2, 31, 36, 39, 40, 42, 53}


class OnlineSequencerError(RuntimeError):
    """A user-facing Online Sequencer integration error."""


@dataclass(frozen=True, slots=True)
class SearchResult:
    sequence_id: int
    title: str

    @property
    def url(self) -> str:
        return f"{SITE_ROOT}/{self.sequence_id}"

    @property
    def display(self) -> str:
        return f"{self.title}  [#{self.sequence_id}]"


@dataclass(frozen=True, slots=True)
class SequenceNote:
    pitch: int
    time: float
    length: float
    instrument: int
    volume: float


@dataclass(frozen=True, slots=True)
class SequenceMarker:
    time: float
    setting: int
    instrument: int
    value: float
    blend: bool


@dataclass(frozen=True, slots=True)
class ParsedSequence:
    bpm: int
    notes: tuple[SequenceNote, ...]
    markers: tuple[SequenceMarker, ...]


_SEQUENCE_HREF_RE = re.compile(
    r"^(?:https?://(?:www\.)?onlinesequencer\.net)?/(?:sequence/)?(\d+)(?:[/?#].*)?$",
    re.IGNORECASE,
)
_SEQUENCE_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?onlinesequencer\.net/(?:sequence/)?(\d+)",
    re.IGNORECASE,
)
_INVALID_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SPACE_RE = re.compile(r"\s+")


def extract_sequence_id(value: str | int) -> int:
    """Extract a positive Online Sequencer ID from a number or sequence URL."""
    if isinstance(value, int):
        sequence_id = value
    else:
        text = value.strip()
        if text.isdigit():
            sequence_id = int(text)
        else:
            match = _SEQUENCE_URL_RE.search(text)
            if not match:
                raise OnlineSequencerError(
                    "Enter a numeric sequence ID or an Online Sequencer URL."
                )
            sequence_id = int(match.group(1))
    if sequence_id <= 0:
        raise OnlineSequencerError("The sequence ID must be greater than zero.")
    return sequence_id


def _clean_title(value: str, sequence_id: int) -> str:
    title = html.unescape(_SPACE_RE.sub(" ", value)).strip(" \t\r\n-|–—")
    for suffix in (
        " - Online Sequencer",
        " | Online Sequencer",
        " — Online Sequencer",
    ):
        if title.casefold().endswith(suffix.casefold()):
            title = title[: -len(suffix)].strip()
    if not title or title.casefold() in {"sequence", "online sequencer", "play"}:
        return f"Online Sequencer #{sequence_id}"
    return title[:180]


class _SearchResultsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[SearchResult] = []
        self._seen: set[int] = set()
        self._active_id: int | None = None
        self._active_parts: list[str] = []
        self._active_hint = ""
        self._preview_title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.casefold(): value or "" for key, value in attrs}
        classes = set(attrs_dict.get("class", "").casefold().split())
        if "preview" in classes and attrs_dict.get("title"):
            self._preview_title = attrs_dict["title"].strip()
        if self._active_id is not None:
            if tag.casefold() == "img":
                alt = attrs_dict.get("alt", "").strip()
                if alt:
                    self._active_parts.append(alt)
            return
        if tag.casefold() != "a":
            return
        href = attrs_dict.get("href", "").strip()
        match = _SEQUENCE_HREF_RE.match(href)
        if not match:
            return
        sequence_id = int(match.group(1))
        if sequence_id in self._seen:
            return
        self._active_id = sequence_id
        self._active_parts = []
        self._active_hint = (
            attrs_dict.get("data-title")
            or attrs_dict.get("aria-label")
            or attrs_dict.get("title")
            or self._preview_title
            or ""
        )

    def handle_data(self, data: str) -> None:
        if self._active_id is not None and data.strip():
            self._active_parts.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if self._active_id is None:
            return
        if tag.casefold() != "a":
            return
        sequence_id = self._active_id
        title_source = self._active_hint or " ".join(self._active_parts).strip()
        self.results.append(
            SearchResult(sequence_id, _clean_title(title_source, sequence_id))
        )
        self._seen.add(sequence_id)
        self._active_id = None
        self._active_parts = []
        self._active_hint = ""


class _TitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._inside_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.casefold(): value or "" for key, value in attrs}
        if tag.casefold() == "meta":
            prop = (attrs_dict.get("property") or attrs_dict.get("name") or "").casefold()
            if prop in {"og:title", "twitter:title"} and attrs_dict.get("content"):
                self.title = attrs_dict["content"]
        elif tag.casefold() == "title":
            self._inside_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "title":
            self._inside_title = False

    def handle_data(self, data: str) -> None:
        if self._inside_title and not self.title and data.strip():
            self.title = data.strip()


def _request_bytes(url: str, timeout: float = 20.0) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/octet-stream;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip",
            "Connection": "close",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise OnlineSequencerError(f"Online Sequencer returned HTTP {status}.")
            data = response.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                raise OnlineSequencerError("The Online Sequencer response is too large.")
            encoding = (response.headers.get("Content-Encoding") or "").casefold()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise OnlineSequencerError("That Online Sequencer sequence was not found.") from exc
        raise OnlineSequencerError(
            f"Online Sequencer returned HTTP {exc.code}. Try again later."
        ) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise OnlineSequencerError(
            f"Could not connect to Online Sequencer: {reason}"
        ) from exc
    except TimeoutError as exc:
        raise OnlineSequencerError("Online Sequencer took too long to respond.") from exc

    if encoding == "gzip" or data[:2] == b"\x1f\x8b":
        try:
            data = gzip.decompress(data)
        except OSError as exc:
            raise OnlineSequencerError("Online Sequencer returned invalid compressed data.") from exc
    return data


def search_sequences(query: str, limit: int = 40) -> list[SearchResult]:
    query = query.strip()
    if not query:
        raise OnlineSequencerError("Type a song name first.")
    url = SEARCH_URL.format(query=urllib.parse.quote_plus(query))
    raw = _request_bytes(url)
    text = raw.decode("utf-8", errors="replace")
    parser = _SearchResultsParser()
    parser.feed(text)
    return parser.results[: max(1, min(limit, 100))]


def fetch_sequence_title(sequence_id: int) -> str:
    raw = _request_bytes(f"{SITE_ROOT}/{extract_sequence_id(sequence_id)}")
    parser = _TitleParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    return _clean_title(parser.title, sequence_id)


def fetch_sequence_proto(sequence_id: int) -> bytes:
    sequence_id = extract_sequence_id(sequence_id)
    data = _request_bytes(PROTO_URL.format(sequence_id=sequence_id))
    if not data:
        raise OnlineSequencerError("Online Sequencer returned an empty sequence.")
    # Some server/proxy combinations may deliver the compressed body without a
    # Content-Encoding header; _request_bytes also checks the gzip signature.
    return data


# ---- Minimal Protocol Buffers wire reader ---------------------------------
# The public SequencePlayer reference project publishes the generated schema.
# A tiny reader keeps this app single-purpose and avoids bundling a compiler or
# generated 280 KB source file. Unknown fields are safely ignored.


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(data) and shift < 70:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    raise OnlineSequencerError("The Online Sequencer sequence data is malformed.")


def _iter_fields(data: bytes) -> Iterator[tuple[int, int, object]]:
    offset = 0
    length = len(data)
    while offset < length:
        tag, offset = _read_varint(data, offset)
        field_number = tag >> 3
        wire_type = tag & 0x07
        if field_number == 0:
            raise OnlineSequencerError("The sequence contains an invalid protobuf field.")
        if wire_type == 0:
            value, offset = _read_varint(data, offset)
        elif wire_type == 1:
            if offset + 8 > length:
                raise OnlineSequencerError("The sequence data ended unexpectedly.")
            value = data[offset : offset + 8]
            offset += 8
        elif wire_type == 2:
            size, offset = _read_varint(data, offset)
            if size < 0 or offset + size > length:
                raise OnlineSequencerError("The sequence contains an invalid field length.")
            value = data[offset : offset + size]
            offset += size
        elif wire_type == 5:
            if offset + 4 > length:
                raise OnlineSequencerError("The sequence data ended unexpectedly.")
            value = data[offset : offset + 4]
            offset += 4
        else:
            raise OnlineSequencerError(
                f"Unsupported protobuf wire type {wire_type} in sequence data."
            )
        yield field_number, wire_type, value


def _float32(value: object) -> float:
    if not isinstance(value, (bytes, bytearray)) or len(value) != 4:
        raise OnlineSequencerError("The sequence contains an invalid floating-point field.")
    return struct.unpack("<f", value)[0]


def _parse_settings(data: bytes) -> int:
    bpm = 110
    for field, wire, value in _iter_fields(data):
        if field == 1 and wire == 0:
            bpm = int(value)
    return bpm if 20 <= bpm <= 999 else 110


def _parse_note(data: bytes) -> SequenceNote:
    pitch = 0
    time_value = 0.0
    length = 0.0
    instrument = 0
    volume = 1.0
    for field, wire, value in _iter_fields(data):
        if field == 1 and wire == 0:
            pitch = int(value)
        elif field == 2 and wire == 5:
            time_value = _float32(value)
        elif field == 3 and wire == 5:
            length = _float32(value)
        elif field == 4 and wire == 0:
            instrument = int(value)
        elif field == 5 and wire == 5:
            volume = _float32(value)
    return SequenceNote(pitch, time_value, length, instrument, volume)


def _parse_marker(data: bytes) -> SequenceMarker:
    time_value = 0.0
    setting = 0
    instrument = 0
    value_float = 0.0
    blend = False
    for field, wire, value in _iter_fields(data):
        if field == 1 and wire == 5:
            time_value = _float32(value)
        elif field == 2 and wire == 0:
            setting = int(value)
        elif field == 3 and wire == 0:
            instrument = int(value)
        elif field == 4 and wire == 5:
            value_float = _float32(value)
        elif field == 5 and wire == 0:
            blend = bool(value)
    return SequenceMarker(time_value, setting, instrument, value_float, blend)


def parse_sequence_proto(data: bytes) -> ParsedSequence:
    bpm = 110
    notes: list[SequenceNote] = []
    markers: list[SequenceMarker] = []
    for field, wire, value in _iter_fields(data):
        if not isinstance(value, bytes):
            continue
        if field == 1 and wire == 2:
            bpm = _parse_settings(value)
        elif field == 2 and wire == 2:
            note = _parse_note(value)
            if (
                0 <= note.pitch <= 127
                and math.isfinite(note.time)
                and math.isfinite(note.length)
                and note.time >= 0
                and note.length >= 0
            ):
                notes.append(note)
        elif field == 3 and wire == 2:
            markers.append(_parse_marker(value))
    if not notes:
        raise OnlineSequencerError("This sequence does not contain any playable notes.")
    notes.sort(key=lambda note: (note.time, note.instrument, note.pitch))
    markers.sort(key=lambda marker: marker.time)
    return ParsedSequence(bpm, tuple(notes), tuple(markers))


def _tempo_events(sequence: ParsedSequence) -> list[tuple[int, int]]:
    values: dict[int, int] = {0: sequence.bpm}
    for marker in sequence.markers:
        # SequencePlayer treats setting 0, instrument 0 as BPM automation.
        if (
            marker.setting == 0
            and marker.instrument == 0
            and math.isfinite(marker.time)
            and math.isfinite(marker.value)
            and marker.time >= 0
            and 20 <= marker.value <= 999
        ):
            tick = max(0, round(marker.time * TICKS_PER_SEQUENCE_UNIT))
            values[tick] = round(marker.value)
    return sorted(values.items())


def sequence_to_midi(sequence: ParsedSequence, title: str = "Online Sequencer Import") -> mido.MidiFile:
    midi = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)

    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage("track_name", name=title[:100], time=0))
    previous_tick = 0
    for tick, bpm in _tempo_events(sequence):
        tempo_track.append(
            mido.MetaMessage(
                "set_tempo",
                tempo=mido.bpm2tempo(max(20, min(999, bpm))),
                time=tick - previous_tick,
            )
        )
        previous_tick = tick
    tempo_track.append(mido.MetaMessage("end_of_track", time=0))
    midi.tracks.append(tempo_track)

    instruments = sorted({note.instrument for note in sequence.notes})
    melodic_channels = [channel for channel in range(16) if channel != 9]
    channel_by_instrument: dict[int, int] = {}
    melodic_index = 0
    for instrument in instruments:
        if instrument % 10000 in DRUM_INSTRUMENTS:
            channel_by_instrument[instrument] = 9
        else:
            channel_by_instrument[instrument] = melodic_channels[
                melodic_index % len(melodic_channels)
            ]
            melodic_index += 1

    notes_by_instrument: dict[int, list[SequenceNote]] = {}
    for note in sequence.notes:
        notes_by_instrument.setdefault(note.instrument, []).append(note)

    for instrument in instruments:
        channel = channel_by_instrument[instrument]
        track = mido.MidiTrack()
        track.append(
            mido.MetaMessage(
                "track_name",
                name=("Drums" if channel == 9 else f"Instrument {instrument}"),
                time=0,
            )
        )
        if channel != 9:
            track.append(
                mido.Message(
                    "program_change",
                    channel=channel,
                    program=max(0, min(127, instrument % 128)),
                    time=0,
                )
            )

        events: list[tuple[int, int, int, mido.Message]] = []
        serial = 0
        for note in notes_by_instrument[instrument]:
            start = max(0, round(note.time * TICKS_PER_SEQUENCE_UNIT))
            duration_units = note.length if note.length > 0 else 0.25
            end = max(start + 1, round((note.time + duration_units) * TICKS_PER_SEQUENCE_UNIT))
            if not math.isfinite(note.volume) or note.volume <= 0:
                velocity = 100
            else:
                velocity = max(1, min(127, round(note.volume * 127)))
            # NoteType's numeric value is the same pitch number used by the
            # site's MIDI/export ecosystem, despite its octave label convention.
            pitch = max(0, min(127, note.pitch))
            events.append(
                (start, 1, serial, mido.Message("note_on", channel=channel, note=pitch, velocity=velocity, time=0))
            )
            events.append(
                (end, 0, serial, mido.Message("note_off", channel=channel, note=pitch, velocity=0, time=0))
            )
            serial += 1

        events.sort(key=lambda item: (item[0], item[1], item[2]))
        previous_tick = 0
        for tick, _, _, message in events:
            track.append(message.copy(time=tick - previous_tick))
            previous_tick = tick
        track.append(mido.MetaMessage("end_of_track", time=0))
        midi.tracks.append(track)

    return midi


def safe_filename(title: str, sequence_id: int) -> str:
    cleaned = _INVALID_FILENAME_RE.sub("_", html.unescape(title))
    cleaned = _SPACE_RE.sub(" ", cleaned).strip(" ._")
    if not cleaned:
        cleaned = "Online Sequencer"
    cleaned = cleaned[:110].rstrip(" ._")
    return f"{cleaned} [OS-{sequence_id}].mid"


def import_sequence(
    sequence_id_or_url: str | int,
    destination_folder: str | Path,
    title: str | None = None,
) -> Path:
    sequence_id = extract_sequence_id(sequence_id_or_url)
    resolved_title = _clean_title(title or "", sequence_id)
    try:
        page_title = fetch_sequence_title(sequence_id)
        if not page_title.startswith("Online Sequencer #"):
            resolved_title = page_title
    except OnlineSequencerError:
        # The protobuf can still be imported when the public page metadata is
        # temporarily unavailable; use the search title or sequence ID.
        pass
    sequence = parse_sequence_proto(fetch_sequence_proto(sequence_id))
    midi = sequence_to_midi(sequence, resolved_title)
    destination = Path(destination_folder) / "Online Sequencer"
    destination.mkdir(parents=True, exist_ok=True)
    existing = sorted(destination.glob(f"* [OS-{sequence_id}].mid"))
    output = existing[0] if existing else destination / safe_filename(resolved_title, sequence_id)
    midi.save(output)
    return output
