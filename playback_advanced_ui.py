from __future__ import annotations

from typing import Any


CUSTOM_PROFILE_LABEL = "Custom — Advanced timing & mapping"
_TIMING_MARKER = "\nBPSR timing • "


def _show_custom_panel(app: Any, visible: bool) -> None:
    panel = getattr(app, "custom_settings_frame", None)
    if panel is None:
        return
    layout = getattr(app, "_advanced_panel_layout", "grid")
    if visible:
        if layout == "grid":
            panel.grid()
        else:
            panel.pack(fill="x", padx=20, pady=(0, 12))
    elif layout == "grid":
        panel.grid_remove()
    else:
        panel.pack_forget()


def _timing_profile(instrument: str) -> Any | None:
    try:
        from playback_overhaul import TIMING_PROFILES

        return TIMING_PROFILES.get(instrument)
    except Exception:
        return None


def _prepare_custom_panel(app: Any, app_module: Any) -> None:
    if hasattr(app, "custom_settings_frame"):
        return

    body = getattr(app, "_gaming_body", None)
    if body is not None:
        body.rowconfigure(1, weight=0)
        panel = app_module.ttk.LabelFrame(
            body,
            text="Advanced BPSR tuning — Custom profile",
            padding=10,
        )
        panel.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        app._advanced_panel_layout = "grid"
    else:
        panel = app_module.ttk.LabelFrame(
            app,
            text="Advanced BPSR tuning — Custom profile",
            padding=10,
        )
        panel.pack(fill="x", padx=20, pady=(0, 12))
        app._advanced_panel_layout = "pack"

    panel.columnconfigure(1, weight=1)
    panel.columnconfigure(3, weight=1)
    app.custom_settings_frame = panel
    app._build_custom_settings(panel)

    # The product intentionally stays on the safe middle/no-page layout. Keep
    # the legacy page-delay widgets available to controller code, but hide them
    # from the Custom UI because no user-facing mode can use them.
    for child in panel.winfo_children():
        try:
            info = child.grid_info()
            row = int(info.get("row", -1))
            column = int(info.get("column", -1))
            text = str(child.cget("text")) if "text" in child.keys() else ""
            variable = str(child.cget("textvariable")) if "textvariable" in child.keys() else ""

            if text == "Playback style":
                child.configure(text="Playback safety")
            if row == 1 and column >= 2:
                child.grid_remove()
            if variable == str(app.minimum_note_var):
                try:
                    child.configure(from_=0)
                except Exception:
                    pass
                app._advanced_minimum_note_spin = child
            elif variable == str(getattr(app, "release_gap_var", "")):
                app._advanced_release_gap_spin = child
            elif variable == str(getattr(app, "articulation_var", "")):
                app._advanced_articulation_combo = child
            elif variable == str(getattr(app, "sustain_mode_var", "")):
                app._advanced_sustain_combo = child
        except Exception:
            continue

    app._advanced_hint_var = app_module.tk.StringVar(master=app)
    app_module.ttk.Label(
        panel,
        textvariable=app._advanced_hint_var,
        style="Hint.TLabel",
        wraplength=1040,
        justify="left",
    ).grid(row=8, column=0, columnspan=4, sticky="w", pady=(10, 0))

    try:
        app.mode_combo.configure(state="disabled")
    except Exception:
        pass
    _show_custom_panel(app, False)


def _sync_custom_controls(app: Any) -> None:
    if not hasattr(app, "_advanced_hint_var"):
        return

    try:
        app.mode_combo.configure(state="disabled")
    except Exception:
        pass

    sustain_enabled = bool(getattr(app, "pedal_var", None) and app.pedal_var.get())
    sustain_combo = getattr(app, "_advanced_sustain_combo", None)
    if sustain_combo is not None:
        try:
            sustain_combo.configure(state="readonly" if sustain_enabled else "disabled")
        except Exception:
            pass

    instrument = app._instrument_code()
    timing = _timing_profile(instrument)
    articulation = str(getattr(app, "articulation_var", None).get()) if hasattr(app, "articulation_var") else "Balanced"
    sustain = str(getattr(app, "sustain_mode_var", None).get()) if hasattr(app, "sustain_mode_var") else "Native BPSR pedal"

    articulation_help = {
        "Musical": "Musical keeps fuller note tails.",
        "Balanced": "Balanced is recommended for most songs.",
        "Dense / Fast": "Dense / Fast shortens pressure in rapid passages.",
        "Raw MIDI": "Raw MIDI follows authored lengths as closely as BPSR input allows.",
    }.get(articulation, "Balanced is recommended for most songs.")

    if sustain_enabled:
        sustain_help = (
            "Native BPSR pedal uses Space taps."
            if sustain == "Native BPSR pedal"
            else "Simulated sustain extends note holds without Space taps."
            if sustain == "Simulated note hold"
            else "Sustain events are ignored."
        )
    else:
        sustain_help = "MIDI sustain is disabled; Sustain behavior is inactive."

    auto_help = ""
    if timing is not None:
        auto_help = (
            f" Auto {instrument.title()} timing: minimum {timing.musical_min_ms} ms, "
            f"retrigger gap {timing.retrigger_gap_ms} ms. Set Minimum note or Retrigger gap to 0 to use Auto."
        )
    app._advanced_hint_var.set(f"{articulation_help} {sustain_help}{auto_help}")


def _custom_profile_summary(app: Any) -> tuple[str, str]:
    instrument = app._instrument_code()
    articulation = str(app.articulation_var.get()) if hasattr(app, "articulation_var") else "Balanced"
    summary = (
        f"Custom {instrument.title()} tuning • Stable / no-page playback • {articulation} articulation. "
        "Use the advanced panel below to tune mapping, chord detail, note timing and sustain."
    )
    if instrument == "bass":
        notice = (
            "Open Bass in its normal Default mode. Custom tuning may use High Octave (Shift) when needed, "
            "but never presses < or >."
        )
    else:
        notice = (
            f"Open {instrument.title()} on the middle page in Default octave. Custom tuning may use Ctrl/Shift "
            "when needed, but never presses < or >."
        )
    return summary, notice


def _append_timing_preview(app: Any) -> None:
    plan = getattr(app, "current_plan", None)
    if plan is None or not hasattr(app, "analysis_var"):
        return
    base = str(app.analysis_var.get()).split(_TIMING_MARKER, 1)[0]
    articulation = str(getattr(plan, "articulation_mode", "balanced")).replace("_", " ").title()
    instrument = str(getattr(plan, "timing_profile", getattr(plan, "instrument", "keyboard"))).title()
    compressed = int(getattr(plan, "retrigger_compressed_notes", 0))
    merged = int(getattr(plan, "retrigger_merged_notes", 0))
    dropped = int(getattr(plan, "retrigger_dropped_notes", 0))
    adjusted = compressed + merged + dropped
    sustain = str(getattr(plan, "sustain_mode", "off")).replace("_", " ").title()

    if adjusted:
        repeat_text = f"rapid repeats {adjusted} adjusted ({compressed} shortened, {merged} merged, {dropped} dropped)"
    else:
        repeat_text = "rapid repeats clean"
    page_switches = int(getattr(plan, "page_switches", 0))
    page_text = f" • WARNING: {page_switches} unexpected page switch(es)" if page_switches else ""
    app.analysis_var.set(
        f"{base}{_TIMING_MARKER}{instrument} / {articulation} • {repeat_text} • sustain {sustain}{page_text}"
    )


def install_advanced_playback_profile(app_module: Any) -> None:
    """Integrate the v3.2 Custom timing profile into the 2026 single-window UI."""
    if getattr(app_module, "_advanced_playback_profile_installed", False):
        return

    original_labels_for = app_module.profile_labels_for
    original_label_for = app_module.profile_label_for

    def profile_labels_for(instrument: Any) -> dict[str, str]:
        labels = dict(original_labels_for(instrument))
        labels[CUSTOM_PROFILE_LABEL] = "custom"
        return labels

    def profile_label_for(instrument: Any, code: str) -> str:
        if code == "custom":
            return CUSTOM_PROFILE_LABEL
        return original_label_for(instrument, code)

    app_module.profile_labels_for = profile_labels_for
    app_module.profile_label_for = profile_label_for

    app_class = app_module.App
    original_build_ui = app_class._build_ui
    original_apply_profile_ui = app_class._apply_profile_ui
    original_custom_variable_changed = app_class._custom_variable_changed
    original_analyze = app_class._analyze
    original_thread_finished = app_class._thread_finished

    def build_ui(self: Any) -> None:
        original_build_ui(self)
        _prepare_custom_panel(self, app_module)

    def apply_profile_ui(self: Any, schedule: bool = True) -> None:
        if self._profile_code() != "custom":
            _show_custom_panel(self, False)
            original_apply_profile_ui(self, schedule=schedule)
            return

        instrument = self._instrument_code()
        self._active_instrument_code = instrument
        self._active_profile_code = "custom"
        self._profile_by_instrument[instrument] = "custom"
        self._refresh_custom_mode_choices()
        _show_custom_panel(self, True)
        _sync_custom_controls(self)
        summary, notice = _custom_profile_summary(self)
        self.profile_summary_var.set(summary)
        self.notice_var.set(notice)
        if schedule:
            self._schedule_analysis()

    def custom_variable_changed(self: Any, *args: object) -> None:
        original_custom_variable_changed(self, *args)
        if self._profile_code() == "custom":
            _sync_custom_controls(self)
            summary, notice = _custom_profile_summary(self)
            self.profile_summary_var.set(summary)
            self.notice_var.set(notice)

    def analyze(self: Any) -> None:
        original_analyze(self)
        _append_timing_preview(self)

    def thread_finished(self: Any, error: str | None) -> None:
        original_thread_finished(self, error)
        timing = str(getattr(self.player, "last_timing_summary", ""))
        if error is not None or not timing:
            return
        stopped = bool(self.player.stop_event.is_set())
        prefix = "Stopped. All keys released" if stopped else "Playback completed"
        duration = max(float(getattr(getattr(self, "current_plan", None), "duration", 0.0)), 0.001)
        progress = min(1.0, max(0.0, float(getattr(self.player, "position", 0.0)) / duration))
        self.ui_queue.put(("status", (f"{prefix} • {timing}", progress)))

    app_class._build_ui = build_ui
    app_class._apply_profile_ui = apply_profile_ui
    app_class._custom_variable_changed = custom_variable_changed
    app_class._analyze = analyze
    app_class._thread_finished = thread_finished
    app_module._advanced_playback_profile_installed = True
