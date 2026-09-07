from __future__ import annotations

from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")

from studio_band.audio_note_guard import validate_master_notes
from studio_band.music import BeatMap, MasterSong, MusicEvent


def _tone(pitch: int, seconds: float = 1.0, amp: float = .15):
    sr = 44100
    t = np.arange(int(sr * seconds), dtype="float64") / sr
    hz = 440.0 * 2 ** ((pitch - 69) / 12.0)
    mono = amp * np.sin(2 * np.pi * hz * t)
    return np.column_stack([mono, mono]).astype("float32"), sr


def _files(tmp_path: Path, owner: str, pitch: int = 69):
    tone, sr = _tone(pitch)
    silence = np.zeros_like(tone)
    stems = {}
    for name in ("vocals", "piano", "guitar", "bass", "drums", "other"):
        path = tmp_path / f"{name}.wav"
        sf.write(path, tone if name == owner else silence, sr, subtype="FLOAT")
        stems[name] = path
    mixture = tmp_path / "prepared.wav"
    sf.write(mixture, tone, sr, subtype="FLOAT")
    return stems, mixture


def _master(source: str, *, tags=None):
    event = MusicEvent(
        source, "HARMONY", .20, .55, 69, 80, .72,
        "transkun" if source == "piano" else "basic_pitch",
        set(tags or ()), event_id="candidate",
        evidence={"confidence_kind": "test"},
    )
    return MasterSong("test", 1.0, BeatMap(), [event])


def test_audio_note_guard_keeps_note_present_in_its_stem(tmp_path: Path):
    stems, mixture = _files(tmp_path, "piano")
    master = validate_master_notes(_master("piano"), stems, mixture)
    assert [event.event_id for event in master.events] == ["candidate"]
    assert not master.rejected
    assert master.events[0].evidence["audio_note_validation"]["target_snr_db"] > 6


def test_audio_note_guard_rejects_guitar_note_owned_by_another_stem(tmp_path: Path):
    stems, mixture = _files(tmp_path, "piano")
    master = validate_master_notes(_master("guitar"), stems, mixture)
    assert not master.events
    assert master.rejected
    assert master.rejected[0]["reason"] == "guitar_cross_stem_leakage"


def test_repeated_motif_does_not_exempt_clear_cross_stem_leakage(tmp_path: Path):
    stems, mixture = _files(tmp_path, "piano")
    master = validate_master_notes(_master("guitar", tags={"repeated_motif"}), stems, mixture)
    assert not master.events
    assert master.rejected[0]["reason"] == "repeated_or_chord_audio_mismatch"
