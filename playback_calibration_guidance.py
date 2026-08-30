from __future__ import annotations

from typing import Any

import playback_calibration_ui as calibration

_original_record_feedback: Any = None
_original_test_changed: Any = None

_RANGES: dict[str, tuple[int, int, int]] = {
    "hold": (20, 220, 4),
    "repeat": (4, 80, 2),
    "chord": (0, 10, 1),
    "modifier": (10, 180, 4),
}


def _guide_state(app: Any) -> dict[tuple[str, str], tuple[int, int]]:
    state = getattr(app, "_calibration_guide_bounds", None)
    if state is None:
        state = {}
        app._calibration_guide_bounds = state
    return state


def _current_test(app: Any) -> str:
    return calibration.TEST_LABELS.get(app._calibration_test_var.get(), "hold")


def _bounds(app: Any, instrument: str, test_code: str) -> tuple[int, int]:
    state = _guide_state(app)
    key = (instrument, test_code)
    if key not in state:
        low, high, _ = _RANGES[test_code]
        state[key] = (low, high)
    return state[key]


def _set_bounds(app: Any, instrument: str, test_code: str, low: int, high: int) -> None:
    _guide_state(app)[(instrument, test_code)] = (max(0, low), max(0, high))


def _guide_description(test_code: str) -> str:
    return {
        "hold": "Goal: find the shortest note hold that still sounds clean and complete.",
        "repeat": "Goal: find the smallest release gap that still retriggers every repeated note.",
        "chord": "Goal: find the smallest chord-key stagger that avoids dropped attacks without sounding rolled.",
        "modifier": "Goal: find the shortest Ctrl/Shift settle delay that changes octave reliably before the note.",
    }[test_code]


def _refresh_guide(app: Any) -> None:
    if not hasattr(app, "_calibration_guide_var"):
        return
    instrument = app._instrument_code()
    test_code = _current_test(app)
    low, high = _bounds(app, instrument, test_code)
    app._calibration_guide_var.set(
        f"Guided search • {_guide_description(test_code)} Current search range: {low}–{high} ms. "
        "Play the suggested value, then rate what you heard."
    )


def _guided_test_changed(app: Any) -> None:
    assert _original_test_changed is not None
    _original_test_changed(app)
    instrument = app._instrument_code()
    test_code = _current_test(app)
    low, high = _bounds(app, instrument, test_code)
    default = int(app._calibration_value_var.get())
    if not low <= default <= high:
        app._calibration_value_var.set((low + high) // 2)
    calibration._set_feedback_ready(app, False)
    _refresh_guide(app)


def _guided_record_feedback(app: Any, feedback: str) -> None:
    assert _original_record_feedback is not None
    # Check the completed-sample token before mutating the guided bounds. This
    # prevents button clicks (or a changed value/test) from converging a search
    # that was never actually played in BPSR.
    if not calibration._feedback_sample_matches(app):
        calibration._set_feedback_ready(app, False)
        app.status_var.set(
            "Play and finish this exact calibration value before recording feedback."
        )
        return

    instrument = app._instrument_code()
    test_code = _current_test(app)
    value = max(0, int(app._calibration_value_var.get()))
    low, high = _bounds(app, instrument, test_code)

    # All four tests are searches for the smallest reliable value. "Clean"
    # proves the threshold is at or below the current value. "Missed" proves it
    # is above. "Too muddy" means the current value is needlessly long/rolled,
    # so search downward just like an overly conservative clean result.
    if feedback == "missed":
        low = max(low, value + 1)
    else:
        high = min(high, max(0, value - (1 if feedback == "muddy" else 0)))
    if high < low:
        high = low
    _set_bounds(app, instrument, test_code, low, high)

    _original_record_feedback(app, feedback)

    _, _, tolerance = _RANGES[test_code]
    span = high - low
    if span <= tolerance:
        suggested = high
        app._calibration_value_var.set(suggested)
        calibration._set_feedback_ready(app, False)
        app._calibration_guide_var.set(
            f"Guided search converged near {suggested} ms for {instrument.title()} / {test_code}. "
            "Run one final sample at this value and mark Clean before treating it as confirmed."
        )
    else:
        suggested = (low + high) // 2
        app._calibration_value_var.set(suggested)
        calibration._set_feedback_ready(app, False)
        app._calibration_guide_var.set(
            f"Next suggested test: {suggested} ms. Remaining plausible threshold: {low}–{high} ms. "
            "Press Play test, listen in BPSR, then rate it again."
        )


def install_guided_calibration(app_module: Any) -> None:
    global _original_record_feedback, _original_test_changed
    if getattr(app_module, "_guided_calibration_installed", False):
        return
    _original_record_feedback = calibration._record_feedback
    _original_test_changed = calibration._test_changed
    calibration._record_feedback = _guided_record_feedback
    calibration._test_changed = _guided_test_changed

    app_class = app_module.App
    original_build_ui = app_class._build_ui
    original_instrument_changed = app_class._instrument_changed

    def build_ui(self: Any) -> None:
        original_build_ui(self)
        panel = getattr(self, "_calibration_panel", None)
        if panel is None:
            return
        self._calibration_guide_var = app_module.tk.StringVar(master=self)
        app_module.ttk.Label(
            panel,
            textvariable=self._calibration_guide_var,
            style="Hint.TLabel",
            wraplength=1050,
            justify="left",
        ).grid(row=6, column=0, columnspan=7, sticky="w", pady=(7, 0))
        _refresh_guide(self)

    def instrument_changed(self: Any) -> None:
        original_instrument_changed(self)
        calibration._set_feedback_ready(self, False)
        _refresh_guide(self)

    app_class._build_ui = build_ui
    app_class._instrument_changed = instrument_changed
    app_module._guided_calibration_installed = True
