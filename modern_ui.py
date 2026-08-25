from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable


"""Beginner-first single-page UI for BPSR MIDI Lite.

The interface exposes the musical choices a normal player needs: instrument,
BPSR category, MIDI song, song speed, countdown, and Play. Keyboard connection
is kept as a visible recovery option because different Windows/game setups can
accept different input methods. Technical MIDI fitting remains automatic.
"""


def _apply_simple_styles(app: Any) -> None:
    style = app._style
    style.configure("Hero.TLabel", font=("Segoe UI", 21, "bold"))
    style.configure("Subtitle.TLabel", font=("Segoe UI", 10))
    style.configure("Section.TLabel", font=("Segoe UI", 10, "bold"))
    style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"), padding=(18, 10))
    style.configure("Stop.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 8))
    style.configure("Soft.TButton", padding=(10, 6))
    style.configure("Ready.TLabel", font=("Segoe UI", 11, "bold"))


def _refresh_scroll_region(self: Any) -> None:
    if not hasattr(self, "_scroll_canvas"):
        return
    bbox = self._scroll_canvas.bbox("all")
    if bbox:
        self._scroll_canvas.configure(scrollregion=bbox)


def _scroll_mousewheel(self: Any, event: Any) -> None:
    if not hasattr(self, "_scroll_canvas"):
        return

    widget_class = ""
    try:
        widget_class = event.widget.winfo_class()
    except (AttributeError, tk.TclError):
        pass
    if widget_class in {"TCombobox", "TSpinbox", "Spinbox"}:
        return

    delta = getattr(event, "delta", 0)
    if delta:
        steps = -int(delta / 120)
        if steps == 0:
            steps = -1 if delta > 0 else 1
        self._scroll_canvas.yview_scroll(steps, "units")
    elif getattr(event, "num", None) == 4:
        self._scroll_canvas.yview_scroll(-1, "units")
    elif getattr(event, "num", None) == 5:
        self._scroll_canvas.yview_scroll(1, "units")


def _poll_song_library(self: Any) -> None:
    """Refresh the song picker when files are added/removed in the opened folder."""
    try:
        if not self.player.is_playing:
            folder = Path(self.midi_folder_var.get())
            files = self._modern_module.scan_midi_folder(folder)
            names = [path.relative_to(folder).as_posix() for path in files]
            if names != list(self._midi_lookup):
                self._reload_midi_library(
                    analyze=True,
                    preferred_display=self.midi_display_var.get(),
                )
    except (OSError, tk.TclError):
        pass

    try:
        self.after(1500, lambda: _poll_song_library(self))
    except tk.TclError:
        pass


def _build_help_and_recovery(self: Any, outer: Any) -> None:
    support = ttk.LabelFrame(outer, text="Help & recovery", padding=14)
    support.pack(fill="x", pady=(0, 12))
    support.columnconfigure(0, weight=1)
    support.columnconfigure(1, weight=1)

    ttk.Label(support, text="Restore settings", style="Section.TLabel").grid(
        row=0, column=0, sticky="w", padx=(0, 12), pady=(0, 5)
    )
    ttk.Label(support, text="Keyboard connection", style="Section.TLabel").grid(
        row=0, column=1, sticky="w", pady=(0, 5)
    )

    ttk.Button(
        support,
        text="Restore recommended settings",
        command=self._reset_defaults,
    ).grid(row=1, column=0, sticky="w", padx=(0, 12))

    self.input_backend_combo = ttk.Combobox(
        support,
        textvariable=self.input_backend_var,
        values=list(self._modern_module.INPUT_BACKEND_LABELS),
        state="readonly",
    )
    self.input_backend_combo.grid(row=1, column=1, sticky="ew")
    self.input_backend_combo.bind("<<ComboboxSelected>>", lambda _event: self._save_config())

    ttk.Label(
        support,
        text="Win32 scan code is recommended. Keep another method only if it works better on your PC.",
        style="Hint.TLabel",
        wraplength=290,
        justify="left",
    ).grid(row=2, column=1, sticky="w", pady=(6, 0))


def _modern_build_ui(self: Any) -> None:
    self._apply_system_theme(force=True)
    _apply_simple_styles(self)

    self.geometry("780x700")
    self.minsize(560, 500)

    shell = ttk.Frame(self)
    shell.pack(fill="both", expand=True)

    canvas_bg = self._style.lookup("TFrame", "background") or self.cget("background")
    self._scroll_canvas = tk.Canvas(
        shell,
        borderwidth=0,
        highlightthickness=0,
        background=canvas_bg,
    )
    scrollbar = ttk.Scrollbar(shell, orient="vertical", command=self._scroll_canvas.yview)
    self._scroll_canvas.configure(yscrollcommand=scrollbar.set)
    self._scroll_canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    outer = ttk.Frame(self._scroll_canvas, padding=(20, 18, 16, 22))
    self._scroll_window = self._scroll_canvas.create_window((0, 0), window=outer, anchor="nw")

    outer.bind("<Configure>", lambda _event: _refresh_scroll_region(self))
    self._scroll_canvas.bind(
        "<Configure>",
        lambda event: self._scroll_canvas.itemconfigure(self._scroll_window, width=event.width),
    )
    self.bind("<MouseWheel>", lambda event: _scroll_mousewheel(self, event), add="+")
    self.bind("<Button-4>", lambda event: _scroll_mousewheel(self, event), add="+")
    self.bind("<Button-5>", lambda event: _scroll_mousewheel(self, event), add="+")

    header = ttk.Frame(outer)
    header.pack(fill="x", pady=(0, 18))
    ttk.Label(header, text="BPSR MIDI Lite", style="Hero.TLabel").pack(anchor="w")
    ttk.Label(
        header,
        text="Choose instrument → category → song → Play. Song fitting is automatic.",
        style="Hint.TLabel",
        wraplength=620,
        justify="left",
    ).pack(anchor="w", pady=(3, 0))

    setup = ttk.LabelFrame(outer, text="1  Instrument", padding=14)
    setup.pack(fill="x", pady=(0, 12))
    setup.columnconfigure(0, weight=1, uniform="setup")
    setup.columnconfigure(1, weight=1, uniform="setup")

    ttk.Label(setup, text="What are you playing?", style="Section.TLabel").grid(
        row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 5)
    )
    ttk.Label(setup, text="Which category have you unlocked?", style="Section.TLabel").grid(
        row=0, column=1, sticky="w", padx=(8, 0), pady=(0, 5)
    )

    self.instrument_combo = ttk.Combobox(
        setup,
        textvariable=self.instrument_var,
        values=list(self._modern_module.INSTRUMENT_LABELS),
        state="readonly",
    )
    self.instrument_combo.grid(row=1, column=0, sticky="ew", padx=(0, 8))
    self.instrument_combo.bind("<<ComboboxSelected>>", lambda _event: self._instrument_changed())

    self.profile_combo = ttk.Combobox(
        setup,
        textvariable=self.profile_var,
        values=list(self._modern_module.profile_labels_for("keyboard")),
        state="readonly",
    )
    self.profile_combo.grid(row=1, column=1, sticky="ew", padx=(8, 0))
    self.profile_combo.bind("<<ComboboxSelected>>", lambda _event: self._profile_changed())

    ttk.Label(
        setup,
        textvariable=self.profile_summary_var,
        style="Hint.TLabel",
        wraplength=620,
        justify="left",
    ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))

    songs = ttk.LabelFrame(outer, text="2  Song", padding=14)
    songs.pack(fill="x", pady=(0, 12))
    songs.columnconfigure(0, weight=1)

    self.midi_combo = ttk.Combobox(
        songs,
        textvariable=self.midi_display_var,
        state="readonly",
        values=(),
    )
    self.midi_combo.grid(row=0, column=0, sticky="ew")
    self.midi_combo.bind("<<ComboboxSelected>>", lambda _event: self._midi_selected())
    ttk.Button(songs, text="Open folder", command=self._open_midi_folder).grid(
        row=0, column=1, padx=(8, 0)
    )

    speed_row = ttk.Frame(songs)
    speed_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
    speed_row.columnconfigure(3, weight=1)
    ttk.Label(speed_row, text="Song speed", style="Section.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Spinbox(
        speed_row,
        from_=25,
        to=200,
        increment=5,
        textvariable=self.speed_var,
        width=6,
    ).grid(row=0, column=1, sticky="w", padx=(8, 4))
    ttk.Label(speed_row, text="%", style="Hint.TLabel").grid(row=0, column=2, sticky="w")
    ttk.Button(
        speed_row,
        text="Restore song speed to default 100%",
        command=lambda: self.speed_var.set(100),
    ).grid(row=0, column=3, sticky="e", padx=(12, 0))
    ttk.Label(
        speed_row,
        text="100% = original MIDI speed",
        style="Hint.TLabel",
    ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(5, 0))

    ttk.Label(
        songs,
        text=(
            "Open the song folder and copy .mid/.midi files there; the list refreshes automatically. "
            "Normal categories fit notes automatically. Raw MIDI keeps pitches unchanged and skips out-of-range notes."
        ),
        style="Hint.TLabel",
        wraplength=620,
        justify="left",
    ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

    self.analysis_frame = ttk.LabelFrame(outer, text="3  Song check", padding=14)
    self.analysis_frame.pack(fill="x", pady=(0, 12))
    self.suitability_label = ttk.Label(
        self.analysis_frame,
        textvariable=self.suitability_var,
        style="Ready.TLabel",
    )
    self.suitability_label.pack(anchor="w")
    ttk.Label(
        self.analysis_frame,
        textvariable=self.analysis_var,
        style="Hint.TLabel",
        wraplength=620,
        justify="left",
    ).pack(anchor="w", pady=(6, 0))

    play = ttk.LabelFrame(outer, text="4  Play", padding=14)
    play.pack(fill="x", pady=(0, 12))

    ttk.Label(play, textvariable=self.notice_var, wraplength=620, justify="left").pack(anchor="w", pady=(0, 12))

    countdown = ttk.Frame(play)
    countdown.pack(fill="x", pady=(0, 10))
    ttk.Label(countdown, text="Countdown", style="Section.TLabel").pack(side="left")
    ttk.Spinbox(
        countdown,
        from_=0,
        to=30,
        increment=0.5,
        textvariable=self.start_delay_var,
        width=7,
    ).pack(side="left", padx=(8, 4))
    ttk.Label(countdown, text="seconds to switch back to BPSR", style="Hint.TLabel").pack(side="left")

    actions = ttk.Frame(play)
    actions.pack(fill="x")
    actions.columnconfigure(0, weight=1)
    actions.columnconfigure(1, weight=0)

    self.start_button = ttk.Button(
        actions,
        text="Play in BPSR",
        style="Primary.TButton",
        command=self._start,
        state="disabled",
    )
    self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    self.stop_button = ttk.Button(
        actions,
        text="Stop  (F10)",
        style="Stop.TButton",
        command=self._stop,
        state="disabled",
    )
    self.stop_button.grid(row=0, column=1)

    self.progress = ttk.Progressbar(play, maximum=1.0, mode="determinate")
    self.progress.pack(fill="x", pady=(14, 8))
    ttk.Label(play, textvariable=self.status_var, wraplength=620, justify="left").pack(anchor="w")

    _build_help_and_recovery(self, outer)

    ttk.Label(
        outer,
        text="The app stays open during playback. F10 always stops playback and releases held keys.",
        style="Hint.TLabel",
        wraplength=620,
        justify="left",
    ).pack(anchor="w")

    self.after(1500, lambda: _poll_song_library(self))


def _modern_apply_system_theme(self: Any, force: bool = False) -> None:
    self._modern_original_apply_system_theme(force=force)
    if hasattr(self, "_scroll_canvas"):
        background = self._style.lookup("TFrame", "background") or self.cget("background")
        try:
            self._scroll_canvas.configure(background=background)
        except tk.TclError:
            pass


def _modern_apply_profile_ui(self: Any, schedule: bool = True) -> None:
    app_module = self._modern_module
    instrument = self._instrument_code()
    profile_code = self._profile_code()
    self._active_instrument_code = instrument
    self._active_profile_code = profile_code
    self._profile_by_instrument[instrument] = profile_code

    profile = app_module.get_fixed_profile(instrument, profile_code)
    self.profile_summary_var.set(profile.summary)

    if instrument == "bass":
        if profile.unlock_tier == "tier1":
            notice = "Open Bass in its normal Default mode. Press Play, then switch back to BPSR during the countdown."
        else:
            notice = (
                "Open Bass in its normal Default mode. The app switches High Octave when needed and returns to Default afterward. "
                "It never uses < or >."
            )
    else:
        notice = (
            f"Open {instrument.title()} on the middle page in the normal octave. The app uses Ctrl/Shift when needed, "
            "returns to normal afterward, and never uses < or >."
        )

    if profile_code == "raw":
        notice += " Raw MIDI does not remap pitches; out-of-range notes are skipped."

    self.notice_var.set(notice)
    if schedule:
        self._schedule_analysis()


def _preserve_song_speed(self: Any, action: Callable[[], None]) -> None:
    try:
        speed = max(25, min(200, int(self.speed_var.get())))
    except (TypeError, ValueError, tk.TclError):
        speed = 100

    action()

    if int(self.speed_var.get()) != speed:
        self._suspend_auto_analysis = True
        try:
            self.speed_var.set(speed)
        finally:
            self._suspend_auto_analysis = False
        self._schedule_analysis()
        self._save_config()


def _modern_profile_changed(self: Any) -> None:
    _preserve_song_speed(self, self._modern_original_profile_changed)


def _modern_instrument_changed(self: Any) -> None:
    _preserve_song_speed(self, self._modern_original_instrument_changed)


def _modern_save_config(self: Any) -> None:
    self._modern_original_save_config()
    if self._suspend_auto_analysis:
        return
    try:
        path = self._config_path()
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(data, dict):
            data = {}
        data["song_speed_percent"] = max(25, min(200, int(self.speed_var.get())))
        data.pop("minimize", None)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except (OSError, ValueError, TypeError, json.JSONDecodeError, tk.TclError):
        pass


def _modern_load_config(self: Any) -> None:
    self._modern_original_load_config()
    try:
        path = self._config_path()
        if not path.exists() and self._legacy_config_path().exists():
            path = self._legacy_config_path()
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(data, dict):
            return
        speed = int(data.get("song_speed_percent", 100))
        self.speed_var.set(max(25, min(200, speed)))
    except (OSError, ValueError, TypeError, json.JSONDecodeError, tk.TclError):
        self.speed_var.set(100)


def _friendly_analyze(self: Any) -> None:
    self._modern_original_analyze()

    if self.current_plan is None:
        self.start_button.configure(state="disabled")
        if not self.file_var.get():
            self.suitability_var.set("Add a MIDI song to begin")
            self.analysis_var.set("Open the song folder and copy in a .mid or .midi file.")
        return

    plan = self.current_plan

    # Product-level invariant: no selectable profile may use page buttons.
    # Block playback instead of silently violating the no-page product promise.
    if plan.page_switches or any(event.kind == "page" for event in plan.events):
        self.suitability_var.set("Playback blocked — unexpected page change")
        self.suitability_label.configure(style="Danger.TLabel")
        self.analysis_var.set("This profile should never press < or >. Playback was blocked so the instrument cannot desync.")
        self.start_button.configure(state="disabled")
        return

    suitability = self.current_suitability
    code = getattr(suitability, "code", "good")
    if code == "good":
        self.suitability_var.set("Ready to play")
        self.suitability_label.configure(style="Good.TLabel")
    elif code == "busy":
        self.suitability_var.set("Playable, but this song is busy")
        self.suitability_label.configure(style="Warning.TLabel")
    else:
        self.suitability_var.set("This song may sound crowded")
        self.suitability_label.configure(style="Danger.TLabel")

    minutes, seconds = divmod(max(0, round(plan.duration)), 60)
    duration = f"{minutes}:{seconds:02d}" if minutes else f"{seconds}s"

    remapped = plan.remapped_notes
    metrics = (
        f"Remapped: {remapped:,} • Skipped: {plan.skipped_notes:,} • "
        f"Filtered/simplified: {plan.filtered_notes:,} • Peak keys: {plan.max_simultaneous_keys:,}"
    )
    if plan.retrigger_merged_notes or plan.retrigger_dropped_notes:
        metrics += (
            f" • Close repeats merged: {plan.retrigger_merged_notes:,}"
            f" / dropped: {plan.retrigger_dropped_notes:,}"
        )

    if self._profile_code() == "raw":
        if plan.skipped_notes:
            explanation = "Raw MIDI keeps every in-range pitch unchanged; out-of-range notes are skipped."
        else:
            explanation = "Raw MIDI: this song already fits the instrument range, so every pitch stays unchanged."
    elif plan.transposed_semitones:
        direction = "+" if plan.transposed_semitones > 0 else ""
        explanation = (
            f"Whole-song shift: {direction}{plan.transposed_semitones} semitones to fit this category. "
            "This keeps the song intervals together; any remaining local fitting is minimized."
        )
    elif remapped:
        explanation = "Remapped notes were moved into the range available for your selected category."
    else:
        explanation = "This song already fits the selected category without pitch remapping."

    self.analysis_var.set(
        f"{duration} • {plan.note_count:,} playable notes\n"
        f"{metrics}\n"
        f"{explanation}"
    )
    if not self.player.is_playing:
        self.start_button.configure(state="normal")


def _friendly_reload(self: Any, analyze: bool = True, preferred_display: str | None = None) -> None:
    self._modern_original_reload(analyze=analyze, preferred_display=preferred_display)
    if not self._midi_lookup:
        self.start_button.configure(state="disabled")
        self.suitability_var.set("No songs yet")
        self.analysis_var.set("Open the song folder and copy in a .mid or .midi file. The list refreshes automatically.")
        self.status_var.set("Your song library is empty.")


def install_modern_ui(app_module: Any) -> None:
    """Install the single-page UI while preserving the proven MIDI engine."""
    app_class = app_module.App

    app_class._modern_module = app_module
    app_class._modern_original_apply_system_theme = app_class._apply_system_theme
    app_class._modern_original_analyze = app_class._analyze
    app_class._modern_original_reload = app_class._reload_midi_library
    app_class._modern_original_profile_changed = app_class._profile_changed
    app_class._modern_original_instrument_changed = app_class._instrument_changed
    app_class._modern_original_save_config = app_class._save_config
    app_class._modern_original_load_config = app_class._load_config

    app_class._apply_system_theme = _modern_apply_system_theme
    app_class._build_ui = _modern_build_ui
    app_class._apply_profile_ui = _modern_apply_profile_ui
    app_class._profile_changed = _modern_profile_changed
    app_class._instrument_changed = _modern_instrument_changed
    app_class._save_config = _modern_save_config
    app_class._load_config = _modern_load_config
    app_class._analyze = _friendly_analyze
    app_class._reload_midi_library = _friendly_reload
