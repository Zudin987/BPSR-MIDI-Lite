from __future__ import annotations

import struct
from json import loads
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import mido
import pytest

from midi_engine import PlanOptions, build_plan
from online_sequencer import (
    CachedSequence,
    OnlineSequencerError,
    SearchResult,
    fetch_sequence_to_cache,
    lookup_sequence_metadata,
    parse_sequence_reference,
    save_cached_sequence,
    search_sequences,
    sequence_proto_to_midi,
)


def _varint(value: int) -> bytes:
    output = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            output.append(byte | 0x80)
        else:
            output.append(byte)
            return bytes(output)


def _key(field: int, wire: int) -> bytes:
    return _varint((field << 3) | wire)


def _v(field: int, value: int) -> bytes:
    return _key(field, 0) + _varint(value)


def _f(field: int, value: float) -> bytes:
    return _key(field, 5) + struct.pack("<f", value)


def _m(field: int, payload: bytes) -> bytes:
    return _key(field, 2) + _varint(len(payload)) + payload


def _note(note_type: int, time: float, length: float, instrument: int = 0, volume: float = 1.0) -> bytes:
    return b"".join(
        (
            _v(1, note_type),
            _f(2, time),
            _f(3, length),
            _v(4, instrument),
            _f(5, volume),
        )
    )


def _sequence_fixture() -> bytes:
    settings = _v(1, 120)
    tempo_marker = b"".join((_f(1, 4.0), _v(2, 0), _v(3, 0), _f(4, 60.0)))
    return b"".join(
        (
            _m(1, settings),
            _m(2, _note(36, 0.0, 4.0)),  # Online Sequencer C3 -> MIDI/BPSR C3 (48)
            _m(2, _note(40, 4.0, 4.0)),  # E3 -> MIDI 52
            _m(2, _note(31, 0.0, 1.0, instrument=2)),  # drum kit -> MIDI channel 10
            _m(3, tempo_marker),
        )
    )


def test_parse_sequence_reference_accepts_id_and_public_url() -> None:
    assert parse_sequence_reference("123456") == 123456
    assert parse_sequence_reference("https://onlinesequencer.net/123456") == 123456
    assert parse_sequence_reference("https://www.onlinesequencer.net/123456/") == 123456
    assert parse_sequence_reference("https://onlinesequencer.net/app/sequencer.php?frame=1&id=123456") == 123456
    assert parse_sequence_reference("https://onlinesequencer.net/app/api/get_proto.php?id=123456") == 123456
    assert parse_sequence_reference("https://example.com/123456") is None
    assert parse_sequence_reference("zelda") is None


def test_direct_reference_resolution_never_scrapes_an_html_page(monkeypatch) -> None:
    monkeypatch.setattr(
        "online_sequencer.build_opener",
        lambda: pytest.fail("direct reference resolution must not make an HTML request"),
    )
    results = search_sequences("https://onlinesequencer.net/123456")
    assert len(results) == 1
    assert results[0].sequence_id == 123456
    assert results[0].title == "Sequence #123456"


def test_title_text_is_rejected_without_browser_handoff() -> None:
    with pytest.raises(OnlineSequencerError, match="does not provide an app-accessible title-search API") as error:
        search_sequences("Taylor Swift")
    assert "no browser was opened" in str(error.value)


def test_public_metadata_lookup_returns_real_title_and_author(monkeypatch) -> None:
    requested: dict[str, object] = {}

    def fake_request(url: str, *, timeout: float, max_bytes: int) -> bytes:
        requested.update(url=url, timeout=timeout, max_bytes=max_bytes)
        return (
            b'{"status":"success","data":{"title":"  Real  Song - Online Sequencer",'
            b'"author":"Alice"}}'
        )

    monkeypatch.setattr("online_sequencer._request_metadata_bytes", fake_request)

    result = lookup_sequence_metadata(5529399)

    assert result is not None
    assert result.title == "Real Song"
    assert result.author == "Alice"
    query = parse_qs(urlparse(str(requested["url"])).query)
    assert query == {
        "url": ["https://onlinesequencer.net/5529399"],
        "filter": ["title,author"],
    }
    assert requested["timeout"] == 8.0


def test_real_metadata_flows_to_cached_and_saved_midi_name(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("online_sequencer._request_bytes", lambda *_args, **_kwargs: _sequence_fixture())
    monkeypatch.setattr(
        "online_sequencer.lookup_sequence_metadata",
        lambda sequence_id: SearchResult(sequence_id, "Actual Song: Finale?", "Alice"),
    )

    cached = fetch_sequence_to_cache(5529399, title="Sequence #5529399", root=tmp_path / "cache")
    saved = save_cached_sequence(cached, tmp_path / "library")

    assert cached.title == "Actual Song: Finale?"
    assert cached.author == "Alice"
    assert saved.name == "Actual Song_ Finale_ [OS 5529399].mid"


def test_generic_existing_cache_is_upgraded_without_downloading_notes_again(monkeypatch, tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    monkeypatch.setattr("online_sequencer._request_bytes", lambda *_args, **_kwargs: _sequence_fixture())
    monkeypatch.setattr("online_sequencer.lookup_sequence_metadata", lambda _sequence_id: None)
    initial = fetch_sequence_to_cache(321, title="Sequence #321", root=cache_root)
    assert initial.title == "Sequence #321"

    monkeypatch.setattr(
        "online_sequencer.lookup_sequence_metadata",
        lambda sequence_id: SearchResult(sequence_id, "Recovered Title", "Bob"),
    )
    monkeypatch.setattr(
        "online_sequencer._request_bytes",
        lambda *_args, **_kwargs: pytest.fail("cached notes must not be downloaded again"),
    )
    upgraded = fetch_sequence_to_cache(321, title="Sequence #321", root=cache_root)

    assert upgraded.title == "Recovered Title"
    assert upgraded.author == "Bob"
    metadata = loads((cache_root / "os_321.json").read_text(encoding="utf-8"))
    assert metadata["title"] == "Recovered Title"
    assert metadata["author"] == "Bob"


def test_title_lookup_failure_never_blocks_sequence_playback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("online_sequencer._request_bytes", lambda *_args, **_kwargs: _sequence_fixture())

    def unavailable(_sequence_id: int) -> None:
        raise OnlineSequencerError("title service unavailable")

    monkeypatch.setattr("online_sequencer.lookup_sequence_metadata", unavailable)

    cached = fetch_sequence_to_cache(444, title="Sequence #444", root=tmp_path)

    assert cached.title == "Sequence #444"
    assert cached.path.exists()


def test_proto_conversion_creates_standard_midi_and_preserves_tempo(tmp_path: Path) -> None:
    target = tmp_path / "online.mid"
    note_count, percussion_count, duration = sequence_proto_to_midi(_sequence_fixture(), target)
    assert note_count == 3
    assert percussion_count == 1
    assert target.exists()
    assert duration > 1.4

    midi = mido.MidiFile(target)
    melodic = []
    drums = []
    for track in midi.tracks:
        for message in track:
            if message.type == "note_on" and message.velocity > 0:
                (drums if message.channel == 9 else melodic).append(message.note)
    assert melodic == [48, 52]
    assert drums == [43]


def test_online_generated_midi_uses_existing_bpsr_planner(tmp_path: Path) -> None:
    target = tmp_path / "online.mid"
    sequence_proto_to_midi(_sequence_fixture(), target)
    plan = build_plan(
        target,
        PlanOptions(
            instrument="keyboard",
            mode="stable",
            unlock_tier="tier1",
            mapping_method="transpose",
            max_notes_per_chord=2,
            ignore_percussion=True,
        ),
    )
    assert plan.note_count == 2
    assert plan.source_percussion_notes == 1
    assert plan.filtered_notes >= 1
    assert plan.page_switches == 0


def test_save_cached_sequence_makes_unique_local_files(tmp_path: Path) -> None:
    cache_file = tmp_path / "cache.mid"
    cache_file.write_bytes(b"midi")
    cached = CachedSequence(123, cache_file, "A: Song?", "Alice", 10, 0, 2.0)
    library = tmp_path / "library"
    first = save_cached_sequence(cached, library)
    second = save_cached_sequence(cached, library)
    assert first.name == "A_ Song_ [OS 123].mid"
    assert second.name == "A_ Song_ [OS 123] (2).mid"
    assert first.read_bytes() == b"midi"
