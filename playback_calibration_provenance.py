from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import playback_adaptive as adaptive
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


def _read_json_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _write_json_object(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def load_measurement_flags(instrument: str) -> dict[str, bool]:
    flags = {field: False for field in MEASUREMENT_FIELDS}
    item = _read_json_object(provenance_path()).get(instrument)
    if isinstance(item, dict):
        for field in flags:
            flags[field] = bool(item.get(field, False))
    return flags


def set_measurement(instrument: str, field: str, verified: bool) -> None:
    if field not in MEASUREMENT_FIELDS:
        raise ValueError(f"Unknown calibration measurement field: {field}")
    path = provenance_path()
    payload = _read_json_object(path)
    current = payload.get(instrument)
    values = {name: False for name in MEASUREMENT_FIELDS}
    if isinstance(current, dict):
        for name in values:
            values[name] = bool(current.get(name, False))
    values[field] = bool(verified)
    payload[instrument] = values
    _write_json_object(path, payload)


def mark_measurement(instrument: str, field: str) -> None:
    set_measurement(instrument, field, True)


def reset_instrument_calibration(instrument: str) -> None:
    if instrument not in adaptive.ADAPTIVE_DEFAULTS:
        raise ValueError(f"Unknown calibration instrument: {instrument}")
    for path in (adaptive.calibration_path(), provenance_path()):
        payload = _read_json_object(path)
        if instrument in payload:
            payload.pop(instrument, None)
            _write_json_object(path, payload)


def measurement_state_label(instrument: str) -> str:
    flags = load_measurement_flags(instrument)
    measured = [field for field, value in flags.items() if value]
    if not measured:
        return "safe defaults active"
    if len(measured) == len(MEASUREMENT_FIELDS):
        return "fully verified"
    return "verified: " + ", ".join(measured)


def _effective_profile(
    instrument: str,
    saved: adaptive.CalibrationProfile,
    flags: dict[str, bool],
) -> adaptive.CalibrationProfile:
    """Return only values that have earned per-parameter verification."""
    defaults = adaptive._default_calibration(instrument)
    return replace(
        defaults,
        minimum_clean_hold_ms=(
            saved.minimum_clean_hold_ms if flags["hold"] else defaults.minimum_clean_hold_ms
        ),
        hard_floor_ms=saved.hard_floor_ms if flags["hold"] else defaults.hard_floor_ms,
        retrigger_gap_ms=(
            saved.retrigger_gap_ms if flags["repeat"] else defaults.retrigger_gap_ms
        ),
        chord_stagger_ms=(
            saved.chord_stagger_ms if flags["chord"] else defaults.chord_stagger_ms
        ),
        modifier_settle_ms=(
            saved.modifier_settle_ms if flags["modifier"] else defaults.modifier_settle_ms
        ),
        max_polyphony=saved.max_polyphony if flags["polyphony"] else defaults.max_polyphony,
        calibrated=any(flags.values()),
        updated_at=saved.updated_at,
    )


def _provenance_auto_tune(
    options: adaptive.AdaptivePlanOptions,
    analysis: adaptive.SourceAnalysis,
    profile: adaptive.CalibrationProfile,
) -> adaptive.AdaptivePlanOptions:
    assert _original_auto_tune is not None
    if not options.adaptive_auto or options.mapping_method == "skip":
        return options

    flags = load_measurement_flags(options.instrument)
    effective = _effective_profile(options.instrument, profile, flags)

    # Run the conservative auto-tuner with aggregate calibration disabled so
    # destructive settings cannot be authorized by an unrelated measurement.
    tuned = _original_auto_tune(options, analysis, replace(effective, calibrated=False))

    if flags["polyphony"]:
        limit = options.adaptive_chord_limit or effective.max_polyphony
        tuned = replace(tuned, adaptive_chord_limit=limit)
        if limit > 0 and tuned.max_notes_per_chord <= 0 and analysis.max_chord > limit:
            tuned = replace(tuned, max_notes_per_chord=limit)
    if flags["chord"] and options.chord_stagger_ms < 0:
        tuned = replace(tuned, chord_stagger_ms=effective.chord_stagger_ms)
    if flags["modifier"]:
        tuned = replace(
            tuned,
            octave_switch_lead_ms=max(tuned.octave_switch_lead_ms, effective.modifier_settle_ms),
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
        result.calibration_source = "fully verified"
    else:
        result.calibration_source = f"verified {measured}/{len(MEASUREMENT_FIELDS)}"
    return result


def _guided_search_converged(app: Any, instrument: str, test_code: str) -> bool:
    state = getattr(app, "_calibration_guide_bounds", None)
    if not isinstance(state, dict):
        return True
    bounds = state.get((instrument, test_code))
    if not isinstance(bounds, tuple) or len(bounds) != 2:
        return False
    low, high = int(bounds[0]), int(bounds[1])
    tolerances = {"hold": 4, "repeat": 2, "chord": 1, "modifier": 4}
    return high - low <= tolerances.get(test_code, 0)


def _record_feedback_with_provenance(app: Any, feedback: str) -> None:
    assert _original_record_feedback is not None
    instrument = app._instrument_code()
    test_code = calibration.TEST_LABELS.get(app._calibration_test_var.get(), "hold")
    _original_record_feedback(app, feedback)

    # Negative samples guide the search but revoke permission for Auto to use
    # the exploratory value. Clean becomes active only near convergence.
    verified = feedback == "clean" and _guided_search_converged(app, instrument, test_code)
    set_measurement(instrument, test_code, verified)
    if hasattr(app, "_calibration_summary_var"):
        app._calibration_summary_var.set(
            calibration._profile_summary(adaptive.get_calibration_profile(instrument))
        )


def _save_polyphony_with_provenance(app: Any) -> None:
    assert _original_save_polyphony is not None
    instrument = app._instrument_code()
    _original_save_polyphony(app)
    mark_measurement(instrument, "polyphony")
    if hasattr(app, "_calibration_summary_var"):
        app._calibration_summary_var.set(
            calibration._profile_summary(adaptive.get_calibration_profile(instrument))
        )


def _profile_summary_with_provenance(profile: adaptive.CalibrationProfile) -> str:
    state = measurement_state_label(profile.instrument)
    return (
        f"{profile.instrument.title()} ({state}) • working hold {profile.minimum_clean_hold_ms} ms • "
        f"hard floor {profile.hard_floor_ms} ms • repeat gap {profile.retrigger_gap_ms} ms • "
        f"chord stagger {profile.chord_stagger_ms} ms • modifier settle {profile.modifier_settle_ms} ms • "
        f"polyphony {profile.max_polyphony}. Unverified working values are not used by Auto."
    )


def _reset_from_ui(app: Any, app_module: Any) -> None:
    instrument = app._instrument_code()
    if not app_module.messagebox.askyesno(
        "Reset BPSR calibration",
        f"Reset {instrument.title()} calibration to conservative defaults?",
        parent=app,
    ):
        return
    reset_instrument_calibration(instrument)
    bounds = getattr(app, "_calibration_guide_bounds", None)
    if isinstance(bounds, dict):
        for key in tuple(bounds):
            if isinstance(key, tuple) and key and key[0] == instrument:
                bounds.pop(key, None)
    calibration._sync_from_profile(app)
    if hasattr(app, "_calibration_guide_var"):
        try:
            import playback_calibration_guidance as guidance
            guidance._refresh_guide(app)
        except Exception:
            pass
    app.status_var.set(f"{instrument.title()} calibration reset. Auto is using safe defaults again.")
    app._schedule_analysis()


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

    app_class = app_module.App
    original_build_ui = app_class._build_ui

    def build_ui(self: Any) -> None:
        original_build_ui(self)
        panel = getattr(self, "_calibration_panel", None)
        if panel is None or hasattr(self, "_calibration_reset_button"):
            return
        self._calibration_reset_button = app_module.ttk.Button(
            panel,
            text="Reset this instrument",
            command=lambda: _reset_from_ui(self, app_module),
        )
        self._calibration_reset_button.grid(row=1, column=7, padx=(8, 0), pady=(8, 0))

    app_class._build_ui = build_ui
    app_module._calibration_provenance_installed = True
