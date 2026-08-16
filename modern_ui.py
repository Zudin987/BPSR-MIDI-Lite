from __future__ import annotations

import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any


"""Beginner-first UI for BPSR MIDI Lite.

The MIDI planner, input sender, profile rules, timing compensation and player are
intentionally left in their existing modules. This file only changes how users
reach those capabilities: the common path is Instrument -> Range -> Song -> Play.
Advanced controls remain available from Settings without competing with the main
flow.
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


def _field(parent: Any, label: str, variable: tk.Variable, values: list[str], command: Any) -> ttk.Combobox:
    box = ttk.Frame(parent)
    box.pack(fill="x", pady=(0, 12))
    ttk.Label(box, text=label, style="Section.TLabel").pack(anchor="w", pady=(0, 5))
    combo = ttk.Combobox(box, textvariable=variable, values=values, state="readonly")
    combo.pack(fill="x")
    combo.bind("<<ComboboxSelected>>", command)
    return combo


def _unique_target(folder: Path, source: Path) -> Path:
    target = folder / source.name
    if not target.exists():
        return target
    try:
        if target.resolve() == source.resolve():
            return target
    except OSError:
        pass

    stem = source.stem
    suffix = source.suffix
    number = 2
    while True:
        candidate = folder / f"{stem} ({number}){suffix}"
        if not candidate.exists():
            return candidate
        number += 1


def _add_midi_files(self: Any) -> None:
    files = filedialog.askopenfilenames(
        parent=self,
        title="Add MIDI songs",
        filetypes=[("MIDI files", "*.mid *.midi"), ("All files", "*.*")],
    )
    if not files:
        return

    folder = Path(self.midi_folder_var.get())
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        messagebox.showerror(self._modern_module.APP_NAME, f"Could not open the song library:\n{exc}")
        return

    added: list[Path] = []
    for raw in files:
        source = Path(raw)
        if source.suffix.casefold() not in self._modern_module.MIDI_EXTENSIONS:
            continue
        try:
            target = _unique_target(folder, source)
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
            added.append(target)
        except OSError as exc:
            messagebox.showerror(
                self._modern_module.APP_NAME,
                f"Could not add {source.name}:\n{exc}",
            )
            return

    if not added:
        self.status_var.set("No MIDI files were added.")
        return

    preferred = added[-1].relative_to(folder).as_posix()
    self._reload_midi_library(analyze=False, preferred_display=preferred)
    self._midi_selected()
    count = len(added)
    self.status_var.set(f"Added {count} song{'s' if count != 1 else ''}. Checking the selected song…")


def _toggle_troubleshooting(self: Any) -> None:
    if self._troubleshooting_visible:
        self._troubleshooting_frame.pack_forget()
        self._troubleshooting_visible = False
        self._troubleshooting_button.configure(text="Troubleshooting")
    else:
        self._troubleshooting_frame.pack(fill="x", pady=(14, 0))
        self._troubleshooting_visible = True
        self._troubleshooting_button.configure(text="Hide troubleshooting")


def _show_settings(self: Any) -> None:
    if self._profile_code() == "custom":
        self.custom_settings_frame.pack(fill="x", pady=(14, 0))
    else:
        self.custom_settings_frame.pack_forget()
    self._settings_window.deiconify()
    self._settings_window.lift()
    self._settings_window.focus_force()


def _hide_settings(self: Any) -> None:
    self._settings_window.withdraw()


def _build_settings_window(self: Any) -> None:
    win = tk.Toplevel(self)
    self._settings_window = win
    win.title("Settings — BPSR MIDI Lite")
    win.geometry("610x710")
    win.minsize(560, 560)
    win.transient(self)
    win.protocol("WM_DELETE_WINDOW", lambda: self._hide_settings())

    outer = ttk.Frame(win, padding=18)
    outer.pack(fill="both", expand=True)

    header = ttk.Frame(outer)
    header.pack(fill="x", pady=(0, 16))
    ttk.Label(header, text="Settings", style="Title.TLabel").pack(side="left")
    ttk.Button(header, text="Done", command=self._hide_settings).pack(side="right")

    ttk.Label(
        outer,
        text="You normally do not need to change anything here. The recommended choices are already selected.",
        style="Hint.TLabel",
        wraplength=550,
        justify="left",
    ).pack(anchor="w", pady=(0, 14))

    playback = ttk.LabelFrame(outer, text="Before the song starts", padding=12)
    playback.pack(fill="x")
    row = ttk.Frame(playback)
    row.pack(fill="x")
    ttk.Label(row, text="Countdown").pack(side="left")
    ttk.Spinbox(
        row,
        from_=0,
        to=30,
        increment=0.5,
        textvariable=self.start_delay_var,
        width=7,
    ).pack(side="left", padx=(10, 5))
    ttk.Label(row, text="seconds", style="Hint.TLabel").pack(side="left")
    ttk.Checkbutton(
        playback,
        text="Minimize this app after I press Play",
        variable=self.minimize_var,
        command=self._save_config,
    ).pack(anchor="w", pady=(10, 0))

    self.custom_settings_frame = ttk.LabelFrame(
        outer,
        text="Advanced song fitting",
        padding=12,
    )
    self._build_custom_settings(self.custom_settings_frame)

    self._troubleshooting_button = ttk.Button(
        outer,
        text="Troubleshooting",
        command=self._toggle_troubleshooting,
    )
    self._troubleshooting_button.pack(anchor="w", pady=(16, 0))

    self._troubleshooting_visible = False
    self._troubleshooting_frame = ttk.LabelFrame(
        outer,
        text="Only change this if input is not working",
        padding=12,
    )
    trouble = self._troubleshooting_frame

    ttk.Label(trouble, text="Keyboard connection").pack(anchor="w")
    self.input_backend_combo = ttk.Combobox(
        trouble,
        textvariable=self.input_backend_var,
        values=list(self._modern_module.INPUT_BACKEND_LABELS),
        state="readonly",
    )
    self.input_backend_combo.pack(fill="x", pady=(5, 10))
    self.input_backend_combo.bind("<<ComboboxSelected>>", lambda _event: self._save_config())

    buttons = ttk.Frame(trouble)
    buttons.pack(fill="x")
    self.test_button = ttk.Button(buttons, text="Test keyboard input", command=self._test_input)
    self.test_button.pack(side="left")
    ttk.Button(buttons, text="Copy support info", command=self._copy_diagnostics).pack(side="left", padx=(8, 0))

    library = ttk.LabelFrame(outer, text="Song library", padding=12)
    library.pack(fill="x", pady=(16, 0))
    ttk.Button(library, text="Open songs folder", command=self._open_midi_folder).pack(side="left")
    ttk.Button(library, text="Restore recommended settings", command=self._reset_defaults).pack(side="left", padx=(8, 0))

    win.withdraw()


def _modern_build_custom_settings(self: Any, settings: Any) -> None:
    ttk.Label(
        settings,
        text=(
            "These controls are only for unusual MIDI files or the experimental full instrument range. "
            "If you are unsure, use a normal unlocked-range option on the main screen."
        ),
        style="Hint.TLabel",
        wraplength=520,
        justify="left",
    ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))

    settings.columnconfigure(1, weight=1)
    settings.columnconfigure(3, weight=1)

    ttk.Label(settings, text="Playback style").grid(row=1, column=0, sticky="w", pady=4)
    self.mode_combo = ttk.Combobox(
        settings,
        textvariable=self.mode_var,
        values=list(self._modern_module.MODE_LABELS),
        state="readonly",
        width=34,
    )
    self.mode_combo.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=4)

    ttk.Label(settings, text="Unlocked notes").grid(row=2, column=0, sticky="w", pady=4)
    self.unlock_combo = ttk.Combobox(
        settings,
        textvariable=self.unlock_var,
        values=list(self._modern_module.UNLOCK_LABELS_BY_INSTRUMENT["keyboard"]),
        state="readonly",
        width=26,
    )
    self.unlock_combo.grid(row=2, column=1, sticky="ew", padx=(8, 12), pady=4)

    ttk.Label(settings, text="Page-change wait").grid(row=2, column=2, sticky="w", pady=4)
    self.page_delay_spin = ttk.Spinbox(
        settings,
        from_=40,
        to=1000,
        increment=10,
        textvariable=self.page_delay_var,
        width=8,
    )
    self.page_delay_spin.grid(row=2, column=3, sticky="w", padx=(8, 0), pady=4)

    ttk.Label(settings, text="Fit notes that are outside the range").grid(row=3, column=0, sticky="w", pady=4)
    self.mapping_combo = ttk.Combobox(
        settings,
        textvariable=self.mapping_var,
        values=list(self._modern_module.MAPPING_LABELS),
        state="readonly",
    )
    self.mapping_combo.grid(row=3, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=4)

    ttk.Label(settings, text="Keep from large chords").grid(row=4, column=0, sticky="w", pady=4)
    self.chord_combo = ttk.Combobox(
        settings,
        textvariable=self.chord_var,
        values=list(self._modern_module.STANDARD_CHORD_LABELS),
        state="readonly",
        width=28,
    )
    self.chord_combo.grid(row=4, column=1, sticky="ew", padx=(8, 12), pady=4)

    ttk.Label(settings, text="Octave-change lead").grid(row=4, column=2, sticky="w", pady=4)
    ttk.Spinbox(
        settings,
        from_=10,
        to=500,
        increment=5,
        textvariable=self.modifier_lead_var,
        width=8,
    ).grid(row=4, column=3, sticky="w", padx=(8, 0), pady=4)

    timing = ttk.Frame(settings)
    timing.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(10, 0))
    for column in range(3):
        timing.columnconfigure(column, weight=1)

    for column, (label, variable, low, high, suffix) in enumerate(
        (
            ("Song speed", self.speed_var, 25, 200, "%"),
            ("Held-note length", self.length_var, 50, 300, "%"),
            ("Shortest note", self.minimum_note_var, 20, 1000, "ms"),
        )
    ):
        cell = ttk.Frame(timing)
        cell.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
        ttk.Label(cell, text=label, style="Hint.TLabel").pack(anchor="w")
        value_row = ttk.Frame(cell)
        value_row.pack(anchor="w", pady=(4, 0))
        ttk.Spinbox(value_row, from_=low, to=high, textvariable=variable, width=7).pack(side="left")
        ttk.Label(value_row, text=suffix, style="Hint.TLabel").pack(side="left", padx=(4, 0))

    options = ttk.Frame(settings)
    options.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(12, 0))
    ttk.Checkbutton(
        options,
        text="Ignore drum/percussion track",
        variable=self.percussion_var,
    ).pack(anchor="w")
    ttk.Checkbutton(
        options,
        text="Use sustain-pedal events from the MIDI",
        variable=self.pedal_var,
    ).pack(anchor="w", pady=(5, 0))


def _modern_build_ui(self: Any) -> None:
    self._apply_system_theme(force=True)
    _apply_simple_styles(self)

    self.geometry("760x690")
    self.minsize(700, 620)

    outer = ttk.Frame(self, padding=20)
    outer.pack(fill="both", expand=True)

    header = ttk.Frame(outer)
    header.pack(fill="x", pady=(0, 18))
    title = ttk.Frame(header)
    title.pack(side="left", fill="x", expand=True)
    ttk.Label(title, text="BPSR MIDI Lite", style="Hero.TLabel").pack(anchor="w")
    ttk.Label(
        title,
        text="Choose a song. Choose your instrument. Press Play.",
        style="Hint.TLabel",
    ).pack(anchor="w", pady=(3, 0))
    ttk.Button(header, text="Settings", command=self._show_settings).pack(side="right", anchor="n")

    setup = ttk.LabelFrame(outer, text="1  Instrument", padding=14)
    setup.pack(fill="x", pady=(0, 12))
    setup.columnconfigure(0, weight=1)
    setup.columnconfigure(1, weight=1)

    left = ttk.Frame(setup)
    left.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    ttk.Label(left, text="What are you playing?", style="Section.TLabel").pack(anchor="w", pady=(0, 5))
    self.instrument_combo = ttk.Combobox(
        left,
        textvariable=self.instrument_var,
        values=list(self._modern_module.INSTRUMENT_LABELS),
        state="readonly",
    )
    self.instrument_combo.pack(fill="x")
    self.instrument_combo.bind("<<ComboboxSelected>>", lambda _event: self._instrument_changed())

    right = ttk.Frame(setup)
    right.grid(row=0, column=1, sticky="ew", padx=(8, 0))
    ttk.Label(right, text="How much have you unlocked?", style="Section.TLabel").pack(anchor="w", pady=(0, 5))
    self.profile_combo = ttk.Combobox(
        right,
        textvariable=self.profile_var,
        values=list(self._modern_module.profile_labels_for("keyboard")),
        state="readonly",
    )
    self.profile_combo.pack(fill="x")
    self.profile_combo.bind("<<ComboboxSelected>>", lambda _event: self._profile_changed())

    ttk.Label(
        setup,
        textvariable=self.profile_summary_var,
        style="Hint.TLabel",
        wraplength=680,
        justify="left",
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))

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
    ttk.Button(songs, text="Add MIDI…", command=self._add_midi_files).grid(row=0, column=1, padx=(8, 0))
    ttk.Button(songs, text="Open folder", command=self._open_midi_folder).grid(row=0, column=2, padx=(8, 0))

    ttk.Label(
        songs,
        text="Add a .mid or .midi file once. It stays in your song list automatically.",
        style="Hint.TLabel",
    ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

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
        wraplength=680,
        justify="left",
    ).pack(anchor="w", pady=(6, 0))

    play = ttk.LabelFrame(outer, text="4  Play", padding=14)
    play.pack(fill="both", expand=True)

    ttk.Label(
        play,
        textvariable=self.notice_var,
        wraplength=680,
        justify="left",
    ).pack(anchor="w", pady=(0, 12))

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
    ttk.Label(
        play,
        textvariable=self.status_var,
        wraplength=680,
        justify="left",
    ).pack(anchor="w")

    ttk.Label(
        outer,
        text="F10 always stops playback and releases held keys.",
        style="Hint.TLabel",
    ).pack(anchor="w", pady=(12, 0))

    self._build_settings_window()


def _modern_apply_profile_ui(self: Any, schedule: bool = True) -> None:
    app_module = self._modern_module
    instrument = self._instrument_code()
    profile_code = self._profile_code()
    self._active_instrument_code = instrument
    self._active_profile_code = profile_code
    self._profile_by_instrument[instrument] = profile_code

    self.unlock_combo.configure(values=list(self._unlock_labels()))
    self.chord_combo.configure(values=list(self._chord_labels()))

    if profile_code == "custom":
        self.profile_summary_var.set(
            "Advanced setup. Recommended only when you need the experimental full range or unusual MIDI fitting."
        )
        self.custom_settings_frame.pack(fill="x", pady=(14, 0))
        self._refresh_custom_mode_choices()
    else:
        profile = app_module.get_fixed_profile(instrument, profile_code)
        self.profile_summary_var.set(profile.summary)
        self.custom_settings_frame.pack_forget()

    mode = self._mode_code()
    tier = self._unlock_code()
    unlock = app_module.get_unlock_profile(tier, instrument)

    if instrument == "bass":
        if tier == "tier2":
            notice = (
                "Open Bass in its normal starting mode. Press Play, then click back into BPSR. "
                "The app handles the High Octave switch automatically."
            )
        else:
            notice = "Open Bass in its normal starting mode. Press Play, then click back into BPSR."
    elif mode == "full" and tier == "tier4":
        notice = (
            f"Open {instrument.title()} on the middle page with the normal octave. Press Play, then click back into BPSR. "
            "Automatic page changes are enabled for this advanced range."
        )
    else:
        notice = (
            f"Open {instrument.title()} on the middle page with the normal octave. Press Play, then click back into BPSR."
        )

    self.notice_var.set(notice)
    if schedule:
        self._schedule_analysis()


def _friendly_analyze(self: Any) -> None:
    self._modern_original_analyze()

    if self.current_plan is None:
        self.start_button.configure(state="disabled")
        if not self.file_var.get():
            self.suitability_var.set("Add a MIDI song to begin")
            self.analysis_var.set("The app will check and fit the song automatically.")
        return

    plan = self.current_plan
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
    changed = plan.folded_notes + plan.skipped_notes + plan.filtered_notes
    if plan.page_switches:
        protection = "Automatic page changes are needed; timing protection is already included."
    elif changed:
        protection = "Some notes were fitted to your instrument automatically."
    else:
        protection = "The song already fits this instrument range well."

    self.analysis_var.set(f"{duration} • {plan.note_count:,} playable notes. {protection}")
    if not self.player.is_playing:
        self.start_button.configure(state="normal")


def _friendly_reload(self: Any, analyze: bool = True, preferred_display: str | None = None) -> None:
    self._modern_original_reload(analyze=analyze, preferred_display=preferred_display)
    if not self._midi_lookup:
        self.start_button.configure(state="disabled")
        self.suitability_var.set("No songs yet")
        self.analysis_var.set("Click Add MIDI… and choose a .mid or .midi file.")
        self.status_var.set("Your song library is empty.")


def install_modern_ui(app_module: Any) -> None:
    """Install the radical-simplification UI without changing MIDI behavior."""
    app_class = app_module.App

    app_class._modern_module = app_module
    app_class._modern_original_analyze = app_class._analyze
    app_class._modern_original_reload = app_class._reload_midi_library

    app_class._build_ui = _modern_build_ui
    app_class._build_custom_settings = _modern_build_custom_settings
    app_class._apply_profile_ui = _modern_apply_profile_ui
    app_class._add_midi_files = _add_midi_files
    app_class._show_settings = _show_settings
    app_class._hide_settings = _hide_settings
    app_class._toggle_troubleshooting = _toggle_troubleshooting
    app_class._build_settings_window = _build_settings_window
    app_class._analyze = _friendly_analyze
    app_class._reload_midi_library = _friendly_reload
