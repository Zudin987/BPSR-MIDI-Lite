from __future__ import annotations

import contextvars
import math
import sys
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
_attack_metrics_context: contextvars.ContextVar[tuple[float, float]] = contextvars.ContextVar(
    "bpsr_adaptive_attack_metrics", default=(0.0, 0.0)
)
_original_preanalyse: Any = None
_original_to_adaptive_plan: Any = None
_original_evaluate: Any = None


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


def _attack_pressure_metrics(starts: list[float]) -> tuple[float, float]:
    anchors = _attack_anchors(starts)
    if not anchors:
        return 0.0, 0.0
    peak = adaptive._window_peak(anchors, 0.250)
    rates = sorted(adaptive._window_rates(anchors, 0.500))
    p95 = rates[max(0, math.ceil(len(rates) * 0.95) - 1)] if rates else 0.0
    return peak, p95


def _refined_preanalyse(path: Path) -> adaptive.SourceAnalysis:
    assert _original_preanalyse is not None
    analysis = _original_preanalyse(path)
    try:
        starts = [
            candidate.start
            for candidate in adaptive._collect_candidates(Path(path))
            if candidate.channel != 9
        ]
        peak, p95 = _attack_pressure_metrics(starts)
        _attack_rate_context.set(peak)
        _attack_metrics_context.set((peak, p95))
    except Exception:
        _attack_rate_context.set(0.0)
        _attack_metrics_context.set((0.0, 0.0))
    return analysis


def _refined_auto_tune(
    options: adaptive.AdaptivePlanOptions,
    analysis: adaptive.SourceAnalysis,
    calibration: adaptive.CalibrationProfile,
) -> adaptive.AdaptivePlanOptions:
    if not options.adaptive_auto or options.mapping_method == "skip":
        return options

    # Timing defaults are inherited from v3.2 and are intentionally conservative.
    # A new polyphony cap is different: dropping chord tones is destructive, so
    # only an explicitly authorized calibration layer may introduce one.
    measured_limit = (
        options.adaptive_chord_limit
        or (calibration.max_polyphony if calibration.calibrated else 0)
    )
    tuned = replace(
        options,
        minimum_note_ms=calibration.minimum_clean_hold_ms,
        hard_press_floor_ms=calibration.hard_floor_ms,
        repeated_release_gap_ms=calibration.retrigger_gap_ms,
        adaptive_chord_limit=measured_limit,
        chord_stagger_ms=(
            calibration.chord_stagger_ms
            if calibration.calibrated and options.chord_stagger_ms < 0
            else (0 if options.chord_stagger_ms < 0 else options.chord_stagger_ms)
        ),
        octave_switch_lead_ms=(
            max(options.octave_switch_lead_ms, calibration.modifier_settle_ms)
            if calibration.calibrated
            else options.octave_switch_lead_ms
        ),
    )
    if (
        measured_limit > 0
        and tuned.max_notes_per_chord <= 0
        and analysis.max_chord > measured_limit
    ):
        tuned.max_notes_per_chord = measured_limit

    attack_rate = _attack_rate_context.get()
    if attack_rate >= 12.0 or analysis.fast_repeat_ratio >= 0.20:
        tuned.articulation_mode = "dense"
    elif attack_rate >= 8.0 and tuned.articulation_mode == "musical":
        tuned.articulation_mode = "balanced"
    return tuned


def _refined_limit_notes_per_chord(
    notes: list[me.SourceNote],
    maximum: int,
    instrument: me.InstrumentCode = "keyboard",
) -> tuple[list[me.SourceNote], int]:
    options = adaptive._options_context.get()
    if options is None:
        return adaptive._adaptive_limit_notes_per_chord(notes, maximum, instrument)
    if options.adaptive_auto and options.adaptive_chord_limit <= 0:
        # Preserve root/role-aware scoring for an existing fixed-profile limit,
        # but do not invent a new limit from unmeasured fallback polyphony.
        token = adaptive._options_context.set(replace(options, adaptive_auto=False))
        try:
            return adaptive._adaptive_limit_notes_per_chord(notes, maximum, instrument)
        finally:
            adaptive._options_context.reset(token)
    return adaptive._adaptive_limit_notes_per_chord(notes, maximum, instrument)


def _next_attack_by_note(
    anchors: list[float],
    anchor_for_note: list[float],
) -> list[float | None]:
    index_by_anchor = {value: index for index, value in enumerate(anchors)}
    result: list[float | None] = []
    for anchor in anchor_for_note:
        index = index_by_anchor[anchor]
        result.append(anchors[index + 1] if index + 1 < len(anchors) else None)
    return result


def _refined_apply_note_lengths(
    notes: list[me.PlannedNote],
    options: Any,
) -> list[me.PlannedNote]:
    tuned = adaptive._coerce_adaptive_options(options)
    if not notes:
        return []
    if not tuned.adaptive_auto:
        # Custom and Raw remain manual: keep v3.2's explicit articulation and
        # hard-floor behavior instead of adding register/density/phrase shaping.
        return po._enhanced_apply_note_lengths(notes, tuned)

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

    next_attack_for_note = _next_attack_by_note(attack_anchors, anchor_for_note)
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
        attack_anchor = anchor_for_note[index]
        following_attack = next_attack_for_note[index]

        if following_attack is not None:
            onset_gap = max(0.001, following_attack - attack_anchor)
            gate_ratio = source_duration / onset_gap
            if gate_ratio < 0.45:
                target = min(
                    target,
                    max(
                        hard_floor,
                        source_duration + tuned.resolved_short_tail_ms / 2000.0,
                    ),
                )
            elif gate_ratio > 0.92:
                same_key_next = next_same_key[index]
                same_key_at_next_attack = (
                    same_key_next is not None
                    and abs(same_key_next - following_attack) <= cluster_window
                )
                if not same_key_at_next_attack:
                    target = max(
                        target,
                        min(onset_gap + 0.030, base + 0.050),
                    )

        if attack_densities[index] >= 12.0:
            target *= 0.70
        elif attack_densities[index] >= 8.0:
            target *= 0.80
        elif attack_densities[index] >= 5.0:
            target *= 0.90

        if following_attack is None or following_attack - attack_anchor > 0.35:
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


def _refined_to_adaptive_plan(*args: Any, **kwargs: Any):
    assert _original_to_adaptive_plan is not None
    result = _original_to_adaptive_plan(*args, **kwargs)
    peak, p95 = _attack_metrics_context.get()
    # Timing pressure should count distinct attacks, not every chord tone. Chord
    # size is already represented separately by max_source_chord/max_planned_chord.
    result.local_peak_nps = float(peak)
    result.p95_window_nps = float(p95)

    parts = [part for part in str(result.arranger_summary).split(" • ") if part]
    tail = [part for part in parts if not part.startswith("peak ") and not part.startswith("p95 ")]
    result.arranger_summary = " • ".join(
        [f"peak {peak:.1f} attacks/s", f"p95 {p95:.1f} attacks/s", *tail]
    )
    return result


def _legacy_density_penalty(notes_per_second: float) -> int:
    """Return the v3.2 suitability points assigned to raw note density."""
    if notes_per_second >= 10.0:
        return 3
    if notes_per_second >= 6.0:
        return 2
    if notes_per_second >= 3.5:
        return 1
    return 0


def _adaptive_score_label(score: int) -> tuple[str, str, str]:
    if score >= 7:
        return (
            "complex",
            "Very complex",
            "Adaptive arranger can simplify it, but the busiest passages may still exceed BPSR input limits.",
        )
    if score >= 3:
        return (
            "busy",
            "Busy",
            "Adaptive arranger will thin/reshape the busiest passages while protecting melody and bass roles.",
        )
    return (
        "good",
        "Good fit",
        "Adaptive arranger should translate this cleanly with the selected BPSR instrument.",
    )


def _refined_evaluate_song_suitability(plan: Any):
    assert _original_evaluate is not None
    result = _original_evaluate(plan)
    if not getattr(plan, "adaptive_enabled", False):
        return result

    # The legacy score treats every simultaneous chord tone as another note per
    # second. Adaptive playback already models chord size separately and models
    # timing pressure using distinct attack clusters, so keeping the legacy raw
    # density points would double-penalize block chords. Remove only that known
    # legacy component; retain chord/remap/retrigger/track/control penalties.
    raw_density_prefixes = (
        "very fast note density (",
        "fast note density (",
        "moderate note density (",
    )
    had_raw_density_reason = any(
        str(reason).startswith(raw_density_prefixes) for reason in result.reasons
    )
    score = int(result.score)
    if had_raw_density_reason:
        score = max(0, score - _legacy_density_penalty(float(result.notes_per_second)))

    rewritten: list[str] = []
    for reason in result.reasons:
        text = str(reason)
        if text.startswith(raw_density_prefixes):
            continue
        if text.startswith("short burst reaches ") and text.endswith(" notes/sec"):
            rewritten.append(text[: -len(" notes/sec")] + " attacks/sec")
        elif text.startswith("95th-percentile local density is ") and text.endswith(" notes/sec"):
            prefix = text[: -len(" notes/sec")]
            rewritten.append(prefix.replace("local density", "local attack density") + " attacks/sec")
        else:
            rewritten.append(text)

    code, label, summary = _adaptive_score_label(score)
    return replace(
        result,
        code=code,
        label=label,
        summary=summary,
        score=score,
        reasons=tuple(rewritten),
    )


def install_adaptive_pressure_model(app_module: Any) -> None:
    global _original_preanalyse, _original_to_adaptive_plan, _original_evaluate
    if getattr(app_module, "_adaptive_pressure_model_installed", False):
        return
    _original_preanalyse = adaptive._preanalyse
    _original_to_adaptive_plan = adaptive._to_adaptive_plan
    _original_evaluate = app_module.evaluate_song_suitability
    adaptive._preanalyse = _refined_preanalyse
    adaptive._auto_tune_options = _refined_auto_tune
    adaptive._adaptive_apply_note_lengths = _refined_apply_note_lengths
    adaptive._to_adaptive_plan = _refined_to_adaptive_plan
    me._limit_notes_per_chord = _refined_limit_notes_per_chord
    me._apply_note_lengths = _refined_apply_note_lengths

    adaptive.suitability_module.evaluate_song_suitability = _refined_evaluate_song_suitability
    app_module.evaluate_song_suitability = _refined_evaluate_song_suitability
    for name in ("online_ui", "online_integration", "online_search_bridge"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "evaluate_song_suitability"):
            module.evaluate_song_suitability = _refined_evaluate_song_suitability

    app_module._adaptive_pressure_model_installed = True
