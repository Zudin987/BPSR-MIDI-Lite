"""Provider-level wiring for note-local audio validation.

The validator runs inside the existing isolated provider process, after Transkun
or Basic Pitch has produced notes but before that result is cached by Studio.
This keeps stale hallucinations out of every later fusion/arrangement stage and
needs no extra model/runtime.
"""
from __future__ import annotations

from pathlib import Path

from .audio_note_guard import validate_master_notes
from .music import BeatMap, MasterSong, MusicEvent

_PATCHED = False


def _validation_files(audio: Path) -> tuple[dict[str, Path], Path | None]:
    parent = audio.parent
    stems = {}
    for name in ("vocals", "piano", "guitar", "bass", "drums", "other"):
        direct = parent / f"{name}.wav"
        if direct.is_file():
            stems[name] = direct
    # Normal layout is <job>/stems/<stage-key>/<stem>.wav.
    mixture = None
    if len(audio.parents) >= 3:
        candidate = audio.parents[2] / "prepared.wav"
        if candidate.is_file():
            mixture = candidate
    return stems, mixture


def _guard_result(result: dict, payload: dict, source: str) -> dict:
    if source not in {"piano", "guitar"} or not result.get("events"):
        return result
    audio = Path(payload.get("audio", ""))
    if not audio.is_file():
        return result
    stems, mixture = _validation_files(audio)
    if mixture is None or not {"piano", "guitar"}.issubset(stems):
        return result

    events = []
    for record in result.get("events", []):
        event = MusicEvent.from_dict(record)
        if event.source == source:
            events.append(event)
    if not events:
        return result

    duration = max((event.end for event in events), default=.001)
    master = MasterSong("provider-audio-validation", duration, BeatMap(), list(events))
    try:
        validate_master_notes(master, stems, mixture)
    except (ImportError, ModuleNotFoundError, OSError, RuntimeError, ValueError) as exc:
        # This is a quality guard, never a reason to throw away an otherwise
        # valid specialist transcription. Record the skip for diagnostics.
        guarded = dict(result)
        guarded.setdefault("warnings", []).append(
            f"Audio-grounded {source} note validation was skipped: {exc}"
        )
        return guarded

    guarded = dict(result)
    guarded["events"] = [event.to_dict() for event in master.events]
    provenance = dict(guarded.get("provenance") or {})
    note_guard = dict(master.provenance.get("audio_note_guard") or {})
    note_guard["rejected_events"] = len(master.rejected)
    provenance["audio_note_guard"] = note_guard
    guarded["provenance"] = provenance
    if master.rejected:
        guarded["audio_note_rejections"] = master.rejected
    return guarded


def patch_provider_note_guard(providers_module) -> None:
    """Wrap Basic Pitch guitar/piano fallback and Transkun exactly once."""
    global _PATCHED
    registry = providers_module.PROVIDERS
    if _PATCHED:
        return

    original_basic = registry.get("basic_pitch")
    if original_basic is not None and not getattr(original_basic, "_bpsr_audio_note_guard", False):
        def basic_pitch(payload: dict, report):
            result = original_basic(payload, report)
            return _guard_result(result, payload, str(payload.get("source", "")))

        basic_pitch._bpsr_audio_note_guard = True
        registry["basic_pitch"] = basic_pitch
        try:
            providers_module.basic_pitch = basic_pitch
        except Exception:
            pass

    original_transkun = registry.get("transkun")
    if original_transkun is not None and not getattr(original_transkun, "_bpsr_audio_note_guard", False):
        def transkun(payload: dict, report):
            result = original_transkun(payload, report)
            return _guard_result(result, payload, "piano")

        transkun._bpsr_audio_note_guard = True
        registry["transkun"] = transkun
        try:
            providers_module.transkun = transkun
        except Exception:
            pass

    _PATCHED = True
