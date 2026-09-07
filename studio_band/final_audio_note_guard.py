"""Run note-local piano/guitar audio validation on the final musical map.

The raw specialist providers do not yet know about Aria/MuScriptor/MR-MT3
agreement or repeated-motif tags.  Validating there can delete a real note before
independent evidence gets a chance to protect it.  This hook captures the resolved
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


def apply_final_audio_note_guard() -> None:
    global _APPLIED
    if _APPLIED:
        return

    from . import fusion, pipeline
    from .audio_note_guard import validate_master_notes

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
            if stems and mixture and Path(mixture).is_file():
                validate_master_notes(master, stems, Path(mixture))
            else:
                master.provenance["audio_note_guard"] = {
                    "version": 1,
                    "checked": 0,
                    "removed": 0,
                    "skipped": "resolved stems or prepared mixture unavailable",
                }
        except (ImportError, ModuleNotFoundError, OSError, RuntimeError, ValueError) as exc:
            # Quality validation must never turn a usable transcription into a
            # failed conversion. Keep the musical-map result and expose why the
            # final audio check could not run.
            master.warnings.append(f"Final audio-grounded note validation was skipped: {exc}")
            master.provenance["audio_note_guard"] = {
                "version": 1,
                "checked": 0,
                "removed": 0,
                "skipped": str(exc),
            }
        finally:
            _clear_context()
        return master

    fusion.build_master = build_master
    # pipeline imported build_master by value; keep the active conversion path synced.
    pipeline.build_master = build_master
    _APPLIED = True
