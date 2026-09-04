from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, fields, replace
from statistics import median
from typing import Any

import midi_engine as me
import playback_adaptive as adaptive
import playback_adaptive_ui as adaptive_ui
import playback_arranger_refinements as arranger_refinements
import gaming_runtime_2026 as gaming_runtime
import gaming_ui_2026 as gaming_ui


_ATTACK_WINDOW_SECONDS = 0.015
_MIN_RELIABLE_BASS_NOTES = 8
_MIN_RELIABLE_BASS_ATTACK_COVERAGE = 0.12

_previous_collect_candidates: Any = None
_previous_limit_notes_per_chord: Any = None
_previous_to_adaptive_plan: Any = None
_previous_arrangement_impact_text: Any = None
_previous_render_visualizer: Any = None


@dataclass(slots=True)
class EvidenceAdaptiveMidiPlan(adaptive.AdaptiveMidiPlan):
    """Adaptive plan with explicit provenance for intentional arrangement edits."""

    arranged_out_notes: int = 0
    bass_line_notes: int = 0
    arrangement_strategy: str = "adaptive"


def _attack_groups_candidates(notes: list[Any]) -> list[list[Any]]:
    ordered = sorted(notes, key=lambda item: (float(item.start), int(item.pitch)))
    groups: list[list[Any]] = []
    anchor: float | None = None
    for note in ordered:
        start = float(note.start)
        if anchor is None or start - anchor > _ATTACK_WINDOW_SECONDS:
            groups.append([])
            anchor = start
        groups[-1].append(note)
    return groups


def _attack_count_source(notes: list[me.SourceNote]) -> int:
    if not notes:
        return 0
    starts = sorted(float(note.start) for note in notes)
    count = 0
    anchor: float | None = None
    for start in starts:
        if anchor is None or start - anchor > _ATTACK_WINDOW_SECONDS:
            anchor = start
            count += 1
    return count


def _candidate_stream_key(candidate: Any) -> tuple[int, int, int]:
    return int(candidate.track_index), int(candidate.channel), int(candidate.program)


def _is_generic_chord_stream(notes: list[Any]) -> bool:
    if len(notes) < 12:
        return False
    if any(arranger_refinements._name_role(str(note.track_name)) is not None for note in notes):
        return False
    harmony = sum(getattr(note, "role", "unknown") == "harmony" for note in notes)
    return harmony / max(1, len(notes)) >= 0.80


def _mark_stream_envelope(
    role_by_identity: dict[int, str],
    notes: list[Any],
    *,
    role: str,
    high: bool,
) -> None:
    for group in _attack_groups_candidates(notes):
        if not group:
            continue
        if high:
            chosen = max(group, key=lambda item: (int(item.pitch), int(item.velocity)))
        else:
            chosen = min(group, key=lambda item: (int(item.pitch), -int(item.velocity)))
        role_by_identity[id(chosen)] = role


def _refine_polyphonic_roles(candidates: list[Any]) -> list[Any]:
    """Recover top-melody and low-bass envelopes from dense generic piano.

    The v3.3 stream classifier intentionally calls chord-heavy material
    ``harmony``. That is safe for generic accompaniment, but on a two-hand
    piano MIDI it erases both outer voices. Keep inner notes as harmony while
    exposing one top and one bottom voice per attack to the existing role-aware
    continuity and collision scorers.
    """

    if not candidates:
        return []

    by_stream: dict[tuple[int, int, int], list[Any]] = defaultdict(list)
    for candidate in candidates:
        by_stream[_candidate_stream_key(candidate)].append(candidate)

    generic = [notes for notes in by_stream.values() if _is_generic_chord_stream(notes)]
    if not generic:
        return list(candidates)

    role_by_identity: dict[int, str] = {}
    if len(generic) >= 2:
        ordered = sorted(generic, key=lambda notes: float(median(int(item.pitch) for item in notes)))
        low = ordered[0]
        high = ordered[-1]
        low_median = float(median(int(item.pitch) for item in low))
        high_median = float(median(int(item.pitch) for item in high))
        # A real register split is required before inventing separate hands.
        if high_median - low_median >= 7.0:
            _mark_stream_envelope(role_by_identity, high, role="melody", high=True)
            _mark_stream_envelope(role_by_identity, low, role="bass", high=False)
    else:
        stream = generic[0]
        pitches = [int(item.pitch) for item in stream]
        if pitches and max(pitches) - min(pitches) >= 24:
            # Conservative one-track piano fallback: only spread block attacks
            # receive envelope roles. Single notes and close clusters stay as-is.
            for group in _attack_groups_candidates(stream):
                if len(group) < 2:
                    continue
                low = min(group, key=lambda item: (int(item.pitch), -int(item.velocity)))
                high = max(group, key=lambda item: (int(item.pitch), int(item.velocity)))
                if int(high.pitch) - int(low.pitch) < 7:
                    continue
                role_by_identity[id(high)] = "melody"
                role_by_identity[id(low)] = "bass"

    if not role_by_identity:
        return list(candidates)
    return [
        replace(candidate, role=role_by_identity.get(id(candidate), candidate.role))
        for candidate in candidates
    ]


def _evidence_collect_candidates(path: Any) -> list[Any]:
    assert _previous_collect_candidates is not None
    return _refine_polyphonic_roles(list(_previous_collect_candidates(path)))


def _reliable_bass_line(
    notes: list[me.SourceNote],
    metadata: dict[int, adaptive.SourceMeta],
) -> list[me.SourceNote] | None:
    bass = [
        note
        for note in notes
        if metadata.get(note.serial) is not None and metadata[note.serial].role == "bass"
    ]
    if len(bass) < _MIN_RELIABLE_BASS_NOTES:
        return None
    all_attacks = _attack_count_source(notes)
    bass_attacks = _attack_count_source(bass)
    coverage = bass_attacks / max(1, all_attacks)
    if coverage < _MIN_RELIABLE_BASS_ATTACK_COVERAGE:
        return None
    return bass


def _evidence_limit_notes_per_chord(
    notes: list[me.SourceNote],
    maximum: int,
    instrument: me.InstrumentCode = "keyboard",
) -> tuple[list[me.SourceNote], int]:
    assert _previous_limit_notes_per_chord is not None
    options = adaptive._options_context.get()
    metadata = adaptive._metadata_context.get() or {}

    if (
        instrument != "bass"
        or options is None
        or not options.adaptive_auto
        or options.mapping_method == "skip"
    ):
        return _previous_limit_notes_per_chord(notes, maximum, instrument)

    bass = _reliable_bass_line(notes, metadata)
    if bass is None or len(bass) >= len(notes):
        return _previous_limit_notes_per_chord(notes, maximum, instrument)

    arranged_out = len(notes) - len(bass)
    metrics = adaptive._metrics_context.get()
    if metrics is not None:
        metrics["arranged_out_notes"] = metrics.get("arranged_out_notes", 0) + arranged_out
        metrics["bass_line_notes"] = len(bass)

    kept, physically_removed = _previous_limit_notes_per_chord(bass, maximum, instrument)
    # Intentional arrangement is not a filter failure. Keep the base engine's
    # filtered/chord-removed metrics reserved for notes lost to physical limits.
    return kept, physically_removed


def _evidence_to_adaptive_plan(*args: Any, **kwargs: Any) -> EvidenceAdaptiveMidiPlan:
    assert _previous_to_adaptive_plan is not None
    result = _previous_to_adaptive_plan(*args, **kwargs)
    metrics = kwargs.get("metrics") or {}
    arranged_out = max(0, int(metrics.get("arranged_out_notes", 0)))
    bass_line = max(0, int(metrics.get("bass_line_notes", 0)))
    values = {field.name: getattr(result, field.name) for field in fields(adaptive.AdaptiveMidiPlan)}
    strategy = "auto_bass_line" if arranged_out and bass_line else "adaptive"
    if strategy == "auto_bass_line":
        detail = f"Auto Bass Line {bass_line} note(s); {arranged_out} non-bass source note(s) omitted"
        summary = str(values.get("arranger_summary", "")).strip()
        values["arranger_summary"] = f"{summary} • {detail}" if summary else detail
    return EvidenceAdaptiveMidiPlan(
        **values,
        arranged_out_notes=arranged_out,
        bass_line_notes=bass_line,
        arrangement_strategy=strategy,
    )


def _evidence_arrangement_impact_text(plan: Any) -> str:
    assert _previous_arrangement_impact_text is not None
    arranged = max(0, int(getattr(plan, "arranged_out_notes", 0))) if plan is not None else 0
    if arranged <= 0:
        return _previous_arrangement_impact_text(plan)

    source = max(0, int(getattr(plan, "source_note_count", 0)))
    played = max(0, int(getattr(plan, "note_count", 0)))
    bass_line = max(0, int(getattr(plan, "bass_line_notes", 0)))
    physical_removed = max(
        0,
        int(getattr(plan, "chord_removed_notes", 0))
        + int(getattr(plan, "skipped_notes", 0))
        + int(getattr(plan, "retrigger_dropped_notes", 0)),
    )
    transposition = int(getattr(plan, "transposed_semitones", 0))
    folded = max(0, int(getattr(plan, "folded_notes", 0)))
    if transposition:
        fitting = f"transposed {transposition:+d} st"
        if folded:
            fitting += f" + {folded} local fits"
    else:
        fitting = f"{max(0, int(getattr(plan, 'remapped_notes', 0)))} pitch-fitted"
    source_low = me.midi_note_name(getattr(plan, "source_min_pitch", None))
    source_high = me.midi_note_name(getattr(plan, "source_max_pitch", None))
    planned_low = me.midi_note_name(getattr(plan, "planned_min_pitch", None))
    planned_high = me.midi_note_name(getattr(plan, "planned_max_pitch", None))
    return (
        f"Auto Bass Line • selected {bass_line} bass-role notes from {source} source notes "
        f"({source_low}–{source_high}) → {played} playable ({planned_low}–{planned_high}) • "
        f"{arranged} non-bass omitted intentionally • {fitting} • "
        f"{physical_removed} physical removals"
    )


def _rewrite_analysis_for_arrangement(app: Any) -> None:
    plan = getattr(app, "current_plan", None)
    arranged = max(0, int(getattr(plan, "arranged_out_notes", 0))) if plan is not None else 0
    if arranged <= 0:
        return
    try:
        # Modern UI already reports filtered_notes. Those metrics now contain
        # physical/destructive loss only; append arrangement provenance without
        # rewriting the existing counts.
        text = str(app.analysis_var.get())
        bass_line = max(0, int(getattr(plan, "bass_line_notes", 0)))
        text += (
            f"\nArrangement • Auto Bass Line selected {bass_line:,} bass-role notes; "
            f"{arranged:,} non-bass source notes were intentionally omitted."
        )
        app.analysis_var.set(text)
        if hasattr(app, "_adaptive_impact_var"):
            app._adaptive_impact_var.set(_evidence_arrangement_impact_text(plan))
    except Exception:
        return


def _evidence_render_visualizer(app: Any) -> None:
    assert _previous_render_visualizer is not None
    _previous_render_visualizer(app)
    plan = getattr(app, "current_plan", None)
    if getattr(plan, "arrangement_strategy", "") != "auto_bass_line":
        return
    try:
        app._gaming_router_var.set(
            f"Auto Bass Line • {int(plan.bass_line_notes):,} bass-role notes selected • "
            f"{int(plan.arranged_out_notes):,} non-bass omitted"
        )
    except Exception:
        pass


def install_evidence_refinements(app_module: Any) -> None:
    """Install refinements derived from real BPSR playback + representative MIDIs."""

    global _previous_collect_candidates, _previous_limit_notes_per_chord
    global _previous_to_adaptive_plan, _previous_arrangement_impact_text
    global _previous_render_visualizer

    if getattr(app_module, "_evidence_refinements_installed", False):
        return

    _previous_collect_candidates = adaptive._collect_candidates
    _previous_limit_notes_per_chord = me._limit_notes_per_chord
    _previous_to_adaptive_plan = adaptive._to_adaptive_plan
    _previous_arrangement_impact_text = adaptive_ui.arrangement_impact_text
    _previous_render_visualizer = gaming_runtime._render_visualizer

    adaptive._collect_candidates = _evidence_collect_candidates
    me._limit_notes_per_chord = _evidence_limit_notes_per_chord
    adaptive._to_adaptive_plan = _evidence_to_adaptive_plan
    adaptive_ui.arrangement_impact_text = _evidence_arrangement_impact_text

    app_class = app_module.App
    original_analyze = app_class._analyze

    def analyze(self: Any) -> None:
        original_analyze(self)
        _rewrite_analysis_for_arrangement(self)

    app_class._analyze = analyze

    gaming_runtime._render_visualizer = _evidence_render_visualizer
    gaming_ui._render_visualizer = _evidence_render_visualizer

    app_module._evidence_refinements_installed = True
