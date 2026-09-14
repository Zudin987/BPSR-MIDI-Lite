"""Full-kit built-in drum transcription for normal Audio -> Band conversion.

The old fallback intentionally detected only kick, snare and closed hi-hat.
That made a normal conversion fundamentally incomplete whenever optional ADTOF
or the diagnostic DrumSep pass was unavailable.  This module replaces only the
built-in ``drums_dsp`` provider with a deterministic spectral/onset detector
that keeps the same no-model/no-network fallback contract while estimating the
complete BPSR semantic kit.
"""
from __future__ import annotations

import math
from typing import Any

DRUM_DSP_MODEL = "spectral-kit-2"

# Minimum same-role spacing. Different roles are intentionally allowed at the
# same timestamp so a kick+hat or snare+hat attack survives as two drum hits.
_ROLE_GAP = {
    "KICK": 0.045,
    "SNARE": 0.045,
    "TOM": 0.050,
    "CLOSED_HAT": 0.028,
    "OPEN_HAT": 0.070,
    "RIDE": 0.060,
    "CRASH": 0.100,
    "PERCUSSION": 0.045,
}

_ROLE_DURATION = {
    "KICK": 0.065,
    "SNARE": 0.070,
    "TOM": 0.080,
    "CLOSED_HAT": 0.045,
    "OPEN_HAT": 0.120,
    "RIDE": 0.110,
    "CRASH": 0.140,
    "PERCUSSION": 0.065,
}


def classify_low_hit(*, low_share: float, body_share: float, high_share: float,
                     centroid_hz: float, strength: float = 0.5) -> str:
    """Classify a low-frequency onset as kick or tom.

    The decision deliberately depends on broad spectral ratios rather than a
    single FFT bin, which is more tolerant of separated-stem coloration.
    """
    if low_share >= 0.43 or centroid_hz <= 300.0:
        return "KICK"
    if body_share >= 0.34 and high_share <= 0.34 and centroid_hz <= 2300.0:
        return "TOM"
    # Weak low attacks are often tom resonance; very strong low attacks are
    # more likely a kick even when the separator has removed some sub energy.
    return "KICK" if low_share >= 0.31 and strength >= 0.58 else "TOM"


def classify_mid_hit(*, low_share: float, body_share: float, high_share: float,
                     centroid_hz: float) -> str:
    """Classify a body/mid onset as snare or tom."""
    if body_share >= 0.48 and high_share <= 0.27 and centroid_hz <= 2100.0:
        return "TOM"
    if low_share >= 0.34 and high_share <= 0.24 and centroid_hz <= 1700.0:
        return "TOM"
    return "SNARE"


def classify_high_hit(*, low_share: float, body_share: float, high_share: float,
                      air_share: float, centroid_hz: float, sustain: float,
                      strength: float) -> str:
    """Split a high-frequency attack into hat/ride/crash semantics.

    ``sustain`` is the post-attack high-band energy divided by the attack-frame
    high-band energy. Closed hats decay rapidly; open hats and cymbals retain
    high-frequency energy. Crash is broad/strong, while ride carries more
    persistent upper-mid body and usually less air than a crash wash.
    """
    if (
        sustain >= 0.34
        and strength >= 0.52
        and body_share >= 0.18
        and air_share >= 0.12
    ):
        return "CRASH"
    if (
        sustain >= 0.28
        and body_share >= 0.16
        and high_share >= 0.38
        and air_share <= 0.34
        and centroid_hz <= 10500.0
    ):
        return "RIDE"
    if sustain >= 0.17:
        return "OPEN_HAT"
    return "CLOSED_HAT"


def _adaptive_peaks(np, find_peaks, flux, times, *, minimum_gap: float,
                    percentile: float = 72.0, peak_fraction: float = 0.065):
    if len(flux) < 4 or not len(times):
        return []
    maximum = float(np.max(flux))
    if maximum <= 1e-10:
        return []
    positive = flux[flux > 0]
    if not len(positive):
        return []
    floor = max(
        float(np.percentile(positive, percentile)) * 0.62,
        maximum * peak_fraction,
        1e-10,
    )
    hop = float(times[1] - times[0]) if len(times) > 1 else 0.01
    distance = max(1, round(minimum_gap / max(hop, 1e-4)))
    peaks, _ = find_peaks(
        flux,
        height=floor,
        prominence=max(1e-10, floor * 0.34),
        distance=distance,
    )
    return [int(index) for index in peaks]


def _spectral_features(legacy, audio_path: str):
    import numpy as np
    from scipy.signal import stft

    audio, sample_rate = legacy._audio(audio_path)
    mono = np.asarray(audio, dtype="float32").mean(axis=1)
    if not len(mono):
        return np, sample_rate, np.asarray([]), np.asarray([[]]), {}, {}, np.asarray([])

    # ~5.8 ms hop at 44.1 kHz keeps fast hats distinct while a 1024-sample
    # analysis window still provides enough low-frequency resolution for kick
    # versus tom decisions.
    frequencies, times, spectrum = stft(
        mono,
        sample_rate,
        nperseg=1024,
        noverlap=768,
        boundary="zeros",
        padded=True,
    )
    power = np.abs(spectrum) ** 2
    band_ranges = {
        "sub": (30.0, 120.0),
        "low": (120.0, 350.0),
        "body": (350.0, 1800.0),
        "presence": (1800.0, 5000.0),
        "high": (5000.0, 10000.0),
        "air": (10000.0, min(20000.0, sample_rate / 2.0)),
    }
    energies = {}
    fluxes = {}
    for name, (low, high) in band_ranges.items():
        mask = (frequencies >= low) & (frequencies < high)
        energy = power[mask].sum(axis=0) if np.any(mask) else np.zeros(len(times))
        # Per-band normalization prevents kick energy from numerically drowning
        # small but real hat/cymbal attacks. Log compression makes the detector
        # stable across mastered and quiet recordings.
        scale = max(float(np.percentile(energy, 95)), float(np.max(energy)) * 0.18, 1e-12)
        compressed = np.log1p((energy / scale) * 8.0)
        flux = np.maximum(0.0, np.diff(compressed, prepend=compressed[0]))
        energies[name] = energy
        fluxes[name] = flux

    total_power = power.sum(axis=0) + 1e-12
    centroid = (power * frequencies[:, None]).sum(axis=0) / total_power
    return np, sample_rate, times, power, energies, fluxes, centroid


def _frame_features(np, energies, centroid, index: int) -> dict[str, float]:
    values = {name: float(series[index]) for name, series in energies.items()}
    total = sum(values.values()) + 1e-12
    low = (values["sub"] + values["low"]) / total
    body = (values["body"] + values["presence"]) / total
    high = (values["high"] + values["air"]) / total
    air = values["air"] / total

    high_series = energies["high"] + energies["air"]
    # Skip the attack itself and measure roughly the next 23-70 ms. This is the
    # key distinction between short closed hats and sustained open/cymbal wash.
    tail_start = min(len(high_series), index + 4)
    tail_end = min(len(high_series), index + 13)
    tail = float(np.mean(high_series[tail_start:tail_end])) if tail_end > tail_start else 0.0
    onset = max(float(high_series[index]), 1e-12)
    sustain = max(0.0, min(1.5, tail / onset))
    return {
        "low_share": low,
        "body_share": body,
        "high_share": high,
        "air_share": air,
        "centroid_hz": float(centroid[index]),
        "sustain": sustain,
    }


def _candidate(role: str, start: float, strength: float, features: dict[str, float],
               stream: str) -> dict[str, Any]:
    specificity = {
        "KICK": features["low_share"],
        "TOM": features["body_share"],
        "SNARE": min(1.0, features["body_share"] + features["high_share"] * 0.35),
        "CLOSED_HAT": features["high_share"],
        "OPEN_HAT": min(1.0, features["high_share"] + features["sustain"] * 0.25),
        "RIDE": min(1.0, features["high_share"] + features["body_share"] * 0.25),
        "CRASH": min(1.0, features["high_share"] + features["body_share"] * 0.30),
    }.get(role, 0.45)
    confidence = min(
        0.84,
        0.38 + 0.24 * math.sqrt(max(0.0, min(1.0, strength))) +
        0.17 * max(0.0, min(1.0, specificity)) +
        0.05 * max(0.0, min(1.0, features["sustain"])),
    )
    velocity = max(35, min(120, round(38 + 80 * math.sqrt(max(0.0, min(1.0, strength))))))
    return {
        "role": role,
        "start": max(0.0, start),
        "strength": max(0.0, min(1.0, strength)),
        "confidence": confidence,
        "velocity": velocity,
        "stream": stream,
        "features": features,
    }


def _dedupe_role_hits(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    last_index: dict[str, int] = {}
    for hit in sorted(candidates, key=lambda item: (item["start"], item["role"])):
        role = str(hit["role"])
        previous_index = last_index.get(role)
        if previous_index is not None:
            previous = selected[previous_index]
            if hit["start"] - previous["start"] < _ROLE_GAP.get(role, 0.045):
                if (hit["strength"], hit["confidence"]) > (
                    previous["strength"], previous["confidence"]
                ):
                    selected[previous_index] = hit
                continue
        last_index[role] = len(selected)
        selected.append(hit)
    return sorted(selected, key=lambda item: (item["start"], item["role"]))


def drums_dsp(legacy, payload: dict, report) -> dict:
    """Model-free full-kit drum transcription used by the normal Audio tab."""
    from scipy.signal import find_peaks

    np, _sample_rate, times, _power, energies, fluxes, centroid = _spectral_features(
        legacy, payload["audio"]
    )
    legacy._report(
        report,
        "Detecting full drum kit attacks on CPU…",
        activity="cpu",
        stage_fraction=0.15,
    )
    if not len(times):
        return {"events": [], "device": "cpu", "model": DRUM_DSP_MODEL}

    low_flux = fluxes["sub"] + 0.72 * fluxes["low"] + 0.12 * fluxes["body"]
    mid_flux = fluxes["body"] + 0.78 * fluxes["presence"] + 0.10 * fluxes["low"]
    high_flux = fluxes["high"] + 0.82 * fluxes["air"] + 0.28 * fluxes["presence"]
    global_flux = low_flux + mid_flux + high_flux
    global_peak = float(np.max(global_flux)) + 1e-12

    candidates: list[dict[str, Any]] = []
    streams = (
        ("low", low_flux, 0.040),
        ("mid", mid_flux, 0.040),
        ("high", high_flux, 0.026),
    )
    for stream, flux, gap in streams:
        indices = _adaptive_peaks(np, find_peaks, flux, times, minimum_gap=gap)
        stream_peak = float(np.max(flux)) + 1e-12
        for index in indices:
            features = _frame_features(np, energies, centroid, index)
            stream_strength = float(flux[index]) / stream_peak
            accent = float(global_flux[index]) / global_peak
            strength = min(1.0, 0.76 * stream_strength + 0.24 * accent)

            if stream == "low":
                if features["low_share"] < 0.18 and features["centroid_hz"] > 1800.0:
                    continue
                role = classify_low_hit(
                    low_share=features["low_share"],
                    body_share=features["body_share"],
                    high_share=features["high_share"],
                    centroid_hz=features["centroid_hz"],
                    strength=strength,
                )
            elif stream == "mid":
                if features["body_share"] < 0.24:
                    continue
                role = classify_mid_hit(
                    low_share=features["low_share"],
                    body_share=features["body_share"],
                    high_share=features["high_share"],
                    centroid_hz=features["centroid_hz"],
                )
                # A very low/body-heavy mid peak is usually the same kick that
                # the low stream already found, not an independent snare/tom.
                if role == "TOM" and features["low_share"] >= 0.52:
                    continue
            else:
                # Snare noise bleeds into the high band. Require the cymbal/hat
                # family to own a meaningful fraction before creating a second
                # simultaneous high-frequency hit.
                if (
                    features["high_share"] < 0.30
                    or (
                        features["body_share"] > 0.56
                        and features["sustain"] < 0.14
                    )
                ):
                    continue
                role = classify_high_hit(
                    low_share=features["low_share"],
                    body_share=features["body_share"],
                    high_share=features["high_share"],
                    air_share=features["air_share"],
                    centroid_hz=features["centroid_hz"],
                    sustain=features["sustain"],
                    strength=strength,
                )

            start = max(0.0, float(times[index]) - 0.004)
            candidates.append(_candidate(role, start, strength, features, stream))

    hits = _dedupe_role_hits(candidates)
    events = []
    for hit in hits:
        role = str(hit["role"])
        features = hit["features"]
        start = float(hit["start"])
        events.append(
            legacy.MusicEvent(
                "drums",
                role,
                start,
                start + _ROLE_DURATION.get(role, 0.065),
                None,
                int(hit["velocity"]),
                float(hit["confidence"]),
                "drums_dsp",
                {"fallback", "full_kit_spectral_drum_class"},
                evidence={
                    "confidence_kind": "multiband onset + spectral envelope heuristic",
                    "semantic_model": DRUM_DSP_MODEL,
                    "detection_stream": hit["stream"],
                    "onset_strength": round(float(hit["strength"]), 6),
                    "low_share": round(float(features["low_share"]), 6),
                    "body_share": round(float(features["body_share"]), 6),
                    "high_share": round(float(features["high_share"]), 6),
                    "air_share": round(float(features["air_share"]), 6),
                    "spectral_centroid_hz": round(float(features["centroid_hz"]), 3),
                    "high_band_sustain": round(float(features["sustain"]), 6),
                },
            ).to_dict()
        )

    roles = sorted({event["role"] for event in events})
    return {
        "events": events,
        "device": "cpu",
        "model": DRUM_DSP_MODEL,
        "detected_roles": roles,
        "warnings": [
            "Built-in full-kit spectral drum detection is active. Difficult overlapping cymbal/snare hits "
            "remain approximate; optional ADTOF/DrumSep evidence can refine them when enabled and available."
        ],
    }


def _patch_providers(providers, runtime) -> None:
    """Install the full-kit fallback in both worker and desktop registries."""
    providers._legacy.PROVIDERS["drums_dsp"] = (
        lambda payload, report: drums_dsp(providers._legacy, payload, report)
    )
    # The provider model participates in stage fingerprints/cache keys. Bumping
    # it prevents old kick/snare/closed-hat-only results from surviving upgrade.
    providers._legacy.PROVIDER_MODEL["drums_dsp"] = DRUM_DSP_MODEL
    runtime.PROVIDER_MODEL["drums_dsp"] = DRUM_DSP_MODEL


def apply_drum_transcription() -> None:
    from . import providers, runtime

    _patch_providers(providers, runtime)
