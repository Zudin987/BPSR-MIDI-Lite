"""Run note-local piano/guitar validation on the final musical map.

The raw specialist providers do not yet know about Aria/MuScriptor/MR-MT3
agreement or repeated-motif tags. Validating there can delete a real note before
independent evidence gets a chance to protect it. This hook captures the resolved
stems during separation, then validates only after beta.9 fusion + pitch cleanup
and still before BPSR range/octave mapping.
"""
from __future__ import annotations

from pathlib import Path
import threading

_APPLIED = False
_CONTEXT = threading.local()


def _clear_context() -> None:
    for name in ("stems", "mixture"):
        try:
            delattr(_CONTEXT, name)
        except AttributeError:
            pass


def _skip(master, key: str, reason: str) -> None:
    master.provenance[key] = {
        "version": 1,
        "checked": 0,
        "removed": 0,
        "skipped": reason,
    }


def apply_final_audio_note_guard() -> None:
    global _APPLIED
    if _APPLIED:
        return

    from . import fusion, pipeline
    from .audio_note_guard import validate_master_notes
    from .rhythm_attack_guard import validate_rhythm_attacks

    original_stage = pipeline.BandPipeline._stage

    def stage(self, client, job, provider, audio, payload, cancel, report, warnings,
              settings, hardware):
        result = original_stage(
            self, client, job, provider, audio, payload, cancel, report, warnings,
            settings, hardware,
        )
        if provider == "demucs" and result.get("stems"):
            _CONTEXT.stems = {
                name: Path(path) for name, path in result["stems"].items()
                if name in {"vocals", "piano", "guitar", "bass", "drums", "other"}
            }
            _CONTEXT.mixture = Path(job) / "prepared.wav"
        return result

    pipeline.BandPipeline._stage = stage

    # At this point fusion/build_master already contains beta.9 agreement,
    # instrument-presence decisions, repeated-motif tags and the rhythm guard.
    original_build_master = fusion.build_master

    def build_master(digest, duration, beats, primary, reference, provenance, warnings):
        master = original_build_master(
            digest, duration, beats, primary, reference, provenance, warnings
        )
        stems = getattr(_CONTEXT, "stems", None)
        mixture = getattr(_CONTEXT, "mixture", None)
        try:
            if not (stems and mixture and Path(mixture).is_file()):
                reason = "resolved stems or prepared mixture unavailable"
                _skip(master, "audio_note_guard", reason)
                _skip(master, "rhythm_attack_guard", reason)
                return master

            try:
                validate_master_notes(master, stems, Path(mixture))
            except (ImportError, ModuleNotFoundError, OSError, RuntimeError, ValueError) as exc:
                # The original spectral quality layer remains optional: a usable
                # transcription should never become a failed conversion.
                master.warnings.append(f"Final audio-grounded note validation was skipped: {exc}")
                _skip(master, "audio_note_guard", str(exc))

            try:
                # This second pass solves the narrower case where a pitch really
                # exists in the audio, but the decoder invented a new off-rhythm
                # re-trigger on top of a sustained harmonic.
                validate_rhythm_attacks(master, stems, Path(mixture))
            except (ImportError, ModuleNotFoundError, OSError, RuntimeError, ValueError) as exc:
                master.warnings.append(f"Final rhythm/onset note validation was skipped: {exc}")
                _skip(master, "rhythm_attack_guard", str(exc))
            return master
        finally:
            _clear_context()

    fusion.build_master = build_master
    # pipeline imported build_master by value; keep the active conversion path synced.
    pipeline.build_master = build_master
    _APPLIED = True
