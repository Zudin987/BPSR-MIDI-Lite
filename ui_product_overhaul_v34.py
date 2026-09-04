from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

import gaming_runtime_2026 as gaming_runtime
import gaming_ui_2026 as gaming_ui


_LIBRARY_WIDTH = 260
_CENTER_MIN_WIDTH = 500
_DRAWER_MIN_WIDTH = 285
_DRAWER_MAX_WIDTH = 340


def _plan_counts(plan: Any) -> tuple[int, int, int, int, int, int, int]:
    played = max(0, int(getattr(plan, "note_count", 0)))
    source = max(0, int(getattr(plan, "source_note_count", played)))
    remapped = max(0, int(getattr(plan, "remapped_notes", 0)))
    transposition = int(getattr(plan, "transposed_semitones", 0))
    folded = max(0, int(getattr(plan, "folded_notes", 0)))
    removed = max(
        0,
        int(getattr(plan, "skipped_notes", 0))
        + int(getattr(plan, "chord_removed_notes", 0))
        + int(getattr(plan, "retrigger_dropped_notes", 0)),
    )
    pages = max(0, int(getattr(plan, "page_switches", 0)))
    return played, source, remapped, transposition, folded, removed, pages


def product_metric_texts(plan: Any) -> dict[str, str]:
    """Return compact values for the user-facing Song Check cards."""
    if plan is None:
        return {
            "playable": "—",
            "pitch": "Waiting",
            "removed": "—",
            "safety": "Waiting",
        }

    played, source, remapped, transposition, folded, removed, pages = _plan_counts(plan)
    playable = f"{played:,}" if source == played else f"{played:,} / {source:,}"

    if transposition:
        pitch = f"{transposition:+d} st"
        if folded:
            pitch += f" + {folded:,} fits"
    elif remapped:
        pitch = f"{remapped:,} fits"
    else:
        pitch = "Original"

    safety = "No page keys" if pages == 0 else f"{pages} page change(s)"
    return {
        "playable": playable,
        "pitch": pitch,
        "removed": f"{removed:,}",
        "safety": safety,
    }


def product_summary_text(plan: Any) -> str:
    if plan is None:
        return "Choose a song to see how it will translate into BPSR."

    played, _source, remapped, transposition, folded, physical_removed, pages = _plan_counts(plan)
    safety = "No page keys" if pages == 0 else f"{pages} page change(s)"
    if transposition:
        pitch_text = f"Transposed {transposition:+d} st"
        if folded:
            pitch_text += f" • {folded:,} locally fitted"
    else:
        pitch_text = f"{remapped:,} pitch-fitted"

    if getattr(plan, "arrangement_strategy", "") == "auto_bass_line":
        bass_line = max(0, int(getattr(plan, "bass_line_notes", 0)))
        return (
            f"Auto Bass Line • {bass_line:,} bass-role notes detected • {played:,} playable • "
            f"{pitch_text} • {physical_removed:,} physical removals • {safety}"
        )

    return (
        f"{played:,} playable • {pitch_text} • {physical_removed:,} simplified/removed • "
        f"Peak {max(0, int(getattr(plan, 'max_simultaneous_keys', 0)))} key(s) • {safety}"
    )


def _install_product_styles(app: Any) -> None:
    style = getattr(app, "_style", None)
    if style is None:
        return
    try:
        style.configure("Product.MetricCard.TFrame", padding=(8, 7))
        style.configure(
            "Product.MetricName.TLabel",
            font=("Segoe UI Variable Text", 8),
        )
        style.configure(
            "Product.MetricValue.TLabel",
            font=("Segoe UI Variable Text", 10, "bold"),
        )
        style.configure(
            "Product.Status.TLabel",
            font=("Segoe UI Variable Text", 9),
        )
    except tk.TclError:
        pass


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
            button.configure(text="Details ▸")
        else:
            anchor = getattr(app, "_product_impact_anchor", None)
            if anchor is not None:
                label.pack(fill="x", anchor="w", pady=(5, 0), before=anchor)
            else:
                label.pack(fill="x", anchor="w", pady=(5, 0), after=button)
            button.configure(text="Details ▾")
        app._product_details_visible = not visible
    except tk.TclError:
        pass


def _find_label_by_variable(root: Any, variable: Any) -> Any | None:
    if root is None or variable is None:
        return None
    target = str(variable)
    for child in root.winfo_children():
        try:
            if child.winfo_class() == "TLabel" and str(child.cget("textvariable")) == target:
                return child
        except (tk.TclError, TypeError):
            pass
        nested = _find_label_by_variable(child, variable)
        if nested is not None:
            return nested
    return None


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
        "Session": "Settings",
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
    app._product_setup_frame = setup

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

    app._primary_profile_summary_label = ttk.Label(
        setup,
        textvariable=app.profile_summary_var,
        style="Hint.TLabel",
        wraplength=500,
        justify="left",
    )
    app._primary_profile_summary_label.grid(
        row=2,
        column=0,
        columnspan=2,
        sticky="ew",
        pady=(6, 0),
    )

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
    app._product_center = center

    row_zero = [child for child in center.grid_slaves(row=0) if child is not analysis]
    row_two = [child for child in center.grid_slaves(row=2) if child is not analysis]
    for child in row_zero:
        child.grid_configure(row=2)
    canvas.grid_configure(row=3)
    for child in row_two:
        child.grid_configure(row=4)
    analysis.grid_configure(row=1, sticky="ew", pady=(0, 8))
    center.rowconfigure(1, weight=0)
    center.rowconfigure(3, weight=1)
    canvas.configure(height=205)

    _build_primary_setup(app, center)


def _metric_card(parent: Any, title: str, variable: tk.StringVar, column: int) -> None:
    card = ttk.Frame(parent, style="Product.MetricCard.TFrame", padding=(8, 6))
    card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 4, 0))
    parent.columnconfigure(column, weight=1, uniform="song-metrics")
    ttk.Label(card, text=title, style="Product.MetricName.TLabel").pack(anchor="w")
    ttk.Label(card, textvariable=variable, style="Product.MetricValue.TLabel").pack(anchor="w", pady=(2, 0))


def _update_product_metrics(app: Any) -> None:
    values = product_metric_texts(getattr(app, "current_plan", None))
    variables = getattr(app, "_product_metric_vars", {})
    for key, value in values.items():
        variable = variables.get(key)
        if variable is not None:
            try:
                variable.set(value)
            except tk.TclError:
                pass


def _simplify_song_check(app: Any) -> None:
    frame = getattr(app, "analysis_frame", None)
    if frame is None:
        return

    app._product_summary_var = tk.StringVar(
        master=app,
        value=product_summary_text(getattr(app, "current_plan", None)),
    )
    app._product_metric_vars = {
        key: tk.StringVar(master=app, value=value)
        for key, value in product_metric_texts(getattr(app, "current_plan", None)).items()
    }
    anchor = _find_impact_anchor(app)
    app._product_impact_anchor = anchor

    metrics = ttk.Frame(frame)
    app._product_metrics_frame = metrics
    if anchor is not None:
        metrics.pack(fill="x", pady=(6, 4), before=anchor)
    else:
        metrics.pack(fill="x", pady=(6, 4))
    _metric_card(metrics, "Playable", app._product_metric_vars["playable"], 0)
    _metric_card(metrics, "Pitch", app._product_metric_vars["pitch"], 1)
    _metric_card(metrics, "Removed", app._product_metric_vars["removed"], 2)
    _metric_card(metrics, "Safety", app._product_metric_vars["safety"], 3)

    detail = _find_analysis_detail_label(app)
    app._product_detail_label = detail
    app._product_details_visible = False
    if detail is not None:
        detail.pack_forget()
        button = ttk.Button(
            frame,
            text="Details ▸",
            command=lambda: _toggle_technical_details(app),
        )
        app._product_detail_button = button
        if anchor is not None:
            button.pack(anchor="w", pady=(1, 5), before=anchor)
        else:
            button.pack(anchor="w", pady=(1, 5))

    app._product_impact_label = _find_label_by_variable(
        frame,
        getattr(app, "_adaptive_impact_var", None),
    )


def _library_set_visible(app: Any, visible: bool) -> None:
    panel = getattr(app, "_gaming_library_panel", None)
    body = getattr(app, "_gaming_body", None)
    if panel is None or body is None:
        return
    try:
        if visible:
            body.columnconfigure(0, minsize=_LIBRARY_WIDTH, weight=0)
            panel.grid()
            try:
                import online_ui

                online_ui._schedule_source_notebook_resize(app)
            except Exception:
                pass
        else:
            panel.grid_remove()
            body.columnconfigure(0, minsize=0, weight=0)
        app._gaming_library_visible = visible
    except tk.TclError:
        pass


def _toggle_library_product(app: Any) -> None:
    _library_set_visible(app, not bool(getattr(app, "_gaming_library_visible", True)))


def _drawer_width(app: Any) -> int:
    try:
        width = int(app.winfo_width())
    except (tk.TclError, TypeError, ValueError):
        width = 1180
    return max(_DRAWER_MIN_WIDTH, min(_DRAWER_MAX_WIDTH, int(width * 0.28)))


def _set_settings_drawer_visible(app: Any, visible: bool) -> None:
    panel = getattr(app, "_gaming_settings_panel", None)
    body = getattr(app, "_gaming_body", None)
    if panel is None or body is None:
        return
    try:
        body.columnconfigure(2, minsize=0, weight=0)
        panel.grid_remove()
        panel.place_forget()
        if visible:
            panel.place(
                relx=1.0,
                x=-1,
                y=0,
                anchor="ne",
                width=_drawer_width(app),
                relheight=1.0,
            )
            panel.lift()
        app._gaming_settings_visible = visible
    except tk.TclError:
        pass


def _toggle_settings_drawer(app: Any) -> None:
    _set_settings_drawer_visible(
        app,
        not bool(getattr(app, "_gaming_settings_visible", False)),
    )


def _responsive_product_layout(app: Any, width: int) -> None:
    if width < 760:
        if getattr(app, "_gaming_settings_visible", False):
            _set_settings_drawer_visible(app, False)
        if getattr(app, "_gaming_library_visible", True):
            _library_set_visible(app, False)
    elif width < 930 and getattr(app, "_gaming_library_visible", True):
        _library_set_visible(app, False)

    if getattr(app, "_gaming_settings_visible", False):
        panel = getattr(app, "_gaming_settings_panel", None)
        if panel is not None:
            try:
                panel.place_configure(width=_drawer_width(app))
            except tk.TclError:
                pass


def _configure_responsive_text(app: Any, width: int) -> None:
    usable = max(260, width - 24)
    for label in (
        getattr(app, "_primary_profile_summary_label", None),
        getattr(app, "_product_detail_label", None),
        getattr(app, "_product_impact_label", None),
    ):
        if label is not None:
            try:
                label.configure(wraplength=usable)
            except tk.TclError:
                pass


def _center_resized(app: Any, event: Any) -> None:
    try:
        width = int(event.width)
    except (AttributeError, TypeError, ValueError):
        return
    _configure_responsive_text(app, width)


def _add_drawer_close_control(app: Any) -> None:
    panel = getattr(app, "_gaming_settings_panel", None)
    if panel is None or hasattr(app, "_product_drawer_close"):
        return
    try:
        panel.columnconfigure(1, weight=0)
        app._product_drawer_close = ttk.Button(
            panel,
            text="×",
            width=3,
            command=lambda: _set_settings_drawer_visible(app, False),
        )
        app._product_drawer_close.grid(row=0, column=1, sticky="e", padx=(8, 0))
    except tk.TclError:
        pass


def _polish_bottom_status(app: Any) -> None:
    label = _find_label_by_variable(app, getattr(app, "status_var", None))
    if label is None:
        return
    app._product_status_label = label
    try:
        label.configure(style="Product.Status.TLabel", wraplength=560)
        label.grid_configure(sticky="ew")
    except tk.TclError:
        pass


def _polish_actions(app: Any) -> None:
    try:
        app.start_button.configure(text="Play in BPSR")
        app.stop_button.configure(text="Stop · F10")
    except (AttributeError, tk.TclError):
        pass

    try:
        app.instrument_combo.master.grid_remove()
    except (AttributeError, tk.TclError):
        pass


def _apply_layout_contract(app: Any) -> None:
    body = getattr(app, "_gaming_body", None)
    if body is None:
        return
    try:
        app.geometry("1120x720")
        app.minsize(760, 540)
        body.columnconfigure(0, weight=0, minsize=_LIBRARY_WIDTH)
        body.columnconfigure(1, weight=1, minsize=_CENTER_MIN_WIDTH)
        body.columnconfigure(2, weight=0, minsize=0)
    except tk.TclError:
        pass


def _product_build_ui(app: Any, original_build: Any) -> None:
    original_build(app)
    _install_product_styles(app)
    _apply_layout_contract(app)
    _restructure_center(app)
    _simplify_song_check(app)
    _rename_session_labels(app)
    _add_drawer_close_control(app)
    _polish_bottom_status(app)
    _polish_actions(app)

    center = getattr(app, "_product_center", None)
    if center is not None:
        center.bind("<Configure>", lambda event: _center_resized(app, event), add="+")
        app.after_idle(lambda: _configure_responsive_text(app, max(260, center.winfo_width())))

    _set_settings_drawer_visible(app, False)

    # Keep older runtime helpers in sync if they are invoked by integrations.
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
        _update_product_metrics(self)

    app_class._build_ui = build_ui
    app_class._analyze = analyze

    # Top-bar callbacks resolve these globals at click time, so replacing them
    # upgrades existing buttons without rebuilding the base gaming UI.
    gaming_ui._toggle_library = _toggle_library_product
    gaming_ui._toggle_settings = _toggle_settings_drawer
    gaming_ui._responsive_layout = _responsive_product_layout

    app_module._product_ui_overhaul_installed = True
