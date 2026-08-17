from __future__ import annotations

import json
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable


"""Single-window beginner UI for BPSR MIDI Lite.

Users choose an instrument, the matching in-game unlock category, a song, and a
song speed. Mapping, chord limits, octave timing, page timing, note-length
compensation and other technical choices are automatic. Raw MIDI is exposed as
an explicit profile for users who want exact pitches with no remapping.
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
        self._troubleshooting_button.configure(text="Troubleshooting ▾")
    else:
        self._troubleshooting_frame.pack(fill="x", pady=(10, 0))
        self._troubleshooting_visible = True
        self._troubleshooting_button.configure(text="Troubleshooting ▴")
        if self.winfo_height() < 830:
            self.geometry("800x830")


def _set_settings_visible(self: Any, visible: bool) -> None:
    self._settings_visible = bool(visible)
    if visible:
        self._settings_frame.pack(fill="x", pady=(0, 12), before=self.analysis_frame)
        self._settings_button.configure(text="Hide settings")
        if self.winfo_height() < 780:
            self.geometry("800x780")
    else:
        self._settings_frame.pack_forget()
        self._settings_button.configure(text="More settings")
        if self._troubleshooting_visible:
            self._troubleshooting_frame.pack_forget()
            self._troubleshooting_visible = False
            self._troubleshooting_button.configure(text="Troubleshooting ▾")
        self.geometry("760x690")


def _toggle_settings(self: Any) -> None:
    _set_settings_visible(self, not self._settings_visible)


def _show_settings(self: Any) -> None:
    _set_settings_visible(self, True)


def _hide_settings(self: Any) -> None:
    _set_settings_visible(self, False)


def _build_inline_settings(self: Any, outer: Any) -> None:
    self._settings_visible = False
    self._settings_frame = ttk.LabelFrame(outer, text="Settings", padding=12)
    settings = self._settings_frame

    general = ttk.Frame(settings)
    general.pack(fill="x")
    ttk.Label(general, text="Countdown").pack(side="left")
    ttk.Spinbox(
        general,
        from_=0,
        to=30,
        increment=0.5,
        textvariable=self.start_delay_var,
        width=7,
    ).pack(side="left", padx=(8, 4))
    ttk.Label(general, text="seconds", style="Hint.TLabel").pack(side="left")

    library = ttk.Frame(settings)
    library.pack(fill="x", pady=(10, 0))
    ttk.Button(library, text="Open songs folder", command=self._open_midi_folder).pack(side="left")
    ttk.Button(library, text="Restore recommended settings", command=self._reset_defaults).pack(side="left", padx=(8, 0))

    self._troubleshooting_button = ttk.Button(
        settings,
        text="Troubleshooting ▾",
        command=self._toggle_troubleshooting,
    )
    self._troubleshooting_button.pack(anchor="w", pady=(12, 0))

    self._troubleshooting_visible = False
    self._troubleshooting_frame = ttk.LabelFrame(
        settings,
        text="Only change this if keyboard input is not working",
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
        text="Choose your instrument category, choose a song, press Play.",
        style="Hint.TLabel",
    ).pack(anchor="w", pady=(3, 0))
    self._settings_button = ttk.Button(header, text="More settings", command=self._toggle_settings)
    self._settings_button.pack(side="right", anchor="n")

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
    ttk.Label(right, text="Which category have you unlocked?", style="Section.TLabel").pack(anchor="w", pady=(0, 5))
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

    speed_row = ttk.Frame(songs)
    speed_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))
    ttk.Label(speed_row, text="Song speed", style="Section.TLabel").pack(side="left")
    ttk.Spinbox(
        speed_row,
        from_=25,
        to=200,
        increment=5,
        textvariable=self.speed_var,
        width=6,
    ).pack(side="left", padx=(8, 4))
    ttk.Label(speed_row, text="%", style="Hint.TLabel").pack(side="left")
    ttk.Label(speed_row, text="100% = original MIDI speed", style="Hint.TLabel").pack(side="left", padx=(12, 0))
    ttk.Button(speed_row, text="Reset to 100%", command=lambda: self.speed_var.set(100)).pack(side="right")

    ttk.Label(
        songs,
        text="Normal categories fit notes automatically. Raw MIDI keeps pitches unchanged and skips notes the instrument cannot play.",
        style="Hint.TLabel",
        wraplength=680,
        justify="left",
    ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))

    self._build_inline_settings(outer)

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

    ttk.Label(play, textvariable=self.notice_var, wraplength=680, justify="left").pack(anchor="w", pady=(0, 12))

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
    ttk.Label(play, textvariable=self.status_var, wraplength=680, justify="left").pack(anchor="w")

    ttk.Label(
        outer,
        text="The app stays open during playback. F10 always stops playback and releases held keys.",
        style="Hint.TLabel",
    ).pack(anchor="w", pady=(12, 0))


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
            notice = "Open Bass in its normal Default mode. Press Play, then click back into BPSR during the countdown."
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
            self.analysis_var.set("The app will check and fit the song automatically.")
        return

    plan = self.current_plan

    # Product-level invariant: no selectable v2.3 profile may use page buttons.
    # Block playback rather than silently violating that promise if a future
    # engine/profile regression produces a page transition.
    if plan.page_switches:
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

    if self._profile_code() == "raw":
        if plan.skipped_notes:
            protection = f"Raw mode: {plan.skipped_notes:,} out-of-range note(s) will be skipped; pitches are not remapped."
        else:
            protection = "Raw mode: this MIDI already fits the instrument range, so no pitches are remapped."
    else:
        changed = plan.folded_notes + plan.skipped_notes + plan.filtered_notes
        protection = (
            "Some notes were fitted to your unlocked range automatically."
            if changed
            else "The song already fits this unlocked range well."
        )

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
    """Install the category-first UI while preserving the proven MIDI engine."""
    app_class = app_module.App

    app_class._modern_module = app_module
    app_class._modern_original_analyze = app_class._analyze
    app_class._modern_original_reload = app_class._reload_midi_library
    app_class._modern_original_profile_changed = app_class._profile_changed
    app_class._modern_original_instrument_changed = app_class._instrument_changed
    app_class._modern_original_save_config = app_class._save_config
    app_class._modern_original_load_config = app_class._load_config

    app_class._build_ui = _modern_build_ui
    app_class._apply_profile_ui = _modern_apply_profile_ui
    app_class._add_midi_files = _add_midi_files
    app_class._toggle_settings = _toggle_settings
    app_class._show_settings = _show_settings
    app_class._hide_settings = _hide_settings
    app_class._toggle_troubleshooting = _toggle_troubleshooting
    app_class._build_inline_settings = _build_inline_settings
    app_class._profile_changed = _modern_profile_changed
    app_class._instrument_changed = _modern_instrument_changed
    app_class._save_config = _modern_save_config
    app_class._load_config = _modern_load_config
    app_class._analyze = _friendly_analyze
    app_class._reload_midi_library = _friendly_reload
