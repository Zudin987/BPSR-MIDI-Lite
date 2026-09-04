from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

import gaming_runtime_2026 as gaming_runtime


def product_summary_text(plan: Any) -> str:
    if plan is None:
        return "Choose a song to see how it will translate into BPSR."

    played = max(0, int(getattr(plan, "note_count", 0)))
    remapped = max(0, int(getattr(plan, "remapped_notes", 0)))
    arranged = max(0, int(getattr(plan, "arranged_out_notes", 0)))
    skipped = max(0, int(getattr(plan, "skipped_notes", 0)))
    chord_removed = max(0, int(getattr(plan, "chord_removed_notes", 0)) - arranged)
    retrigger_dropped = max(0, int(getattr(plan, "retrigger_dropped_notes", 0)))
    physical_removed = skipped + chord_removed + retrigger_dropped
    peak_keys = max(0, int(getattr(plan, "max_simultaneous_keys", 0)))
    pages = max(0, int(getattr(plan, "page_switches", 0)))
    safety = "No page keys" if pages == 0 else f"{pages} page change(s)"

    if getattr(plan, "arrangement_strategy", "") == "auto_bass_line":
        bass_line = max(0, int(getattr(plan, "bass_line_notes", 0)))
        return (
            f"Auto Bass Line • {bass_line:,} bass-role notes detected • {played:,} playable • "
            f"{remapped:,} pitch-fitted • {physical_removed:,} physical removals • {safety}"
        )

    return (
        f"{played:,} playable • {remapped:,} pitch-fitted • {physical_removed:,} simplified/removed • "
        f"Peak {peak_keys} key(s) • {safety}"
    )


def _sync_primary_profile_values(app: Any) -> None:
    combo = getattr(app, "_primary_profile_combo", None)
    source = getattr(app, "profile_combo", None)
    if combo is None or source is None:
        return
    try:
        combo.configure(values=source.cget("values"))
    except tk.TclError:
        pass


def _toggle_technical_details(app: Any) -> None:
    label = getattr(app, "_product_detail_label", None)
    button = getattr(app, "_product_detail_button", None)
    if label is None or button is None:
        return
    visible = bool(getattr(app, "_product_details_visible", False))
    try:
        if visible:
            label.pack_forget()
            button.configure(text="Technical details ▸")
        else:
            anchor = getattr(app, "_product_impact_anchor", None)
            if anchor is not None:
                label.pack(anchor="w", pady=(5, 0), before=anchor)
            else:
                label.pack(anchor="w", pady=(5, 0), after=button)
            button.configure(text="Technical details ▾")
        app._product_details_visible = not visible
    except tk.TclError:
        pass


def _find_analysis_detail_label(app: Any) -> Any | None:
    frame = getattr(app, "analysis_frame", None)
    if frame is None:
        return None
    target = str(getattr(app, "analysis_var", ""))
    for child in frame.winfo_children():
        if child is getattr(app, "suitability_label", None):
            continue
        try:
            if child.winfo_class() == "TLabel" and str(child.cget("textvariable")) == target:
                return child
        except tk.TclError:
            continue
    return None


def _find_impact_anchor(app: Any) -> Any | None:
    frame = getattr(app, "analysis_frame", None)
    if frame is None:
        return None
    for child in frame.winfo_children():
        try:
            if child.winfo_class() == "TSeparator":
                return child
        except tk.TclError:
            continue
    return None


def _rename_session_labels(app: Any) -> None:
    panel = getattr(app, "_gaming_settings_panel", None)
    if panel is None:
        return
    replacements = {
        "Game setup": "Current setup",
        "Track / channel router": "Arrangement",
        "Virtual-key connection": "Keyboard connection",
    }
    for child in panel.winfo_children():
        try:
            text = str(child.cget("text"))
        except (tk.TclError, TypeError):
            continue
        if text in replacements:
            try:
                child.configure(text=replacements[text])
            except tk.TclError:
                pass


def _build_primary_setup(app: Any, center: Any) -> None:
    setup = ttk.LabelFrame(center, text="BPSR setup", padding=9)
    setup.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    setup.columnconfigure(0, weight=1, uniform="primary-setup")
    setup.columnconfigure(1, weight=2, uniform="primary-setup")

    ttk.Label(setup, text="Instrument", style="Gaming.Micro.TLabel").grid(
        row=0, column=0, sticky="w", padx=(0, 8)
    )
    ttk.Label(setup, text="Unlocked category", style="Gaming.Micro.TLabel").grid(
        row=0, column=1, sticky="w"
    )

    app._primary_instrument_combo = ttk.Combobox(
        setup,
        textvariable=app.instrument_var,
        values=list(app._modern_module.INSTRUMENT_LABELS),
        state="readonly",
    )
    app._primary_instrument_combo.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(3, 0))

    app._primary_profile_combo = ttk.Combobox(
        setup,
        textvariable=app.profile_var,
        values=app.profile_combo.cget("values"),
        state="readonly",
    )
    app._primary_profile_combo.grid(row=1, column=1, sticky="ew", pady=(3, 0))

    def instrument_changed(_event: Any = None) -> None:
        app._instrument_changed()
        _sync_primary_profile_values(app)

    app._primary_instrument_combo.bind("<<ComboboxSelected>>", instrument_changed)
    app._primary_profile_combo.bind("<<ComboboxSelected>>", lambda _event: app._profile_changed())

    ttk.Label(
        setup,
        textvariable=app.profile_summary_var,
        style="Hint.TLabel",
        wraplength=620,
        justify="left",
    ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

    app.instrument_var.trace_add(
        "write",
        lambda *_args: app.after_idle(lambda: _sync_primary_profile_values(app)),
    )


def _restructure_center(app: Any) -> None:
    canvas = getattr(app, "midi_visualizer", None)
    analysis = getattr(app, "analysis_frame", None)
    if canvas is None or analysis is None:
        return
    center = canvas.master

    # The original center is Live MIDI label / waterfall / active-input strip /
    # Song Check. Put the decision-making controls and fit verdict first.
    row_zero = [child for child in center.grid_slaves(row=0) if child is not analysis]
    row_two = [child for child in center.grid_slaves(row=2) if child is not analysis]
    for child in row_zero:
        child.grid_configure(row=2)
    canvas.grid_configure(row=3)
    for child in row_two:
        child.grid_configure(row=4)
    analysis.grid_configure(row=1, pady=(0, 8))
    center.rowconfigure(1, weight=0)
    center.rowconfigure(3, weight=1)
    canvas.configure(height=220)

    _build_primary_setup(app, center)


def _simplify_song_check(app: Any) -> None:
    frame = getattr(app, "analysis_frame", None)
    if frame is None:
        return

    app._product_summary_var = tk.StringVar(master=app, value=product_summary_text(getattr(app, "current_plan", None)))
    anchor = _find_impact_anchor(app)
    app._product_impact_anchor = anchor

    summary_label = ttk.Label(
        frame,
        textvariable=app._product_summary_var,
        style="Gaming.Metric.TLabel",
        wraplength=680,
        justify="left",
    )
    if anchor is not None:
        summary_label.pack(anchor="w", pady=(4, 3), before=anchor)
    else:
        summary_label.pack(anchor="w", pady=(4, 3))

    detail = _find_analysis_detail_label(app)
    app._product_detail_label = detail
    app._product_details_visible = False
    if detail is not None:
        detail.pack_forget()
        button = ttk.Button(
            frame,
            text="Technical details ▸",
            command=lambda: _toggle_technical_details(app),
        )
        app._product_detail_button = button
        if anchor is not None:
            button.pack(anchor="w", pady=(2, 5), before=anchor)
        else:
            button.pack(anchor="w", pady=(2, 5))


def _polish_actions(app: Any) -> None:
    try:
        app.start_button.configure(text="Play in BPSR")
        app.stop_button.configure(text="Stop · F10")
    except (AttributeError, tk.TclError):
        pass

    # Instrument/category now live in the primary setup card. Remove the
    # duplicate bottom preset block while keeping its widgets alive for legacy
    # integration code that still updates them.
    try:
        app.instrument_combo.master.grid_remove()
    except (AttributeError, tk.TclError):
        pass


def _product_build_ui(app: Any, original_build: Any) -> None:
    original_build(app)
    _restructure_center(app)
    _simplify_song_check(app)
    _rename_session_labels(app)
    _polish_actions(app)

    # Settings are recovery/advanced controls, not the main playback path.
    # Keep them one click away and give the song/fit view the default width.
    try:
        gaming_runtime._set_settings_visible(app, False)
    except Exception:
        pass


def install_product_ui_overhaul(app_module: Any) -> None:
    if getattr(app_module, "_product_ui_overhaul_installed", False):
        return

    app_class = app_module.App
    original_build = app_class._build_ui
    original_analyze = app_class._analyze

    def build_ui(self: Any) -> None:
        _product_build_ui(self, original_build)

    def analyze(self: Any) -> None:
        original_analyze(self)
        if hasattr(self, "_product_summary_var"):
            try:
                self._product_summary_var.set(product_summary_text(getattr(self, "current_plan", None)))
            except tk.TclError:
                pass

    app_class._build_ui = build_ui
    app_class._analyze = analyze
    app_module._product_ui_overhaul_installed = True
