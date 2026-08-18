from __future__ import annotations

import struct
from pathlib import Path

import mido
import pytest

from midi_engine import PlanOptions, build_plan
from online_sequencer import (
    BrowserSearchRequired,
    CachedSequence,
    parse_sequence_reference,
    save_cached_sequence,
    search_sequences,
    search_url,
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


def test_title_search_hands_off_to_a_real_browser() -> None:
    with pytest.raises(BrowserSearchRequired) as error:
        search_sequences("Taylor Swift")
    assert error.value.url == "https://onlinesequencer.net/sequences?search=Taylor+Swift"
    assert search_url("") == "https://onlinesequencer.net/sequences"


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
