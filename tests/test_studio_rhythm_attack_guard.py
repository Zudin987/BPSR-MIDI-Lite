from __future__ import annotations

from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")

from studio_band.music import BeatMap, MasterSong, MusicEvent
from studio_band.rhythm_attack_guard import validate_rhythm_attacks


SR = 44100
PITCH = 69


def _tone(seconds: float = 1.2, *, start: float = 0.0, end: float | None = None):
    frames = int(SR * seconds)
    signal = np.zeros(frames, dtype="float64")
    left = max(0, int(start * SR))
    right = frames if end is None else min(frames, int(end * SR))
    t = np.arange(max(0, right - left), dtype="float64") / SR
    hz = 440.0 * 2 ** ((PITCH - 69) / 12.0)
    signal[left:right] = .16 * np.sin(2 * np.pi * hz * t)
    return np.column_stack([signal, signal]).astype("float32")


def _files(tmp_path: Path, audio):
    piano = tmp_path / "piano.wav"
    mixture = tmp_path / "prepared.wav"
    sf.write(piano, audio, SR, subtype="FLOAT")
    sf.write(mixture, audio, SR, subtype="FLOAT")
    return {"piano": piano}, mixture


def _event(start: float, end: float, confidence: float = .82, *, candidate: bool = False):
    return MusicEvent(
        "piano", "HARMONY", start, end, PITCH, 80,
        .78 if candidate else confidence,
        "transkun",
        {"independent_agreement"} if candidate else set(),
        event_id="candidate" if candidate else f"anchor-{start}",
        evidence={"confidence_kind": "test"},
    )


def _master():
    # At 120 BPM the sixteenth grid is every 125 ms. 310 ms is deliberately
    # outside the loose grid tolerance, while the neighboring anchors are on it.
    beat_map = BeatMap(120.0, [0.0, .5, 1.0], [0.0, 1.0], "test", .95)
    events = [
        _event(.125, .240),
        _event(.310, .450, candidate=True),
        _event(.500, .650),
    ]
    return MasterSong("test", 1.2, beat_map, events)


def test_rejects_supported_off_rhythm_retrigger_when_pitch_is_only_sustained(tmp_path: Path):
    stems, mixture = _files(tmp_path, _tone())
    master = validate_rhythm_attacks(_master(), stems, mixture)

    assert "candidate" not in {event.event_id for event in master.events}
    assert master.rejected[-1]["reason"] == "off_rhythm_retrigger_without_audio_attack"
    assert master.provenance["rhythm_attack_guard"]["removed"] == 1


def test_keeps_off_grid_note_when_audio_has_a_real_pitch_attack(tmp_path: Path):
    stems, mixture = _files(tmp_path, _tone(start=.310, end=.455))
    master = validate_rhythm_attacks(_master(), stems, mixture)

    candidate = next(event for event in master.events if event.event_id == "candidate")
    assert "rhythm_attack_validated" in candidate.tags
    assert not master.rejected
    assert candidate.evidence["rhythm_attack_validation"]["source_attack"]["pitch_attack_db"] > 1.0
