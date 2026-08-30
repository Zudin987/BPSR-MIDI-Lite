from __future__ import annotations

from dataclasses import replace
from typing import Any

import midi_engine as me
import playback_overhaul as po
from playback_adaptive import (
    CalibrationProfile,
    get_calibration_profile,
    save_calibration_profile,
)


TEST_LABELS = {
    "Minimum clean hold": "hold",
    "Repeated-note release gap": "repeat",
    "Chord delivery stagger": "chord",
    "Ctrl/Shift settle delay": "modifier",
}


def _test_default_value(profile: CalibrationProfile, test_code: str) -> int:
    if test_code == "hold":
        return profile.minimum_clean_hold_ms
    if test_code == "repeat":
        return profile.retrigger_gap_ms
    if test_code == "chord":
        return profile.chord_stagger_ms
    return profile.modifier_settle_ms


def _calibration_keys(instrument: str) -> tuple[str, tuple[str, ...]]:
    if instrument == "bass":
        return "q", ("q", "i", "w", "o")
    return "a", ("a", "s", "d", "f")


def _base_plan(
    instrument: str,
    events: list[me.PlannedEvent],
    duration: float,
    note_count: int,
    max_chord: int = 1,
) -> po.EnhancedMidiPlan:
    events.sort(key=lambda event: (event.time, event.priority, event.serial))
    return po.EnhancedMidiPlan(
        events=events,
        instrument=instrument,
        duration=duration,
        mode="stable",
        note_count=note_count,
        source_min_pitch=None,
        source_max_pitch=None,
        planned_min_pitch=None,
        planned_max_pitch=None,
        page_switches=0,
        octave_switches=sum(event.kind == "state" for event in events),
        folded_notes=0,
        remapped_notes=0,
        skipped_notes=0,
        merged_notes=0,
        retrigger_merged_notes=0,
        retrigger_dropped_notes=0,
        filtered_notes=0,
        transposed_semitones=0,
        added_delay=0.0,
        page_switch_delay=0.220,
        unlock_tier=None,
        configured_min_pitch=me.GAME_MIN_PITCH,
        configured_max_pitch=me.STABLE_MAX_PITCH,
        effective_min_pitch=me.GAME_MIN_PITCH,
        effective_max_pitch=me.STABLE_MAX_PITCH,
        source_note_count=note_count,
        source_duration=duration,
        source_track_count=1,
        source_percussion_notes=0,
        max_source_chord=max_chord,
        max_planned_chord=max_chord,
        max_simultaneous_keys=max_chord,
        chord_removed_notes=0,
        articulation_mode="raw",
        sustain_mode="off",
        timing_profile=instrument,
    )


def build_calibration_test_plan(instrument: str, test_code: str, value_ms: int) -> po.EnhancedMidiPlan:
    if instrument not in po.TIMING_PROFILES:
        raise ValueError("Calibration instrument must be keyboard, guitar, or bass.")
    value_ms = max(0, int(value_ms))
    key, chord_keys = _calibration_keys(instrument)
    events: list[me.PlannedEvent] = []
    serial = 0
    cursor = 0.50

    if test_code == "hold":
        hold = max(0.010, value_ms / 1000.0)
        for _ in range(4):
            events.append(me.PlannedEvent(cursor, 20, "note_on", key=key, serial=serial))
            events.append(me.PlannedEvent(cursor + hold, 0, "note_off", key=key, serial=serial))
            cursor += 0.50
            serial += 1
        return _base_plan(instrument, events, cursor + 0.25, serial)

    if test_code == "repeat":
        gap = max(0.001, value_ms / 1000.0)
        hold = 0.080
        for _ in range(6):
            events.append(me.PlannedEvent(cursor, 20, "note_on", key=key, serial=serial))
            events.append(me.PlannedEvent(cursor + hold, 0, "note_off", key=key, serial=serial))
            cursor += hold + gap
            serial += 1
        return _base_plan(instrument, events, cursor + 0.30, serial)

    if test_code == "chord":
        stagger = value_ms / 1000.0
        for index, chord_key in enumerate(chord_keys):
            start = cursor + index * stagger
            events.append(me.PlannedEvent(start, 20, "note_on", key=chord_key, serial=serial))
            events.append(me.PlannedEvent(start + 0.160, 0, "note_off", key=chord_key, serial=serial))
            serial += 1
        return _base_plan(instrument, events, cursor + 0.65, serial, max_chord=len(chord_keys))

    if test_code == "modifier":
        settle = value_ms / 1000.0
        events.append(me.PlannedEvent(cursor, -20, "state", state=1, serial=serial))
        attack = cursor + settle
        events.append(me.PlannedEvent(attack, 20, "note_on", key=key, serial=serial + 1))
        events.append(me.PlannedEvent(attack + 0.140, 0, "note_off", key=key, serial=serial + 1))
        events.append(me.PlannedEvent(attack + 0.35, -20, "state", state=0, serial=serial + 2))
        return _base_plan(instrument, events, attack + 0.70, 1)

    raise ValueError(f"Unknown calibration test: {test_code}")


def _profile_summary(profile: CalibrationProfile) -> str:
    source = "measured" if profile.calibrated else "safe defaults"
    return (
        f"{profile.instrument.title()} ({source}) • clean hold {profile.minimum_clean_hold_ms} ms • "
        f"hard floor {profile.hard_floor_ms} ms • repeat gap {profile.retrigger_gap_ms} ms • "
        f"chord stagger {profile.chord_stagger_ms} ms • modifier settle {profile.modifier_settle_ms} ms • "
        f"working polyphony {profile.max_polyphony}"
    )


def _show_panel(app: Any, visible: bool) -> None:
    panel = getattr(app, "_calibration_panel", None)
    if panel is None:
        return
    if visible:
        panel.grid()
    else:
        panel.grid_remove()
    app._calibration_visible = visible


def _feedback_signature(app: Any) -> tuple[str, str, int]:
    return (
        app._instrument_code(),
        TEST_LABELS.get(app._calibration_test_var.get(), "hold"),
        max(0, int(app._calibration_value_var.get())),
    )


def _feedback_sample_matches(app: Any) -> bool:
    return getattr(app, "_calibration_completed_sample", None) == _feedback_signature(app)


def _set_feedback_ready(app: Any, ready: bool) -> None:
    buttons = getattr(app, "_calibration_feedback_buttons", ())
    state = "normal" if ready else "disabled"
    for button in buttons:
        try:
            button.configure(state=state)
        except Exception:
            pass
    if not ready:
        app._calibration_completed_sample = None


def _sync_from_profile(app: Any) -> None:
    instrument = app._instrument_code()
    profile = get_calibration_profile(instrument)
    app._calibration_instrument_var.set(instrument.title())
    app._calibration_polyphony_var.set(profile.max_polyphony)
    test_code = TEST_LABELS.get(app._calibration_test_var.get(), "hold")
    app._calibration_value_var.set(_test_default_value(profile, test_code))
    app._calibration_summary_var.set(_profile_summary(profile))
    _set_feedback_ready(app, False)


def _test_changed(app: Any) -> None:
    profile = get_calibration_profile(app._instrument_code())
    test_code = TEST_LABELS.get(app._calibration_test_var.get(), "hold")
    app._calibration_value_var.set(_test_default_value(profile, test_code))
    _set_feedback_ready(app, False)


def _play_test(app: Any) -> None:
    if app.player.is_playing:
        app.status_var.set("Stop the current playback before running calibration.")
        return
    instrument = app._instrument_code()
    test_code = TEST_LABELS.get(app._calibration_test_var.get(), "hold")
    value = max(0, int(app._calibration_value_var.get()))
    sample_signature = (instrument, test_code, value)
    plan = build_calibration_test_plan(instrument, test_code, value)
    _set_feedback_ready(app, False)
    app._calibration_play_button.configure(state="disabled")
    app.status_var.set(
        f"Calibration {test_code}: {value} ms. Switch to BPSR during the 2-second countdown."
    )

    def status(text: str, progress: float) -> None:
        app.ui_queue.put(("status", (f"Calibration • {text}", progress)))

    def finished(error: str | None) -> None:
        def restore() -> None:
            app._calibration_play_button.configure(state="normal")
            if error:
                _set_feedback_ready(app, False)
                app.status_var.set(f"Calibration playback error: {error}")
            elif app.player.stop_event.is_set():
                _set_feedback_ready(app, False)
                app.status_var.set("Calibration stopped. No result was recorded.")
            else:
                app._calibration_completed_sample = sample_signature
                _set_feedback_ready(app, True)
                app.status_var.set(
                    "Calibration sample finished. Rate this exact sample once: Clean, Missed / too short, or Too muddy."
                )
        app.after(0, restore)

    app.player.start(
        plan,
        2.0,
        status,
        finished,
        input_backend=app._input_backend_code(),
    )


def _record_feedback(app: Any, feedback: str) -> None:
    if not _feedback_sample_matches(app):
        _set_feedback_ready(app, False)
        app.status_var.set(
            "Play and finish this exact calibration value before recording feedback."
        )
        return

    instrument = app._instrument_code()
    profile = get_calibration_profile(instrument)
    test_code = TEST_LABELS.get(app._calibration_test_var.get(), "hold")
    value = max(0, int(app._calibration_value_var.get()))
    polyphony = max(1, min(12, int(app._calibration_polyphony_var.get())))
    # Consume the sample before writing anything so one playback can only earn
    # one calibration judgment/provenance update.
    _set_feedback_ready(app, False)

    if test_code == "hold":
        if feedback == "clean":
            profile = replace(
                profile,
                minimum_clean_hold_ms=max(profile.hard_floor_ms, value),
                hard_floor_ms=min(profile.hard_floor_ms, max(15, value)),
            )
        elif feedback == "missed":
            profile = replace(
                profile,
                hard_floor_ms=max(profile.hard_floor_ms, value + 5),
                minimum_clean_hold_ms=max(profile.minimum_clean_hold_ms, value + 10),
            )
        else:
            profile = replace(
                profile,
                minimum_clean_hold_ms=max(profile.hard_floor_ms, value - 10),
            )
    elif test_code == "repeat":
        if feedback == "clean":
            profile = replace(profile, retrigger_gap_ms=max(1, value))
        elif feedback == "missed":
            profile = replace(profile, retrigger_gap_ms=max(profile.retrigger_gap_ms, value + 4))
        else:
            profile = replace(profile, retrigger_gap_ms=max(1, value - 2))
    elif test_code == "chord":
        if feedback == "clean":
            profile = replace(profile, chord_stagger_ms=min(12, value), max_polyphony=polyphony)
        elif feedback == "missed":
            profile = replace(profile, chord_stagger_ms=min(12, value + 1), max_polyphony=polyphony)
        else:
            profile = replace(profile, chord_stagger_ms=max(0, value - 1), max_polyphony=polyphony)
    else:
        if feedback == "clean":
            profile = replace(profile, modifier_settle_ms=max(10, value))
        elif feedback == "missed":
            profile = replace(profile, modifier_settle_ms=max(profile.modifier_settle_ms, value + 5))
        else:
            profile = replace(profile, modifier_settle_ms=max(10, value - 5))

    save_calibration_profile(replace(profile, max_polyphony=polyphony))
    updated = get_calibration_profile(instrument)
    app._calibration_summary_var.set(_profile_summary(updated))
    app.status_var.set(
        f"Saved {instrument.title()} calibration feedback. New adaptive plans will use verified timing values automatically."
    )
    app._schedule_analysis()


def _save_polyphony(app: Any) -> None:
    instrument = app._instrument_code()
    profile = get_calibration_profile(instrument)
    polyphony = max(1, min(12, int(app._calibration_polyphony_var.get())))
    save_calibration_profile(replace(profile, max_polyphony=polyphony))
    _sync_from_profile(app)
    app.status_var.set(
        f"Saved {instrument.title()} working polyphony {polyphony}. It is not Auto-verified without an in-game N-key test."
    )
    app._schedule_analysis()


def _build_calibration_panel(app: Any, app_module: Any) -> None:
    if hasattr(app, "_calibration_panel"):
        return
    body = getattr(app, "_gaming_body", None)
    settings_panel = getattr(app, "_gaming_settings_panel", None)
    if body is None or settings_panel is None:
        return

    button = app_module.ttk.Button(
        settings_panel,
        text="BPSR Calibration Lab",
        command=lambda: _show_panel(app, not bool(getattr(app, "_calibration_visible", False))),
    )
    button.grid(row=14, column=0, sticky="ew", pady=(12, 0))
    app._calibration_toggle_button = button

    body.rowconfigure(2, weight=0)
    panel = app_module.ttk.LabelFrame(
        body,
        text="BPSR Calibration Lab — measure this PC + game setup",
        padding=10,
    )
    panel.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
    panel.columnconfigure(3, weight=1)
    app._calibration_panel = panel
    app._calibration_visible = False
    app._calibration_completed_sample = None

    app._calibration_instrument_var = app_module.tk.StringVar(master=app)
    app._calibration_test_var = app_module.tk.StringVar(master=app, value=next(iter(TEST_LABELS)))
    app._calibration_value_var = app_module.tk.IntVar(master=app, value=90)
    app._calibration_polyphony_var = app_module.tk.IntVar(master=app, value=4)
    app._calibration_summary_var = app_module.tk.StringVar(master=app)

    app_module.ttk.Label(panel, text="Instrument").grid(row=0, column=0, sticky="w")
    app_module.ttk.Label(panel, textvariable=app._calibration_instrument_var).grid(
        row=0, column=1, sticky="w", padx=(6, 16)
    )
    app_module.ttk.Label(panel, text="Test").grid(row=0, column=2, sticky="w")
    combo = app_module.ttk.Combobox(
        panel,
        textvariable=app._calibration_test_var,
        values=list(TEST_LABELS),
        state="readonly",
        width=28,
    )
    combo.grid(row=0, column=3, sticky="w", padx=(6, 12))
    combo.bind("<<ComboboxSelected>>", lambda _event: _test_changed(app))

    app_module.ttk.Label(panel, text="Value").grid(row=0, column=4, sticky="w")
    app_module.ttk.Spinbox(
        panel,
        from_=0,
        to=500,
        increment=1,
        textvariable=app._calibration_value_var,
        width=7,
    ).grid(row=0, column=5, sticky="w", padx=(6, 4))
    app_module.ttk.Label(panel, text="ms").grid(row=0, column=6, sticky="w")

    app_module.ttk.Label(panel, text="Working chord keys (not verified)").grid(
        row=1, column=0, sticky="w", pady=(8, 0)
    )
    app_module.ttk.Spinbox(
        panel,
        from_=1,
        to=12,
        increment=1,
        textvariable=app._calibration_polyphony_var,
        width=5,
    ).grid(row=1, column=1, sticky="w", padx=(6, 16), pady=(8, 0))
    app_module.ttk.Button(panel, text="Save working value", command=lambda: _save_polyphony(app)).grid(
        row=1, column=2, sticky="w", pady=(8, 0)
    )

    app._calibration_play_button = app_module.ttk.Button(
        panel,
        text="Play test",
        command=lambda: _play_test(app),
    )
    app._calibration_play_button.grid(row=1, column=3, sticky="w", padx=(8, 0), pady=(8, 0))
    feedback_buttons = [
        app_module.ttk.Button(panel, text="Clean", command=lambda: _record_feedback(app, "clean")),
        app_module.ttk.Button(
            panel,
            text="Missed / too short",
            command=lambda: _record_feedback(app, "missed"),
        ),
        app_module.ttk.Button(panel, text="Too muddy", command=lambda: _record_feedback(app, "muddy")),
    ]
    feedback_buttons[0].grid(row=1, column=4, padx=(8, 0), pady=(8, 0))
    feedback_buttons[1].grid(row=1, column=5, padx=(8, 0), pady=(8, 0))
    feedback_buttons[2].grid(row=1, column=6, padx=(8, 0), pady=(8, 0))
    app._calibration_feedback_buttons = tuple(feedback_buttons)
    _set_feedback_ready(app, False)

    app_module.ttk.Label(
        panel,
        textvariable=app._calibration_summary_var,
        style="Hint.TLabel",
        wraplength=1050,
        justify="left",
    ).grid(row=2, column=0, columnspan=7, sticky="w", pady=(10, 0))
    app_module.ttk.Label(
        panel,
        text=(
            "Run one test at a time in the real BPSR instrument. A rating is accepted only after that exact "
            "sample finishes. Timing results are stored locally. Working polyphony is not trusted by Auto "
            "until a dedicated N-key verification test exists."
        ),
        style="Hint.TLabel",
        wraplength=1050,
        justify="left",
    ).grid(row=3, column=0, columnspan=7, sticky="w", pady=(5, 0))

    _sync_from_profile(app)
    _show_panel(app, False)


def install_calibration_lab(app_module: Any) -> None:
    if getattr(app_module, "_calibration_lab_installed", False):
        return
    app_class = app_module.App
    original_build_ui = app_class._build_ui
    original_instrument_changed = app_class._instrument_changed

    def build_ui(self: Any) -> None:
        original_build_ui(self)
        _build_calibration_panel(self, app_module)

    def instrument_changed(self: Any) -> None:
        original_instrument_changed(self)
        if hasattr(self, "_calibration_summary_var"):
            _sync_from_profile(self)

    app_class._build_ui = build_ui
    app_class._instrument_changed = instrument_changed
    app_module._calibration_lab_installed = True
