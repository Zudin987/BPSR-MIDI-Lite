from __future__ import annotations

from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")

from studio_band.audio_onset_refiner import refine_audio_onsets
from studio_band.music import BeatMap, MasterSong, MusicEvent


SR = 44100
PITCH = 69


def _tone(seconds: float = 1.2, *, start: float, end: float = .500):
    frames = int(SR * seconds)
    signal = np.zeros(frames, dtype="float64")
    left = max(0, int(start * SR))
    right = min(frames, int(end * SR))
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


def _event(start: float, end: float, *, candidate: bool = False):
    return MusicEvent(
        "piano", "HARMONY", start, end, PITCH, 80,
        .78 if candidate else .84,
        "transkun",
        {"independent_agreement"} if candidate else set(),
        event_id="candidate" if candidate else f"anchor-{start}",
        evidence={"confidence_kind": "test"},
    )


def _master():
    beat_map = BeatMap(120.0, [0.0, .5, 1.0], [0.0, 1.0], "test", .95)
    events = [
        _event(.125, .240),
        _event(.310, .450, candidate=True),
        _event(.500, .650),
    ]
    return MasterSong("test", 1.2, beat_map, events)


def test_refines_mistimed_note_to_nearby_real_audio_attack(tmp_path: Path):
    # The model says 310 ms, but the real note begins at 250 ms. The refiner
    # should follow the source+mixture attack rather than blindly snap to a beat.
    stems, mixture = _files(tmp_path, _tone(start=.250))
    master = refine_audio_onsets(_master(), stems, mixture)

    candidate = next(event for event in master.events if event.event_id == "candidate")
    assert candidate.start == pytest.approx(.250, abs=.018)
    assert candidate.end - candidate.start == pytest.approx(.140, abs=.003)
    assert "audio_onset_refined" in candidate.tags
    timing = candidate.evidence["audio_onset_refinement"]
    assert timing["shift_seconds"] == pytest.approx(-.060, abs=.018)
    assert timing["improvement_db"] > 1.75
    assert master.provenance["audio_onset_refiner"]["refined"] == 1


def test_preserves_real_syncopation_when_attack_matches_transcribed_onset(tmp_path: Path):
    stems, mixture = _files(tmp_path, _tone(start=.310))
    master = refine_audio_onsets(_master(), stems, mixture)

    candidate = next(event for event in master.events if event.event_id == "candidate")
    assert candidate.start == pytest.approx(.310, abs=.001)
    assert "audio_onset_refined" not in candidate.tags
    assert master.provenance["audio_onset_refiner"]["refined"] == 0
