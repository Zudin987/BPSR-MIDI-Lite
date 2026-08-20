from __future__ import annotations

import ctypes
import os
import queue
import tkinter as tk
from collections import defaultdict
from tkinter import ttk
from typing import Any

from theme import apply_theme, theme_colors


KEY_LANES = (
    "z", "1", "x", "2", "c", "v", "3", "b", "4", "n", "5", "m",
    "a", "6", "s", "7", "d", "f", "8", "g", "9", "h", "0", "j",
    "q", "i", "w", "o", "e", "r", "p", "t", "[", "y", "]", "u",
)


def _enable_windows_backdrop(app: Any) -> None:
    """Best-effort Windows 11 Mica backdrop. Tk stays fully usable without it."""
    if os.name != "nt":
        return
    try:
        app.update_idletasks()
        user32 = ctypes.windll.user32
        dwmapi = ctypes.windll.dwmapi
        widget_hwnd = int(app.winfo_id())
        hwnd = int(user32.GetParent(widget_hwnd)) or widget_hwnd
        dark = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
        # DWMWA_SYSTEMBACKDROP_TYPE = 38, DWMSBT_MAINWINDOW = 2 (Mica).
        backdrop = ctypes.c_int(2)
        dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop), ctypes.sizeof(backdrop))
    except (AttributeError, OSError, TypeError, ValueError):
        pass


def _apply_gaming_styles(app: Any) -> None:
    colors = theme_colors(True)
    style = app._style
    style.configure("Gaming.Top.TFrame", background=colors.surface)
    style.configure("Gaming.Card.TFrame", background="#171b22")
    style.configure("Gaming.Toolbar.TFrame", background="#11151b")
    style.configure("Gaming.Hero.TLabel", background=colors.surface, foreground=colors.foreground, font=("Segoe UI Variable Display", 18, "bold"))
    style.configure("Gaming.Subtitle.TLabel", background=colors.surface, foreground=colors.muted, font=("Segoe UI Variable Text", 9))
    style.configure("Gaming.Section.TLabel", foreground=colors.foreground, font=("Segoe UI Variable Text", 10, "bold"))
    style.configure("Gaming.Metric.TLabel", foreground=colors.accent, font=("Segoe UI Variable Text", 10, "bold"))
    style.configure("Gaming.Micro.TLabel", foreground=colors.muted, font=("Segoe UI Variable Text", 8))
    style.configure("Gaming.Play.TButton", font=("Segoe UI Variable Text", 11, "bold"), padding=(18, 10))
    style.configure("Gaming.Pause.TButton", font=("Segoe UI Variable Text", 10, "bold"), padding=(14, 10))
    style.configure("Gaming.Panic.TButton", font=("Segoe UI Variable Text", 10, "bold"), padding=(14, 10))
    style.map(
        "Gaming.Panic.TButton",
        foreground=[("!disabled", "#ffffff")],
        background=[("!disabled", "#8c1d2c"), ("active", "#aa2638"), ("pressed", "#6f1622")],
    )
    style.configure("Gaming.Sidebar.TLabelframe", background="#171b22", bordercolor="#303845")
    style.configure("Gaming.Sidebar.TLabelframe.Label", background="#171b22", foreground=colors.foreground, font=("Segoe UI Variable Text", 9, "bold"))
    style.configure("Gaming.Treeview", rowheight=28)


def _gaming_apply_system_theme(self: Any, force: bool = False) -> None:
    del force
    self._dark_mode = True
    apply_theme(self, self._style, True)
    _apply_gaming_styles(self)
    _enable_windows_backdrop(self)


def _toggle_library(app: Any) -> None:
    panel = getattr(app, "_gaming_library_panel", None)
    if panel is None:
        return
    visible = bool(getattr(app, "_gaming_library_visible", True))
    if visible:
        panel.grid_remove()
    else:
        panel.grid()
        try:
            import online_ui

            online_ui._schedule_source_notebook_resize(app)
        except Exception:
            pass
    app._gaming_library_visible = not visible


def _toggle_settings(app: Any) -> None:
    panel = getattr(app, "_gaming_settings_panel", None)
    if panel is None:
        return
    visible = bool(getattr(app, "_gaming_settings_visible", True))
    if visible:
        panel.grid_remove()
    else:
        panel.grid()
    app._gaming_settings_visible = not visible


def _responsive_layout(app: Any, width: int) -> None:
    """Collapse sidebars as the app becomes a compact player."""
    if width < 790:
        if getattr(app, "_gaming_settings_visible", True):
            app._gaming_settings_panel.grid_remove()
            app._gaming_settings_visible = False
        if getattr(app, "_gaming_library_visible", True):
            app._gaming_library_panel.grid_remove()
            app._gaming_library_visible = False
    elif width < 1030:
        if getattr(app, "_gaming_settings_visible", True):
            app._gaming_settings_panel.grid_remove()
            app._gaming_settings_visible = False
    # Wider sizes do not forcibly reopen a panel the user deliberately closed.


def _build_note_spans(plan: Any) -> dict[str, list[tuple[float, float]]]:
    active: dict[str, list[float]] = defaultdict(list)
    spans: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for event in getattr(plan, "events", ()):  # preserve the engine's prepared timeline exactly
        key = getattr(event, "key", None)
        if not key:
            continue
        if event.kind == "note_on":
            active[key].append(float(event.time))
        elif event.kind == "note_off" and active[key]:
            start = active[key].pop(0)
            end = max(start + 0.02, float(event.time))
            spans[key].append((start, end))
    duration = float(getattr(plan, "duration", 0.0))
    for key, starts in active.items():
        for start in starts:
            spans[key].append((start, max(start + 0.08, duration)))
    return spans


def _visualizer_colors(app: Any) -> dict[str, str]:
    colors = theme_colors(True)
    return {
        "bg": "#0c1016",
        "grid": "#1e2834",
        "note": colors.accent,
        "active": "#7ee787",
        "line": "#ffffff",
        "text": colors.muted,
    }


def _render_visualizer(app: Any) -> None:
    canvas = getattr(app, "midi_visualizer", None)
    if canvas is None:
        return
    try:
        width = max(10, canvas.winfo_width())
        height = max(10, canvas.winfo_height())
        palette = _visualizer_colors(app)
        canvas.configure(background=palette["bg"])
        canvas.delete("all")

        plan = getattr(app, "current_plan", None)
        plan_id = id(plan) if plan is not None else None
        if plan_id != getattr(app, "_gaming_visual_plan_id", None):
            app._gaming_visual_plan_id = plan_id
            app._gaming_note_spans = _build_note_spans(plan) if plan is not None else {}

        lane_count = len(KEY_LANES)
        lane_w = width / lane_count
        for index in range(lane_count + 1):
            x = index * lane_w
            canvas.create_line(x, 0, x, height, fill=palette["grid"])

        now = float(getattr(getattr(app, "player", None), "position", 0.0))
        if not getattr(app.player, "is_playing", False):
            now = 0.0
        lookahead = 5.0
        current_y = height - 34
        spans = getattr(app, "_gaming_note_spans", {})
        for lane_index, key in enumerate(KEY_LANES):
            x1 = lane_index * lane_w + 1
            x2 = (lane_index + 1) * lane_w - 1
            for start, end in spans.get(key, ()):
                if end < now - 0.15 or start > now + lookahead:
                    continue
                y_start = current_y - ((start - now) / lookahead) * max(1, current_y - 8)
                y_end = current_y - ((end - now) / lookahead) * max(1, current_y - 8)
                top = min(y_start, y_end)
                bottom = max(y_start, y_end)
                canvas.create_rectangle(x1, top, x2, bottom, fill=palette["note"], outline="")

        active_keys = tuple(getattr(app.player, "active_keys", ()))
        for key in active_keys:
            if key not in KEY_LANES:
                continue
            lane_index = KEY_LANES.index(key)
            x1 = lane_index * lane_w + 1
            x2 = (lane_index + 1) * lane_w - 1
            canvas.create_rectangle(x1, current_y, x2, height, fill=palette["active"], outline="")

        canvas.create_line(0, current_y, width, current_y, fill=palette["line"], width=2)
        if plan is None:
            canvas.create_text(width / 2, height / 2, text="Choose a song to preview the BPSR note stream", fill=palette["text"], font=("Segoe UI Variable Text", 11))
        elif not app.player.is_playing:
            canvas.create_text(12, 12, anchor="nw", text="5-second note preview", fill=palette["text"], font=("Segoe UI Variable Text", 8))

        active_text = "  ".join(key.upper() for key in active_keys[:12]) if active_keys else "—"
        app._gaming_active_keys_var.set(active_text)
        activity = min(100, len(active_keys) * 18)
        app._gaming_activity_var.set(activity)

        if plan is None:
            app._gaming_router_var.set("Auto router • waiting for a song")
        else:
            percussion = "drums ignored" if bool(getattr(app, "percussion_var", tk.BooleanVar(value=True)).get()) else "drums included"
            app._gaming_router_var.set(
                f"Auto router • {plan.source_track_count} track(s) • {percussion} • max chord {plan.max_planned_chord}"
            )
    except (tk.TclError, AttributeError, TypeError, ValueError):
        pass
    try:
        app.after(80, lambda: _render_visualizer(app))
    except tk.TclError:
        pass


def _sync_speed_scale(app: Any, *_args: object) -> None:
    if getattr(app, "_gaming_speed_sync", False):
        return
    try:
        value = int(app.speed_var.get())
        app._gaming_speed_sync = True
        app._gaming_speed_scale_var.set(value)
        app._gaming_speed_text_var.set(f"{value}%")
    except (tk.TclError, TypeError, ValueError):
        pass
    finally:
        app._gaming_speed_sync = False


def _speed_scale_changed(app: Any, value: str) -> None:
    if getattr(app, "_gaming_speed_sync", False):
        return
    try:
        snapped = max(25, min(200, int(round(float(value) / 5.0) * 5)))
        if int(app.speed_var.get()) != snapped:
            app.speed_var.set(snapped)
    except (tk.TclError, TypeError, ValueError):
        pass


def _toggle_pause(app: Any) -> None:
    try:
        paused = bool(app.player.toggle_pause())
    except Exception as exc:  # noqa: BLE001
        app.status_var.set(f"Pause unavailable: {exc}")
        return
    app.pause_button.configure(text="Resume" if paused else "Pause")
    app.status_var.set("Paused — BPSR keys released. Press Resume to continue." if paused else "Resuming playback…")


def _single_window_start(self: Any) -> None:
    if os.name != "nt":
        self.status_var.set("Playback is supported only on Windows.")
        self.suitability_var.set("Playback unavailable on this operating system")
        self.suitability_label.configure(style="Danger.TLabel")
        return
    self._analyze()
    if self.current_plan is None:
        self.status_var.set("Choose a valid MIDI or online song first.")
        return
    try:
        delay = float(self.start_delay_var.get())
        self.player.start(
            self.current_plan,
            delay,
            self._thread_status,
            self._thread_finished,
            input_backend=self._input_backend_code(),
        )
    except Exception as exc:  # noqa: BLE001
        self._last_error = f"Playback start: {exc}"
        self.status_var.set(self._input_error_message(exc).replace("\n", " "))
        self.suitability_var.set("Could not start playback")
        self.suitability_label.configure(style="Danger.TLabel")
        return

    self.start_button.configure(state="disabled")
    self.pause_button.configure(state="normal", text="Pause")
    self.stop_button.configure(state="normal")
    self.progress["value"] = 0
    self._save_config()


def _single_window_drain_ui_queue(self: Any) -> None:
    try:
        while True:
            kind, payload = self.ui_queue.get_nowait()
            if kind == "status":
                text, progress = payload
                self.status_var.set(str(text))
                self.progress["value"] = float(progress)
            elif kind == "finished":
                self.start_button.configure(state="normal")
                self.pause_button.configure(state="disabled", text="Pause")
                self.stop_button.configure(state="disabled")
                if payload:
                    self._last_error = f"Playback: {payload}"
                    self.status_var.set("Playback error: " + self._input_error_message(payload).replace("\n", " "))
                    self.suitability_var.set("Playback stopped with an error")
                    self.suitability_label.configure(style="Danger.TLabel")
                elif self.player.stop_event.is_set():
                    self._last_error = None
                    self.status_var.set("Stopped. All keys released and instrument mode reset.")
                else:
                    self._last_error = None
                    self.status_var.set("Playback completed. Instrument mode reset.")
    except queue.Empty:
        pass
    self.after(50, self._drain_ui_queue)


def _gaming_build_ui(self: Any) -> None:
    self._apply_system_theme(force=True)
    self.geometry("1180x720")
    self.minsize(700, 520)

    self._gaming_library_visible = True
    self._gaming_settings_visible = True
    self._gaming_visual_plan_id = None
    self._gaming_note_spans: dict[str, list[tuple[float, float]]] = {}
    self._gaming_speed_sync = False
    self._gaming_active_keys_var = tk.StringVar(master=self, value="—")
    self._gaming_activity_var = tk.IntVar(master=self, value=0)
    self._gaming_router_var = tk.StringVar(master=self, value="Auto router • waiting for a song")
    self._gaming_speed_scale_var = tk.DoubleVar(master=self, value=float(self.speed_var.get()))
    self._gaming_speed_text_var = tk.StringVar(master=self, value=f"{int(self.speed_var.get())}%")

    self.columnconfigure(0, weight=1)
    self.rowconfigure(1, weight=1)

    top = ttk.Frame(self, style="Gaming.Top.TFrame", padding=(14, 10))
    top.grid(row=0, column=0, sticky="ew")
    top.columnconfigure(2, weight=1)
    ttk.Label(top, text="BPSR MIDI", style="Gaming.Hero.TLabel").grid(row=0, column=0, sticky="w")
    version = str(getattr(self._modern_module, "APP_VERSION", ""))
    ttk.Label(top, text=version, style="Gaming.Subtitle.TLabel").grid(row=0, column=1, sticky="w", padx=(8, 0), pady=(5, 0))
    ttk.Button(top, text="Library", command=lambda: _toggle_library(self)).grid(row=0, column=3, padx=(8, 0))
    ttk.Button(top, text="Settings", command=lambda: _toggle_settings(self)).grid(row=0, column=4, padx=(8, 0))

    body = ttk.Frame(self, padding=(10, 10, 10, 8))
    body.grid(row=1, column=0, sticky="nsew")
    body.rowconfigure(0, weight=1)
    body.columnconfigure(0, weight=0, minsize=330)
    body.columnconfigure(1, weight=1, minsize=320)
    body.columnconfigure(2, weight=0, minsize=255)
    self._gaming_body = body

    # LEFT — library/source sidebar. Online/Local/Studio integrations replace
    # only the row-0 song picker after this builder runs.
    left = ttk.Frame(body, style="Gaming.Card.TFrame", padding=10)
    left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
    left.columnconfigure(0, weight=1)
    left.rowconfigure(1, weight=1)
    self._gaming_library_panel = left

    ttk.Label(left, text="MIDI Library", style="Gaming.Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
    songs = ttk.LabelFrame(left, text="2  Song", style="Gaming.Sidebar.TLabelframe", padding=8)
    songs.grid(row=1, column=0, sticky="nsew")
    songs.columnconfigure(0, weight=1)
    songs.rowconfigure(0, weight=1)

    self.midi_combo = ttk.Combobox(songs, textvariable=self.midi_display_var, state="readonly", values=())
    self.midi_combo.grid(row=0, column=0, sticky="ew")
    self.midi_combo.bind("<<ComboboxSelected>>", lambda _event: self._midi_selected())
    ttk.Button(songs, text="Open folder", command=self._open_midi_folder).grid(row=0, column=1, padx=(8, 0))
    ttk.Label(
        songs,
        text="Local, Online Sequencer, bookmarks, and Studio sources stay inside this window.",
        style="Hint.TLabel",
        wraplength=285,
        justify="left",
    ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(7, 0))

    # CENTER — reactive waterfall and song check.
    center = ttk.Frame(body, style="Gaming.Card.TFrame", padding=10)
    center.grid(row=0, column=1, sticky="nsew", padx=8)
    center.columnconfigure(0, weight=1)
    center.rowconfigure(1, weight=1)
    ttk.Label(center, text="Live MIDI", style="Gaming.Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 7))
    self.midi_visualizer = tk.Canvas(center, height=360, borderwidth=0, highlightthickness=1, highlightbackground="#303845")
    self.midi_visualizer.grid(row=1, column=0, sticky="nsew")

    input_strip = ttk.Frame(center, padding=(0, 8, 0, 6))
    input_strip.grid(row=2, column=0, sticky="ew")
    input_strip.columnconfigure(1, weight=1)
    ttk.Label(input_strip, text="Active input", style="Gaming.Micro.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(input_strip, textvariable=self._gaming_active_keys_var, style="Gaming.Metric.TLabel").grid(row=0, column=1, sticky="w", padx=(10, 0))
    ttk.Progressbar(input_strip, maximum=100, variable=self._gaming_activity_var).grid(row=0, column=2, sticky="e", ipadx=35)

    self.analysis_frame = ttk.LabelFrame(center, text="Song check", padding=9)
    self.analysis_frame.grid(row=3, column=0, sticky="ew")
    self.suitability_label = ttk.Label(self.analysis_frame, textvariable=self.suitability_var, style="Ready.TLabel")
    self.suitability_label.pack(anchor="w")
    ttk.Label(self.analysis_frame, textvariable=self.analysis_var, style="Hint.TLabel", wraplength=520, justify="left").pack(anchor="w", pady=(5, 0))

    # RIGHT — inline session/settings panel, never a secondary window.
    right = ttk.Frame(body, style="Gaming.Card.TFrame", padding=10)
    right.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
    right.columnconfigure(0, weight=1)
    self._gaming_settings_panel = right
    ttk.Label(right, text="Session", style="Gaming.Section.TLabel").grid(row=0, column=0, sticky="w")

    ttk.Label(right, text="Game setup", style="Gaming.Micro.TLabel").grid(row=1, column=0, sticky="w", pady=(12, 3))
    ttk.Label(right, textvariable=self.profile_summary_var, style="Hint.TLabel", wraplength=225, justify="left").grid(row=2, column=0, sticky="w")

    ttk.Label(right, text="Start countdown", style="Gaming.Micro.TLabel").grid(row=3, column=0, sticky="w", pady=(12, 3))
    countdown = ttk.Frame(right)
    countdown.grid(row=4, column=0, sticky="ew")
    ttk.Spinbox(countdown, from_=0, to=30, increment=0.5, textvariable=self.start_delay_var, width=6).pack(side="left")
    ttk.Label(countdown, text="sec", style="Hint.TLabel").pack(side="left", padx=(5, 0))

    ttk.Separator(right).grid(row=5, column=0, sticky="ew", pady=12)
    ttk.Label(right, text="Track / channel router", style="Gaming.Micro.TLabel").grid(row=6, column=0, sticky="w")
    ttk.Label(right, textvariable=self._gaming_router_var, style="Hint.TLabel", wraplength=225, justify="left").grid(row=7, column=0, sticky="w", pady=(3, 0))

    ttk.Label(right, text="Virtual-key connection", style="Gaming.Micro.TLabel").grid(row=8, column=0, sticky="w", pady=(12, 3))
    self.input_backend_combo = ttk.Combobox(
        right,
        textvariable=self.input_backend_var,
        values=list(self._modern_module.INPUT_BACKEND_LABELS),
        state="readonly",
        width=26,
    )
    self.input_backend_combo.grid(row=9, column=0, sticky="ew")
    self.input_backend_combo.bind("<<ComboboxSelected>>", lambda _event: self._save_config())
    ttk.Label(right, text="Mapping stays automatic for the selected BPSR category.", style="Hint.TLabel", wraplength=225, justify="left").grid(row=10, column=0, sticky="w", pady=(5, 0))

    ttk.Button(right, text="Restore recommended settings", command=self._reset_defaults).grid(row=11, column=0, sticky="ew", pady=(14, 0))
    ttk.Separator(right).grid(row=12, column=0, sticky="ew", pady=12)
    ttk.Label(right, textvariable=self.notice_var, style="Hint.TLabel", wraplength=225, justify="left").grid(row=13, column=0, sticky="w")

    # BOTTOM — anchored quick controls, always visible in compact mode.
    controls = ttk.Frame(self, style="Gaming.Toolbar.TFrame", padding=(12, 10))
    controls.grid(row=2, column=0, sticky="ew")
    controls.columnconfigure(3, weight=1)

    preset = ttk.Frame(controls, style="Gaming.Toolbar.TFrame")
    preset.grid(row=0, column=0, sticky="w")
    ttk.Label(preset, text="Preset", style="Gaming.Micro.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
    self.instrument_combo = ttk.Combobox(preset, textvariable=self.instrument_var, values=list(self._modern_module.INSTRUMENT_LABELS), state="readonly", width=10)
    self.instrument_combo.grid(row=1, column=0, sticky="w", pady=(3, 0))
    self.instrument_combo.bind("<<ComboboxSelected>>", lambda _event: self._instrument_changed())
    self.profile_combo = ttk.Combobox(preset, textvariable=self.profile_var, values=list(self._modern_module.profile_labels_for("keyboard")), state="readonly", width=27)
    self.profile_combo.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(3, 0))
    self.profile_combo.bind("<<ComboboxSelected>>", lambda _event: self._profile_changed())

    tempo = ttk.Frame(controls, style="Gaming.Toolbar.TFrame")
    tempo.grid(row=0, column=1, sticky="ew", padx=(16, 12))
    tempo.columnconfigure(0, weight=1)
    ttk.Label(tempo, text="Tempo / speed", style="Gaming.Micro.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(tempo, textvariable=self._gaming_speed_text_var, style="Gaming.Metric.TLabel").grid(row=0, column=1, sticky="e")
    ttk.Scale(tempo, from_=25, to=200, variable=self._gaming_speed_scale_var, command=lambda value: _speed_scale_changed(self, value), length=180).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(3, 0))

    progress_frame = ttk.Frame(controls, style="Gaming.Toolbar.TFrame")
    progress_frame.grid(row=0, column=3, sticky="ew", padx=(4, 12))
    progress_frame.columnconfigure(0, weight=1)
    self.progress = ttk.Progressbar(progress_frame, maximum=1.0, mode="determinate")
    self.progress.grid(row=0, column=0, sticky="ew")
    ttk.Label(progress_frame, textvariable=self.status_var, style="Gaming.Micro.TLabel", wraplength=420, justify="left").grid(row=1, column=0, sticky="w", pady=(4, 0))

    actions = ttk.Frame(controls, style="Gaming.Toolbar.TFrame")
    actions.grid(row=0, column=4, sticky="e")
    self.start_button = ttk.Button(actions, text="Play", style="Gaming.Play.TButton", command=self._start, state="disabled")
    self.start_button.pack(side="left")
    self.pause_button = ttk.Button(actions, text="Pause", style="Gaming.Pause.TButton", command=lambda: _toggle_pause(self), state="disabled")
    self.pause_button.pack(side="left", padx=(6, 0))
    self.stop_button = ttk.Button(actions, text="Panic Stop  F10", style="Gaming.Panic.TButton", command=self._stop, state="disabled")
    self.stop_button.pack(side="left", padx=(6, 0))

    self.speed_var.trace_add("write", lambda *_args: _sync_speed_scale(self))
    self.bind("<Configure>", lambda event: _responsive_layout(self, int(event.width)) if event.widget is self else None, add="+")
    self.after(80, lambda: _render_visualizer(self))
    self.after(1500, lambda: self._modern_module.scan_midi_folder(self.midi_folder_var.get()) and None)


def install_gaming_ui_2026(app_module: Any) -> None:
    """Replace only the presentation layer; planner/routing/input logic remains intact."""
    app_class = app_module.App
    if getattr(app_class, "_gaming_ui_2026_installed", False):
        return

    app_class._gaming_original_build_ui = app_class._build_ui
    app_class._gaming_original_apply_system_theme = app_class._apply_system_theme
    app_class._gaming_original_start = app_class._start
    app_class._gaming_original_drain_ui_queue = app_class._drain_ui_queue

    app_class._build_ui = _gaming_build_ui
    app_class._apply_system_theme = _gaming_apply_system_theme
    app_class._start = _single_window_start
    app_class._drain_ui_queue = _single_window_drain_ui_queue
    app_class._gaming_ui_2026_installed = True
