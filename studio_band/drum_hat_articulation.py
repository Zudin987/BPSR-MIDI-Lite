"""Recover open/closed hi-hat articulation from DrumSep's shared hh stem."""
from __future__ import annotations


def _tail_ratio(samples, sample_rate: int, onset: float) -> float:
    """Return post-attack energy relative to the initial hat attack."""
    import numpy as np

    audio = np.asarray(samples, dtype="float32")
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    start = max(0, round(float(onset) * sample_rate))
    attack = audio[start:min(len(audio), start + round(.030 * sample_rate))]
    tail = audio[
        min(len(audio), start + round(.045 * sample_rate)):
        min(len(audio), start + round(.150 * sample_rate))
    ]
    if not len(attack) or not len(tail):
        return 0.0
    attack_rms = float(np.sqrt(np.mean(attack * attack) + 1e-12))
    tail_rms = float(np.sqrt(np.mean(tail * tail) + 1e-12))
    return max(0.0, min(2.0, tail_rms / max(attack_rms, 1e-9)))


def _patch_drumsep_hat_articulation(providers) -> None:
    """Wrap DrumSep so its hh stem can emit OPEN_HAT as well as CLOSED_HAT."""
    original = providers._legacy.PROVIDERS.get("drumsep")
    if original is None or getattr(original, "_bpsr_hat_articulation", False):
        return

    def drumsep(payload: dict, report) -> dict:
        import soundfile as sf

        result = original(payload, report)
        hh_path = result.get("stems", {}).get("hh")
        if not hh_path:
            return result
        try:
            samples, sample_rate = sf.read(str(hh_path), dtype="float32", always_2d=True)
        except Exception:
            return result

        open_count = 0
        for event in result.get("events", []):
            if event.get("source") != "drums" or event.get("role") != "CLOSED_HAT":
                continue
            ratio = _tail_ratio(samples, int(sample_rate), float(event.get("start", 0.0)))
            evidence = dict(event.get("evidence") or {})
            evidence["hat_tail_ratio"] = ratio
            evidence["hat_articulation"] = "decay_from_isolated_hh_stem"
            event["evidence"] = evidence
            # Open hats retain substantially more isolated-hat energy after the
            # first 45 ms. Keep the threshold conservative to avoid turning
            # ordinary closed hats into long open-hat splashes.
            if ratio >= .30:
                event["role"] = "OPEN_HAT"
                event["end"] = max(float(event.get("end", 0.0)), float(event["start"]) + .090)
                event["tags"] = sorted(set(event.get("tags", [])) | {"open_hat_decay"})
                open_count += 1
        result.setdefault("provenance", {})["open_hat_decay_classifier"] = {
            "threshold": .30,
            "open_hat_events": open_count,
        }
        return result

    drumsep._bpsr_hat_articulation = True
    providers._legacy.PROVIDERS["drumsep"] = drumsep
    providers.PROVIDERS = providers._legacy.PROVIDERS
