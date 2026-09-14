from __future__ import annotations

from studio_band import PIPELINE_VERSION, VERSION
from studio_band import drum_transcription as drums
from studio_band import providers, runtime


def _hit(role: str, start: float, strength: float) -> dict:
    return {
        "role": role,
        "start": start,
        "strength": strength,
        "confidence": .70,
        "velocity": 90,
        "stream": "test",
        "features": {},
    }


def test_low_band_classifier_separates_kick_and_tom() -> None:
    assert drums.classify_low_hit(
        low_share=.52, body_share=.30, high_share=.18,
        centroid_hz=220.0, strength=.70,
    ) == "KICK"
    assert drums.classify_low_hit(
        low_share=.28, body_share=.48, high_share=.20,
        centroid_hz=1350.0, strength=.42,
    ) == "TOM"


def test_mid_band_classifier_separates_snare_and_tom() -> None:
    assert drums.classify_mid_hit(
        low_share=.20, body_share=.39, high_share=.41, centroid_hz=3300.0,
    ) == "SNARE"
    assert drums.classify_mid_hit(
        low_share=.24, body_share=.55, high_share=.21, centroid_hz=1500.0,
    ) == "TOM"


def test_high_band_classifier_covers_hat_ride_and_crash_family() -> None:
    common = {"low_share": .08}
    assert drums.classify_high_hit(
        **common, body_share=.12, high_share=.70, air_share=.35,
        centroid_hz=11200.0, sustain=.08, strength=.52,
    ) == "CLOSED_HAT"
    assert drums.classify_high_hit(
        **common, body_share=.08, high_share=.72, air_share=.25,
        centroid_hz=11800.0, sustain=.22, strength=.55,
    ) == "OPEN_HAT"
    assert drums.classify_high_hit(
        **common, body_share=.24, high_share=.55, air_share=.20,
        centroid_hz=8000.0, sustain=.36, strength=.40,
    ) == "RIDE"
    assert drums.classify_high_hit(
        **common, body_share=.28, high_share=.58, air_share=.20,
        centroid_hz=9000.0, sustain=.45, strength=.80,
    ) == "CRASH"


def test_deduper_keeps_simultaneous_different_drums_and_only_collapses_same_role() -> None:
    hits = drums._dedupe_role_hits([
        _hit("KICK", 1.000, .70),
        _hit("CLOSED_HAT", 1.000, .55),
        _hit("KICK", 1.020, .92),
        _hit("SNARE", 1.020, .68),
        _hit("CLOSED_HAT", 1.035, .62),
    ])

    assert [(hit["role"], round(hit["start"], 3)) for hit in hits] == [
        ("CLOSED_HAT", 1.000),
        ("KICK", 1.020),
        ("SNARE", 1.020),
        ("CLOSED_HAT", 1.035),
    ]


def test_full_kit_provider_replaces_three_role_fallback_and_invalidates_old_cache() -> None:
    assert VERSION.endswith("hotfix9")
    assert PIPELINE_VERSION == "band-accurate-10"
    assert runtime.PROVIDER_MODEL["drums_dsp"] == drums.DRUM_DSP_MODEL == "spectral-kit-2"
    assert providers._legacy.PROVIDER_MODEL["drums_dsp"] == "spectral-kit-2"
    assert "drums_dsp" in providers._legacy.PROVIDERS
