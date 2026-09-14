"""Refine DrumSep's single hi-hat stem into open/closed BPSR semantics."""
from __future__ import annotations


def _hat_sustain_ratio(audio, sample_rate: int, onset: float) -> float:
    """Return post-attack RMS / attack RMS for one separated hi-hat hit."""
    import numpy as np

    samples = np.asarray(audio, dtype="float32")
    if samples.ndim == 2:
        samples = samples.mean(axis=1)
    elif samples.ndim != 1:
        samples = samples.reshape(-1)
    center = max(0, min(len(samples), round(float(onset) * sample_rate)))
    attack_end = min(len(samples), center + max(1, round(.025 * sample_rate)))
    tail_start = min(len(samples), center + max(1, round(.040 * sample_rate)))
    tail_end = min(len(samples), center + max(1, round(.140 * sample_rate)))
    attack = samples[center:attack_end]
    tail = samples[tail_start:tail_end]
    if not len(attack):
        return 0.0
    attack_rms = float(np.sqrt(np.mean(attack * attack) + 1e-12))
    tail_rms = float(np.sqrt(np.mean(tail * tail) + 1e-12)) if len(tail) else 0.0
    return max(0.0, min(2.0, tail_rms / max(attack_rms, 1e-8)))


def _patch_provider(providers) -> None:
    legacy = providers._legacy
    original = legacy.PROVIDERS.get("drumsep")
    if original is None or getattr(original, "_bpsr_hat_semantics", False):
        return

    def drumsep(payload: dict, report):
        result = original(payload, report)
        hh_path = result.get("stems", {}).get("hh")
        if not hh_path:
            return result
        try:
            audio, sample_rate = legacy._audio(hh_path)
        except Exception:
            return result
        changed = 0
        for event in result.get("events", []):
            if event.get("engine") != "drumsep" or event.get("role") != "CLOSED_HAT":
                continue
            ratio = _hat_sustain_ratio(audio, int(sample_rate), float(event.get("start", 0.0)))
            evidence = dict(event.get("evidence") or {})
            evidence["hat_sustain_ratio"] = round(ratio, 6)
            evidence["hat_semantic_split"] = "decay-envelope"
            event["evidence"] = evidence
            if ratio >= .24:
                event["role"] = "OPEN_HAT"
                event["end"] = max(float(event.get("end", 0.0)), float(event.get("start", 0.0)) + .12)
                event["tags"] = sorted(set(event.get("tags", [])) | {"open_hat_decay"})
                changed += 1
        result.setdefault("provenance", {})["open_hat_splits"] = changed
        return result

    drumsep._bpsr_hat_semantics = True
    legacy.PROVIDERS["drumsep"] = drumsep


def apply_drumsep_hat_patch() -> None:
    from . import providers

    _patch_provider(providers)
