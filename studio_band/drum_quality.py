"""High-quality Audio -> Band drum transcription routing.

Normal Studio conversions should not collapse to a three-role kick/snare/hat
fallback just because the optional cross-check switch is off. This layer makes
DrumSep the preferred primary drum transcriber on CUDA and upgrades the
model-free fallback to a six-kit spectral detector with open-hat distinction.
"""
from __future__ import annotations

import math
from typing import Any

_APPLIED = False


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _cymbal_role(*, sustain: float, strength: float, mid_share: float,
                 air_share: float) -> str:
    """Classify one high-frequency attack without inventing a pitched note."""
    sustain = _clamp(sustain)
    strength = _clamp(strength)
    mid_share = _clamp(mid_share)
    air_share = _clamp(air_share)
    if sustain >= 0.62 and strength >= 0.42:
        return "RIDE" if mid_share >= 0.24 and air_share < 0.58 else "CRASH"
    if sustain >= 0.28:
        return "OPEN_HAT"
    return "CLOSED_HAT"


def _spectral_six_drum_provider(providers, payload: dict, report) -> dict:
    """Model-free multi-band drum fallback preserving simultaneous kit roles."""
    import numpy as np
    from scipy.signal import find_peaks, stft
    from .music import MusicEvent

    audio, sample_rate = providers._legacy._audio(payload["audio"])
    mono = np.asarray(audio, dtype="float32").mean(axis=1)
    providers._legacy._report(
        report, "Detecting kick/snare/toms/hats/ride/crash on CPU…",
        activity="cpu", stage_fraction=0.15,
    )
    if len(mono) < 1024 or float(np.max(np.abs(mono))) < 1e-7:
        return {"events": [], "device": "cpu", "model": "spectral-six-kit-v2"}

    frequencies, times, spectrum = stft(
        mono, sample_rate, nperseg=1024, noverlap=768, boundary="zeros"
    )
    power = np.abs(spectrum) ** 2
    ranges = {
        "sub": (30, 170),
        "lowmid": (170, 650),
        "mid": (650, 3200),
        "high": (3200, 8000),
        "air": (8000, min(19000, sample_rate / 2 - 1)),
    }
    energy: dict[str, Any] = {}
    flux: dict[str, Any] = {}
    for name, (low, high) in ranges.items():
        mask = (frequencies >= low) & (frequencies < high)
        values = power[mask].sum(axis=0) if np.any(mask) else np.zeros(len(times))
        scale = float(np.percentile(values[values > 0], 75)) if np.any(values > 0) else 1.0
        compressed = np.log1p(values / max(scale, 1e-12))
        energy[name] = values
        flux[name] = np.maximum(0.0, np.diff(compressed, prepend=compressed[0]))

    total_energy = sum(energy.values()) + 1e-12
    events = []

    def peaks_for(score, *, gap: float, percentile: float = 82.0,
                  relative: float = 0.055):
        positive = score[score > 0]
        if len(positive) < 3:
            return []
        floor = max(float(np.percentile(positive, percentile)) * 0.62,
                    float(np.max(score)) * relative, 1e-8)
        distance = max(1, round(gap / max(1e-6, float(times[1] - times[0]))))
        found, _ = find_peaks(score, height=floor, prominence=floor * 0.40,
                              distance=distance)
        return found

    def append(role: str, index: int, score, confidence: float, *, duration: float,
               extra: dict | None = None) -> None:
        peak = float(np.max(score)) + 1e-12
        strength = _clamp(float(score[index]) / peak)
        start = max(0.0, float(times[index]) - 0.006)
        evidence = {
            "confidence_kind": "multi-band spectral onset heuristic",
            "onset_strength": strength,
            "spectral_fallback_version": 2,
        }
        if extra:
            evidence.update(extra)
        events.append(MusicEvent(
            "drums", role, start, start + duration, None,
            max(30, min(120, round(38 + 76 * math.sqrt(strength)))),
            _clamp(confidence, 0.25, 0.79), "drums_dsp",
            {"fallback", "six_kit_spectral"}, evidence=evidence,
        ).to_dict())

    kick_score = flux["sub"] + 0.22 * flux["lowmid"]
    for index in peaks_for(kick_score, gap=.050, percentile=80):
        sub_share = float(energy["sub"][index] / total_energy[index])
        if sub_share < .11:
            continue
        strength = float(kick_score[index] / (np.max(kick_score) + 1e-12))
        append("KICK", index, kick_score, .40 + .22 * math.sqrt(strength) + .16 * sub_share,
               duration=.060, extra={"sub_share": sub_share})

    snare_score = 0.18 * flux["lowmid"] + flux["mid"] + 0.48 * flux["high"]
    for index in peaks_for(snare_score, gap=.050, percentile=82):
        mid_share = float((energy["mid"][index] + energy["high"][index]) / total_energy[index])
        sub_share = float(energy["sub"][index] / total_energy[index])
        if mid_share < .24 or (sub_share > .58 and mid_share < .38):
            continue
        strength = float(snare_score[index] / (np.max(snare_score) + 1e-12))
        append("SNARE", index, snare_score, .38 + .24 * math.sqrt(strength) + .15 * mid_share,
               duration=.065, extra={"mid_high_share": mid_share})

    tom_score = flux["lowmid"] + 0.48 * flux["mid"]
    for index in peaks_for(tom_score, gap=.070, percentile=86, relative=.07):
        lowmid_share = float((energy["lowmid"][index] + energy["mid"][index]) / total_energy[index])
        air_share = float((energy["high"][index] + energy["air"][index]) / total_energy[index])
        sub_share = float(energy["sub"][index] / total_energy[index])
        if lowmid_share < .38 or air_share > .46 or sub_share > .62:
            continue
        if any(abs(float(event["start"]) - float(times[index])) < .040 and
               event["role"] == "SNARE" for event in events) and lowmid_share < .58:
            continue
        strength = float(tom_score[index] / (np.max(tom_score) + 1e-12))
        append("TOM", index, tom_score, .36 + .22 * math.sqrt(strength) + .18 * lowmid_share,
               duration=.075, extra={"lowmid_share": lowmid_share})

    cymbal_score = 0.42 * flux["high"] + flux["air"]
    for index in peaks_for(cymbal_score, gap=.032, percentile=76, relative=.040):
        high_share = float((energy["high"][index] + energy["air"][index]) / total_energy[index])
        if high_share < .16:
            continue
        tail_end = min(len(times), index + max(3, round(.18 / max(1e-6, float(times[1] - times[0])))))
        peak_energy = float(energy["high"][index] + energy["air"][index]) + 1e-12
        tail_values = energy["high"][index + 1:tail_end] + energy["air"][index + 1:tail_end]
        sustain = _clamp(float(np.mean(tail_values)) / peak_energy) if len(tail_values) else 0.0
        mid_share = float(energy["mid"][index] / total_energy[index])
        air_share = float(energy["air"][index] / total_energy[index])
        strength = _clamp(float(cymbal_score[index]) / (float(np.max(cymbal_score)) + 1e-12))
        role = _cymbal_role(sustain=sustain, strength=strength,
                            mid_share=mid_share, air_share=air_share)
        duration = {"CLOSED_HAT": .050, "OPEN_HAT": .085, "RIDE": .095, "CRASH": .110}[role]
        append(role, index, cymbal_score,
               .36 + .20 * math.sqrt(strength) + .18 * high_share,
               duration=duration,
               extra={"high_share": high_share, "sustain_ratio": sustain,
                      "mid_share": mid_share, "air_share": air_share})

    events.sort(key=lambda event: (float(event["start"]), str(event["role"])))
    return {
        "events": events,
        "device": "cpu",
        "model": "spectral-six-kit-v2",
        "warnings": [
            "DrumSep/ADToF was unavailable; used the model-free six-kit spectral fallback."
        ],
    }


def _patch_providers(providers) -> None:
    """Replace the old three-role DSP fallback in every worker process."""
    current = providers._legacy.PROVIDERS.get("drums_dsp")
    if getattr(current, "_bpsr_six_kit_fallback", False):
        return

    def drums_dsp(payload: dict, report) -> dict:
        return _spectral_six_drum_provider(providers, payload, report)

    drums_dsp._bpsr_six_kit_fallback = True
    providers._legacy.PROVIDERS["drums_dsp"] = drums_dsp
    providers.PROVIDERS = providers._legacy.PROVIDERS


def _patch_pipeline(pipeline) -> None:
    """Promote DrumSep to the normal CUDA drum path, not an optional cross-check."""
    original = pipeline.BandPipeline._stage
    if getattr(original, "_bpsr_primary_drumsep", False):
        return

    def stage(self, client, job, provider, audio, payload, cancel, report, warnings,
              settings, hardware):
        if provider != "drums_dsp":
            return original(self, client, job, provider, audio, payload, cancel, report,
                            warnings, settings, hardware)

        previous_cross_check = settings.cross_check
        settings.cross_check = False
        try:
            fallback = original(self, client, job, provider, audio, payload, cancel, report,
                                warnings, settings, hardware)
        finally:
            settings.cross_check = previous_cross_check

        if settings.device == "cpu" or not hardware.cuda:
            return fallback
        try:
            preferred = original(self, client, job, "drumsep", audio, {}, cancel, report,
                                 warnings, settings, hardware)
        except Exception as exc:
            if isinstance(exc, pipeline.Cancelled):
                raise
            warnings.append(f"Primary DrumSep transcription unavailable: {exc}")
            fallback.setdefault("warnings", []).append(
                "DrumSep unavailable; retained six-kit spectral drum fallback."
            )
            return fallback
        if not preferred.get("events"):
            fallback.setdefault("warnings", []).append(
                "DrumSep returned no drum events; retained six-kit spectral drum fallback."
            )
            return fallback
        preferred.setdefault("warnings", []).append(
            "Used DrumSep six-kit separation as the primary Audio-to-Band drum transcription."
        )
        preferred.setdefault("provenance", {})["six_kit_primary"] = True
        preferred["six_kit_primary"] = True
        return preferred

    stage._bpsr_primary_drumsep = True
    pipeline.BandPipeline._stage = stage


def apply_drum_quality() -> None:
    global _APPLIED
    if _APPLIED:
        return
    from . import pipeline, providers

    _patch_providers(providers)
    _patch_pipeline(pipeline)
    _APPLIED = True
