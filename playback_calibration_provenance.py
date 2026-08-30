from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import playback_adaptive as adaptive
import playback_adaptive_pressure as pressure
import playback_calibration_ui as calibration

MEASUREMENT_FIELDS = ("hold", "repeat", "chord", "modifier", "polyphony")

_original_auto_tune: Any = None
_original_to_adaptive_plan: Any = None
_original_record_feedback: Any = None
_original_save_polyphony: Any = None
_original_profile_summary: Any = None


def provenance_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home())) / "BPSR MIDI Lite"
    else:
        base = Path.home() / ".config" / "bpsr-midi-lite"
    base.mkdir(parents=True, exist_ok=True)
    return base / "bpsr_calibration_provenance.json"


def load_measurement_flags(instrument: str) -> dict[str, bool]:
    flags = {field: False for field in MEASUREMENT_FIELDS}
    path = provenance_path()
    if not path.exists():
        return flags
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        item = raw.get(instrument) if isinstance(raw, dict) else None
        if isinstance(item, dict):
            for field in flags:
                flags[field] = bool(item.get(field, False))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return flags


def mark_measurement(instrument: str, field: str) -> None:
    if field not in MEASUREMENT_FIELDS:
        raise ValueError(f"Unknown calibration measurement field: {field}")
    path = provenance_path()
    payload: dict[str, object] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                payload = raw
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            payload = {}
    current = payload.get(instrument)
    values = {name: False for name in MEASUREMENT_FIELDS}
    if isinstance(current, dict):
        for name in values:
            values[name] = bool(current.get(name, False))
    values[field] = True
    payload[instrument] = values
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def measurement_state_label(instrument: str) -> str:
    flags = load_measurement_flags(instrument)
    measured = [field for field, value in flags.items() if value]
    if not measured:
        return "safe defaults"
    if len(measured) == len(MEASUREMENT_FIELDS):
        return "fully measured"
    return "measured: " + ", ".join(measured)


def _provenance_auto_tune(
    options: adaptive.AdaptivePlanOptions,
    analysis: adaptive.SourceAnalysis,
    profile: adaptive.CalibrationProfile,
) -> adaptive.AdaptivePlanOptions:
    assert _original_auto_tune is not None
    if not options.adaptive_auto or options.mapping_method == "skip":
        return options

    # Always start from the conservative path. The old aggregate `calibrated`
    # flag only means at least one value was saved; it must never authorize an
    # unrelated destructive setting such as chord thinning.
    tuned = _original_auto_tune(options, analysis, replace(profile, calibrated=False))
    flags = load_measurement_flags(options.instrument)

    if flags["polyphony"]:
        limit = options.adaptive_chord_limit or profile.max_polyphony
        tuned = replace(tuned, adaptive_chord_limit=limit)
        if limit > 0 and tuned.max_notes_per_chord <= 0 and analysis.max_chord > limit:
            tuned = replace(tuned, max_notes_per_chord=limit)
    if flags["chord"] and options.chord_stagger_ms < 0:
        tuned = replace(tuned, chord_stagger_ms=profile.chord_stagger_ms)
    if flags["modifier"]:
        tuned = replace(
            tuned,
            octave_switch_lead_ms=max(tuned.octave_switch_lead_ms, profile.modifier_settle_ms),
        )
    return tuned


def _provenance_to_adaptive_plan(*args: Any, **kwargs: Any):
    assert _original_to_adaptive_plan is not None
    result = _original_to_adaptive_plan(*args, **kwargs)
    instrument = str(getattr(result, "instrument", "keyboard"))
    flags = load_measurement_flags(instrument)
    measured = sum(bool(value) for value in flags.values())
    if measured == 0:
        result.calibration_source = "defaults"
    elif measured == len(MEASUREMENT_FIELDS):
        result.calibration_source = "fully measured"
    else:
        result.calibration_source = f"partial {measured}/{len(MEASUREMENT_FIELDS)}"
    return result


def _record_feedback_with_provenance(app: Any, feedback: str) -> None:
    assert _original_record_feedback is not None
    instrument = app._instrument_code()
    test_code = calibration.TEST_LABELS.get(app._calibration_test_var.get(), "hold")
    _original_record_feedback(app, feedback)
    mark_measurement(instrument, test_code)
    if hasattr(app, "_calibration_summary_var"):
        app._calibration_summary_var.set(calibration._profile_summary(adaptive.get_calibration_profile(instrument)))


def _save_polyphony_with_provenance(app: Any) -> None:
    assert _original_save_polyphony is not None
    instrument = app._instrument_code()
    _original_save_polyphony(app)
    mark_measurement(instrument, "polyphony")
    if hasattr(app, "_calibration_summary_var"):
        app._calibration_summary_var.set(calibration._profile_summary(adaptive.get_calibration_profile(instrument)))


def _profile_summary_with_provenance(profile: adaptive.CalibrationProfile) -> str:
    state = measurement_state_label(profile.instrument)
    return (
        f"{profile.instrument.title()} ({state}) • clean hold {profile.minimum_clean_hold_ms} ms • "
        f"hard floor {profile.hard_floor_ms} ms • repeat gap {profile.retrigger_gap_ms} ms • "
        f"chord stagger {profile.chord_stagger_ms} ms • modifier settle {profile.modifier_settle_ms} ms • "
        f"reliable polyphony {profile.max_polyphony}"
    )


def install_calibration_provenance(app_module: Any) -> None:
    global _original_auto_tune, _original_to_adaptive_plan
    global _original_record_feedback, _original_save_polyphony, _original_profile_summary
    if getattr(app_module, "_calibration_provenance_installed", False):
        return

    _original_auto_tune = adaptive._auto_tune_options
    _original_to_adaptive_plan = adaptive._to_adaptive_plan
    _original_record_feedback = calibration._record_feedback
    _original_save_polyphony = calibration._save_polyphony
    _original_profile_summary = calibration._profile_summary

    adaptive._auto_tune_options = _provenance_auto_tune
    adaptive._to_adaptive_plan = _provenance_to_adaptive_plan
    calibration._record_feedback = _record_feedback_with_provenance
    calibration._save_polyphony = _save_polyphony_with_provenance
    calibration._profile_summary = _profile_summary_with_provenance
    app_module._calibration_provenance_installed = True
