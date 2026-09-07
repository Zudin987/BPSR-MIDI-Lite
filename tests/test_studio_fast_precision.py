from __future__ import annotations

from pathlib import Path

from studio_band.fast_precision import _review_regions, sieve_master
from studio_band.music import BeatMap, MasterSong, MusicEvent
from studio_band.runtime import Hardware
from studio_band import pipeline as studio_pipeline


def _event(source, start, pitch, confidence=.8, *, duration=.24, engine=None, evidence=None):
    return MusicEvent(
        source,
        "HARMONY" if source == "piano" else "RIFF",
        start,
        start + duration,
        pitch,
        confidence=confidence,
        engine=engine or ("transkun" if source == "piano" else "basic_pitch"),
        evidence=evidence or {},
    )


def _audio(target=0.0, fundamental=-2.0, mixture=1.0, share=.08, dominance=-12.0):
    return {
        "audio_note_validation": {
            "target_snr_db": target,
            "fundamental_snr_db": fundamental,
            "mixture_snr_db": mixture,
            "target_share": share,
            "dominance_db": dominance,
        }
    }


def test_fast_sieve_removes_singleton_audio_grounded_tonal_orphan():
    rogue = _event("guitar", 1.0, 66, .66, duration=.15, evidence=_audio())
    master = MasterSong(
        "x", 3.0, BeatMap(),
        [
            _event("guitar", 0.0, 60, .9),
            _event("guitar", .5, 64, .9),
            rogue,
            _event("guitar", 1.5, 64, .9),
            _event("guitar", 2.0, 60, .9),
        ],
    )
    sieve_master(master)
    assert rogue not in master.events
    assert any(item["reason"] == "audio_grounded_tonal_orphan" for item in master.rejected)


def test_fast_sieve_never_dismantles_same_onset_piano_chord():
    weak = _audio()
    chord = [
        _event("piano", 1.0, 60, .72, evidence=weak),
        _event("piano", 1.0, 64, .72, evidence=weak),
        _event("piano", 1.0, 67, .72, evidence=weak),
    ]
    master = MasterSong("x", 2.0, BeatMap(), chord)
    sieve_master(master)
    assert {event.pitch for event in master.events} == {60, 64, 67}
    assert not master.rejected


def test_fast_sieve_keeps_chromatic_note_with_strong_real_audio():
    chromatic = _event(
        "piano", 1.0, 66, .78, duration=.28,
        evidence=_audio(target=10.0, fundamental=8.0, mixture=9.0, share=.70, dominance=5.0),
    )
    master = MasterSong(
        "x", 3.0, BeatMap(),
        [
            _event("piano", 0.0, 60, .9),
            _event("piano", .5, 64, .9),
            chromatic,
            _event("piano", 1.5, 64, .9),
        ],
    )
    sieve_master(master)
    assert chromatic in master.events


def test_auto_separator_no_longer_promotes_full_song_hq():
    hardware = Hardware(True, 24.0, 64.0)
    assert studio_pipeline.choose_separator("auto", hardware, True) == "demucs"
    assert studio_pipeline.choose_separator("hq", hardware, True) == "roformer"


def test_targeted_review_has_hard_audio_budget():
    candidates = [
        {"source": "guitar", "pitch": 60 + (index % 5), "start": index * 5.0,
         "end": index * 5.0 + .2, "_review_score": 1.0 - index * .02}
        for index in range(10)
    ]
    regions = _review_regions(candidates, 60.0)
    assert len(regions) <= 3
    assert sum(region["end"] - region["start"] for region in regions) <= 12.0001


def test_fast_precision_ui_is_deferred_until_studio_setup():
    precision = Path("studio_band/fast_precision.py").read_text(encoding="utf-8")
    ui = Path("studio_fast_precision_ui.py").read_text(encoding="utf-8")
    assert "precision.install_precision_setup_ui = install_precision_setup_ui" in precision
    assert "from studio_fast_precision_ui import install_fast_precision_ui" in precision
    assert "_patch_advanced_ui()" in ui
    assert "Deep separation (experimental full-song HQ" in ui
    assert "Deep diagnostic model review" in ui
    assert "Separation: Auto (fast)" in ui
