from __future__ import annotations

import contextvars
from bisect import bisect_left, bisect_right
from dataclasses import replace
from pathlib import Path
from typing import Any

import midi_engine as me
import playback_adaptive as adaptive
import playback_overhaul as po


_attack_rate_context: contextvars.ContextVar[float] = contextvars.ContextVar(
    "bpsr_adaptive_attack_rate", default=0.0
)
_original_preanalyse: Any = None


def _attack_anchors(starts: list[float], window: float = 0.015) -> list[float]:
    anchors: list[float] = []
    anchor: float | None = None
    for value in sorted(starts):
        if anchor is None or value - anchor > window:
            anchor = value
            anchors.append(value)
    return anchors


def _attack_rate_for_starts(starts: list[float], window: float = 0.250) -> float:
    anchors = _attack_anchors(starts)
    return adaptive._window_peak(anchors, window) if anchors else 0.0


def _refined_preanalyse(path: Path) -> adaptive.SourceAnalysis:
    assert _original_preanalyse is not None
    analysis = _original_preanalyse(path)
    try:
        starts = [
            candidate.start
            for candidate in adaptive._collect_candidates(Path(path))
            if candidate.channel != 9
        ]
        _attack_rate_context.set(_attack_rate_for_starts(starts))
    except Exception:
        _attack_rate_context.set(0.0)
    return analysis


def _refined_auto_tune(
    options: adaptive.AdaptivePlanOptions,
    analysis: adaptive.SourceAnalysis,
    calibration: adaptive.CalibrationProfile,
) -> adaptive.AdaptivePlanOptions:
    if not options.adaptive_auto or options.mapping_method == "skip":
        return options
    tuned = replace(
        options,
        minimum_note_ms=calibration.minimum_clean_hold_ms,
        hard_press_floor_ms=calibration.hard_floor_ms,
        repeated_release_gap_ms=calibration.retrigger_gap_ms,
        adaptive_chord_limit=options.adaptive_chord_limit or calibration.max_polyphony,
        chord_stagger_ms=(
            calibration.chord_stagger_ms
            if options.chord_stagger_ms < 0
            else options.chord_stagger_ms
        ),
        octave_switch_lead_ms=max(
            options.octave_switch_lead_ms,
            calibration.modifier_settle_ms,
        ),
    )
    limit = tuned.adaptive_chord_limit or adaptive.ADAPTIVE_DEFAULTS[options.instrument].max_polyphony
    if tuned.max_notes_per_chord <= 0 and analysis.max_chord > limit:
        tuned.max_notes_per_chord = limit

    attack_rate = _attack_rate_context.get()
    if attack_rate >= 12.0 or analysis.fast_repeat_ratio >= 0.20:
        tuned.articulation_mode = "dense"
    elif attack_rate >= 8.0 and tuned.articulation_mode == "musical":
        tuned.articulation_mode = "balanced"
    return tuned


def _refined_apply_note_lengths(
    notes: list[me.PlannedNote],
    options: Any,
) -> list[me.PlannedNote]:
    tuned = adaptive._coerce_adaptive_options(options)
    if not notes:
        return []

    ordered = sorted(notes, key=lambda note: (note.start, note.serial))
    starts = [note.start for note in ordered]
    cluster_window = max(0.005, tuned.attack_cluster_ms / 1000.0)

    attack_anchors: list[float] = []
    anchor_for_note: list[float] = []
    anchor: float | None = None
    for value in starts:
        if anchor is None or value - anchor > cluster_window:
            anchor = value
            attack_anchors.append(value)
        anchor_for_note.append(anchor)

    attack_densities = [
        (
            bisect_right(attack_anchors, value + 0.250)
            - bisect_left(attack_anchors, value - 0.250)
        )
        / 0.5
        for value in anchor_for_note
    ]

    next_same_key: list[float | None] = [None] * len(ordered)
    upcoming_by_key: dict[str, float] = {}
    for index in range(len(ordered) - 1, -1, -1):
        note = ordered[index]
        next_same_key[index] = upcoming_by_key.get(note.key)
        upcoming_by_key[note.key] = note.start

    hard_floor = tuned.resolved_hard_floor_ms / 1000.0
    release_gap = tuned.resolved_release_gap_ms / 1000.0
    result: list[me.PlannedNote] = []

    for index, note in enumerate(ordered):
        source_duration = max(0.001, note.end - note.start)
        base = po._desired_note_duration(source_duration, tuned)
        target = base * adaptive._register_scale(tuned.instrument, note.pitch)
        following = ordered[index + 1].start if index + 1 < len(ordered) else None

        if following is not None:
            onset_gap = max(0.001, following - note.start)
            gate_ratio = source_duration / onset_gap
            if gate_ratio < 0.45:
                target = min(
                    target,
                    max(
                        hard_floor,
                        source_duration + tuned.resolved_short_tail_ms / 2000.0,
                    ),
                )
            elif gate_ratio > 0.92 and note.key != ordered[index + 1].key:
                target = max(
                    target,
                    min(onset_gap + 0.030, base + 0.050),
                )

        attack_density = attack_densities[index]
        if attack_density >= 12.0:
            target *= 0.70
        elif attack_density >= 8.0:
            target *= 0.80
        elif attack_density >= 5.0:
            target *= 0.90

        if following is None or following - note.start > 0.35:
            target += min(0.045, tuned.resolved_short_tail_ms / 1000.0)

        if next_same_key[index] is not None:
            target = min(
                target,
                max(
                    hard_floor,
                    next_same_key[index] - note.start - release_gap,
                ),
            )

        target = max(hard_floor, target)
        result.append(replace(note, end=note.start + target))

    result.sort(key=lambda note: (note.start, note.serial))
    return result


def install_adaptive_pressure_model(app_module: Any) -> None:
    global _original_preanalyse
    if getattr(app_module, "_adaptive_pressure_model_installed", False):
        return
    _original_preanalyse = adaptive._preanalyse
    adaptive._preanalyse = _refined_preanalyse
    adaptive._auto_tune_options = _refined_auto_tune
    adaptive._adaptive_apply_note_lengths = _refined_apply_note_lengths
    me._apply_note_lengths = _refined_apply_note_lengths
    app_module._adaptive_pressure_model_installed = True
