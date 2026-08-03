from __future__ import annotations

import struct
from pathlib import Path

import mido
import pytest

import online_sequencer as osq


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


def _sample_proto() -> bytes:
    settings = _v(1, 120) + _v(2, 4)
    note = (
        _v(1, 60)
        + _f(2, 4.0)
        + _f(3, 2.0)
        + _v(4, 1)
        + _f(5, 0.8)
    )
    # setting=0 and instrument=0 are omitted by protobuf default-value rules.
    marker = _f(1, 8.0) + _f(4, 140.0)
    return _m(1, settings) + _m(2, note) + _m(3, marker)


def test_extract_sequence_id_accepts_number_and_url() -> None:
    assert osq.extract_sequence_id("123456") == 123456
    assert osq.extract_sequence_id("https://onlinesequencer.net/98765#t1") == 98765
    assert osq.extract_sequence_id("onlinesequencer.net/sequence/42") == 42
    with pytest.raises(osq.OnlineSequencerError):
        osq.extract_sequence_id("not a link")


def test_search_parser_collects_sequence_links_and_deduplicates() -> None:
    parser = osq._SearchResultsParser()
    parser.feed(
        """
        <a href='/123'><span>First Song</span></a>
        <div class='preview' title='Second Song'><a href='https://onlinesequencer.net/456'><img src='x'></a></div>
        <a href='/123'>Duplicate</a>
        <a href='/forum/thread-1'>Ignore</a>
        """
    )
    assert [(r.sequence_id, r.title) for r in parser.results] == [
        (123, "First Song"),
        (456, "Second Song"),
    ]


def test_parse_proto_and_convert_to_midi() -> None:
    sequence = osq.parse_sequence_proto(_sample_proto())
    assert sequence.bpm == 120
    assert len(sequence.notes) == 1
    assert sequence.notes[0].pitch == 60
    assert sequence.notes[0].time == pytest.approx(4.0)
    assert sequence.notes[0].length == pytest.approx(2.0)

    midi = osq.sequence_to_midi(sequence, "Test")
    assert midi.ticks_per_beat == 480
    assert len(midi.tracks) == 2

    tempo_ticks = []
    tick = 0
    for message in midi.tracks[0]:
        tick += message.time
        if message.type == "set_tempo":
            tempo_ticks.append((tick, round(mido.tempo2bpm(message.tempo))))
    assert tempo_ticks == [(0, 120), (960, 140)]

    note_ticks = []
    tick = 0
    for message in midi.tracks[1]:
        tick += message.time
        if message.type in {"note_on", "note_off"}:
            note_ticks.append((tick, message.type, message.note))
    assert note_ticks == [(480, "note_on", 60), (720, "note_off", 60)]


def test_import_sequence_saves_into_online_sequencer_subfolder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(osq, "fetch_sequence_proto", lambda _sid: _sample_proto())
    monkeypatch.setattr(osq, "fetch_sequence_title", lambda _sid: "My Song")
    output = osq.import_sequence(123, tmp_path, title="My Song")
    assert output.parent == tmp_path / "Online Sequencer"
    assert output.name == "My Song [OS-123].mid"
    assert output.exists()

    loaded = mido.MidiFile(output)
    assert any(
        message.type == "note_on" and message.velocity > 0
        for track in loaded.tracks
        for message in track
    )
