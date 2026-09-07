"""Validate final piano/guitar notes against the audio that actually produced them.

Global stem purity and musical-context rules are useful, but they can still keep a
locally wrong note when a generally clean stem contains one separator/transcriber
artifact.  This guard measures the detected pitch at the exact note onset in the
resolved stem, the original mixture, and competing stems.  It is deliberately a
precision layer: strong notes are kept, borderline notes are only down-weighted,
and rejection requires clear local audio disagreement.
"""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import replace
import math
from pathlib import Path
from typing import Any

from .music import MasterSong, MusicEvent

_TARGETS = {"piano", "guitar"}
_STEM_ORDER = ("piano", "guitar", "vocals", "bass", "drums", "other")


def _strong_support(event: MusicEvent) -> bool:
    """Independent model evidence is strong; repeated motifs alone are not.

    A separator artifact can repeat every bar and become a ``repeated_motif``.
    That tag should protect rhythmic cleanup, but it must not exempt a note from
    checking whether the pitch exists in the audio.
    """
    if event.tags & {"independent_agreement", "targeted_repair"}:
        return True
    return any(event.evidence.get(key) for key in ("beta9_support_engines", "agreement_engines"))


def _raw_confidence(event: MusicEvent) -> float:
    return float(event.confidence if event.original_confidence is None else event.original_confidence)


def _onset_groups(events: list[MusicEvent], tolerance: float = .045) -> list[list[MusicEvent]]:
    groups: list[list[MusicEvent]] = []
    for event in sorted(events, key=lambda item: (item.start, item.pitch or -1)):
        if not groups or event.start - groups[-1][0].start > tolerance:
            groups.append([])
        groups[-1].append(event)
    return groups


def _read_window(handle, onset: float, seconds: float = .22):
    import numpy as np

    sr = int(handle.samplerate)
    pre = .025
    start = max(0, int((onset - pre) * sr))
    frames = max(256, int((seconds + pre) * sr))
    handle.seek(min(start, max(0, len(handle) - 1)))
    audio = handle.read(frames, dtype="float32", always_2d=True)
    if not len(audio):
        return np.zeros(256, dtype="float32"), sr
    mono = np.asarray(audio, dtype="float32").mean(axis=1)
    return mono, sr


def _spectrum(samples, sample_rate: int):
    import numpy as np

    values = np.asarray(samples, dtype="float64")
    if len(values) < 256:
        values = np.pad(values, (0, 256-len(values)))
    values = values - float(values.mean())
    peak = float(np.max(np.abs(values))) if len(values) else 0.0
    rms = math.sqrt(float(np.mean(values * values))) if len(values) else 0.0
    # 8192 gives useful low-register resolution while keeping this post-pass
    # lightweight. Longer windows may naturally use 16384.
    nfft = 1 << max(13, (len(values)-1).bit_length())
    nfft = min(16384, nfft)
    if len(values) > nfft:
        values = values[:nfft]
    elif len(values) < nfft:
        values = np.pad(values, (0, nfft-len(values)))
    window = np.hanning(len(values))
    power = np.abs(np.fft.rfft(values * window)) ** 2
    frequencies = np.fft.rfftfreq(len(values), 1.0 / sample_rate)
    return power, frequencies, rms, peak


def _pitch_evidence(power, frequencies, pitch: int) -> dict[str, float]:
    import numpy as np

    f0 = 440.0 * (2.0 ** ((pitch - 69) / 12.0))
    nyquist = float(frequencies[-1]) if len(frequencies) else 0.0
    weighted_signal = 0.0
    weighted_floor = 0.0
    fundamental_signal = 0.0
    fundamental_floor = 0.0
    used = 0
    for harmonic in range(1, 6):
        center = f0 * harmonic
        if center < 24.0 or center >= min(6000.0, nyquist * .96):
            break
        # +/-1.35% is roughly a quarter semitone. The wider surrounding ring is
        # a local noise/other-note reference rather than a global loudness test.
        width = max(3.0, center * .0135)
        ring = max(13.0, center * .055)
        band_mask = (frequencies >= center-width) & (frequencies <= center+width)
        ring_mask = (frequencies >= center-ring) & (frequencies <= center+ring) & ~band_mask
        band = power[band_mask]
        around = power[ring_mask]
        if not len(band):
            continue
        # A real pitched partial is narrow. Use the strongest few bins, but a
        # median local ring so neighboring chord energy does not look like zero.
        ordered = np.sort(band)
        take = ordered[-min(3, len(ordered)):]
        signal = float(np.mean(take))
        floor = float(np.median(around)) if len(around) else float(np.median(power))
        floor = max(floor, 1e-18)
        weight = 1.0 / math.sqrt(harmonic)
        weighted_signal += weight * signal
        weighted_floor += weight * floor
        if harmonic == 1:
            fundamental_signal, fundamental_floor = signal, floor
        used += 1
    if not used:
        return {"signal": 0.0, "snr_db": -120.0, "fundamental_snr_db": -120.0}
    snr_db = 10.0 * math.log10((weighted_signal + 1e-18) / (weighted_floor + 1e-18))
    fundamental_snr = 10.0 * math.log10((fundamental_signal + 1e-18) /
                                        (fundamental_floor + 1e-18))
    return {
        "signal": weighted_signal,
        "snr_db": max(-120.0, min(120.0, snr_db)),
        "fundamental_snr_db": max(-120.0, min(120.0, fundamental_snr)),
    }


def _annotate(event: MusicEvent, evidence: dict[str, Any], *, confidence_scale: float = 1.0,
              tag: str | None = None) -> MusicEvent:
    tags = set(event.tags)
    if tag:
        tags.add(tag)
    return replace(
        event,
        confidence=max(0.0, min(.99, event.confidence * confidence_scale)),
        tags=tags,
        evidence={**event.evidence, "audio_note_validation": evidence},
    )


def _rejection(event: MusicEvent, evidence: dict[str, Any], reason: str) -> dict[str, Any]:
    checked = _annotate(event, evidence)
    return {"event": checked.to_dict(), "reason": reason}


def validate_master_notes(master: MasterSong, stems: dict[str, Path], mixture: Path) -> MasterSong:
    """Reject clear piano/guitar hallucinations using local source-audio evidence.

    The function mutates ``master`` in place for the normal pipeline, and returns
    it for convenient focused tests. Any file/dependency error is intentionally
    allowed to bubble to the caller, which treats this quality layer as optional.
    """
    import soundfile as sf

    candidates = [event for event in master.events if event.source in _TARGETS and event.pitch is not None]
    if not candidates:
        master.provenance["audio_note_guard"] = {"version": 1, "checked": 0, "removed": 0}
        return master

    available = {name: Path(path) for name, path in stems.items()
                 if name in _STEM_ORDER and Path(path).is_file()}
    if not _TARGETS.issubset(available) or not Path(mixture).is_file():
        raise OSError("Piano/guitar stem or prepared mixture is missing")

    kept_other = [event for event in master.events if event not in candidates]
    kept_target: list[MusicEvent] = []
    removed: list[dict[str, Any]] = []
    weakened = 0
    checked = 0

    by_source = {source: [event for event in candidates if event.source == source] for source in _TARGETS}
    with ExitStack() as stack:
        handles = {name: stack.enter_context(sf.SoundFile(str(path), "r")) for name, path in available.items()}
        mix_handle = stack.enter_context(sf.SoundFile(str(mixture), "r"))

        for source in sorted(_TARGETS):
            for group in _onset_groups(by_source[source]):
                if not group:
                    continue
                onset = min(event.start for event in group)
                spectra: dict[str, tuple[Any, Any, float, float]] = {}
                for name, handle in handles.items():
                    window, sr = _read_window(handle, onset)
                    spectra[name] = _spectrum(window, sr)
                mix_window, mix_sr = _read_window(mix_handle, onset)
                mix_spectrum = _spectrum(mix_window, mix_sr)

                for event in group:
                    checked += 1
                    target_power, target_freq, target_rms, _ = spectra[source]
                    target = _pitch_evidence(target_power, target_freq, int(event.pitch))
                    mixture_support = _pitch_evidence(mix_spectrum[0], mix_spectrum[1], int(event.pitch))

                    stem_support: dict[str, float] = {}
                    competitor_snr: dict[str, float] = {}
                    for name, (power, frequencies, _, _) in spectra.items():
                        value = _pitch_evidence(power, frequencies, int(event.pitch))
                        stem_support[name] = value["signal"]
                        competitor_snr[name] = value["snr_db"]
                    total = sum(stem_support.values()) + 1e-18
                    target_signal = stem_support.get(source, 0.0)
                    other_items = [(name, value) for name, value in stem_support.items() if name != source]
                    competitor_name, competitor_signal = max(other_items, key=lambda item: item[1]) if other_items else ("none", 0.0)
                    share = target_signal / total
                    dominance_db = 10.0 * math.log10((target_signal + 1e-18) / (competitor_signal + 1e-18))
                    rms_dbfs = 20.0 * math.log10(max(target_rms, 1e-12))
                    evidence = {
                        "source": source,
                        "pitch": int(event.pitch),
                        "target_snr_db": round(target["snr_db"], 3),
                        "fundamental_snr_db": round(target["fundamental_snr_db"], 3),
                        "mixture_snr_db": round(mixture_support["snr_db"], 3),
                        "target_share": round(share, 5),
                        "dominance_db": round(dominance_db, 3),
                        "strongest_competitor": competitor_name,
                        "strongest_competitor_snr_db": round(competitor_snr.get(competitor_name, -120.0), 3),
                        "local_rms_dbfs": round(rms_dbfs, 3),
                        "onset_group_size": len(group),
                    }

                    supported = _strong_support(event)
                    repeated = "repeated_motif" in event.tags
                    raw = _raw_confidence(event)
                    singleton = len(group) == 1

                    # Extreme case: the alleged pitch is not locally tonal in
                    # either the resolved source or the original mixture.
                    no_audio_pitch = target["snr_db"] < .5 and mixture_support["snr_db"] < 1.5
                    # Strong evidence that this is another stem bleeding into
                    # piano/guitar rather than a note owned by this part.
                    severe_leakage = dominance_db < -8.0 and share < .16 and target["snr_db"] < 7.0
                    extreme_leakage = dominance_db < -11.0 and share < .10

                    reject_reason = None
                    if supported:
                        # Independent agreement is valuable, but two models must
                        # not overrule near-total absence from the audio itself.
                        if no_audio_pitch and target["snr_db"] < -1.0:
                            reject_reason = "independent_models_without_audio_pitch_support"
                    elif repeated or not singleton:
                        # Repeated riffs/chords get a much more conservative
                        # threshold, preventing the old guard from deleting real
                        # accompaniment while still catching repeated leakage.
                        if no_audio_pitch or extreme_leakage:
                            reject_reason = "repeated_or_chord_audio_mismatch"
                    elif source == "guitar":
                        if no_audio_pitch:
                            reject_reason = "guitar_note_absent_from_audio"
                        elif severe_leakage:
                            reject_reason = "guitar_cross_stem_leakage"
                        elif (event.engine == "basic_pitch" and raw < .74 and
                              target["snr_db"] < 4.0 and
                              (share < .25 or mixture_support["snr_db"] < 2.5)):
                            reject_reason = "weak_basic_pitch_guitar_audio_support"
                        elif (event.engine == "basic_pitch" and raw < .66 and
                              target["fundamental_snr_db"] < 1.0 and share < .32):
                            reject_reason = "guitar_harmonic_without_fundamental"
                    else:  # piano
                        if no_audio_pitch:
                            reject_reason = "piano_note_absent_from_audio"
                        elif severe_leakage and event.confidence < .84:
                            reject_reason = "piano_cross_stem_leakage"
                        elif (event.engine == "transkun" and event.confidence < .82 and
                              target["snr_db"] < 3.0 and (share < .20 or dominance_db < -7.0)):
                            reject_reason = "weak_transkun_piano_audio_support"

                    if reject_reason:
                        removed.append(_rejection(event, evidence, reject_reason))
                        continue

                    borderline = (
                        not supported and target["snr_db"] < 5.0 and
                        (share < .30 or dominance_db < -4.0)
                    )
                    if borderline:
                        weakened += 1
                        kept_target.append(_annotate(
                            event, evidence, confidence_scale=.90,
                            tag="weak_audio_note_support",
                        ))
                    else:
                        kept_target.append(_annotate(event, evidence, tag="audio_note_validated"))

    master.events = sorted(kept_other + kept_target,
                           key=lambda event: (event.start, event.source, event.pitch or 0))
    master.rejected.extend(removed)
    reasons: dict[str, int] = {}
    for item in removed:
        reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
    master.provenance["audio_note_guard"] = {
        "version": 1,
        "checked": checked,
        "removed": len(removed),
        "weakened": weakened,
        "reasons": dict(sorted(reasons.items())),
        "policy": "note-local mixture plus cross-stem spectral validation",
    }
    return master
