from __future__ import annotations

import argparse
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from midi_engine import PlanOptions, build_plan, get_unlock_profile, midi_note_name
from player import MidiPlayer
from profiles import (
    FIXED_PROFILES,
    PROFILE_LABELS,
    PROFILE_LABELS_REVERSE,
    allowed_modes_for_unlock,
    get_fixed_profile,
)
from theme import apply_theme, system_prefers_dark_mode
from win_input import (
    BACKEND_NAMES,
    WindowsKeySender,
    f10_is_pressed,
    input_abi_diagnostics,
    is_running_as_admin,
)


APP_NAME = "BPSR MIDI Lite"
APP_VERSION = "0.5.1"
APP_AUTHOR = "MrEz"
CONFIG_FILE = "bpsr_midi_lite.json"

MODE_LABELS = {
    "Stable — smooth, never uses < or >": "stable",
    "Full range solo — preserve unlocked notes": "full",
    "Ensemble-safe — preserve the original timeline": "ensemble",
}
MODE_LABELS_REVERSE = {value: key for key, value in MODE_LABELS.items()}
UNLOCK_LABELS = {
    "Tier 1 — C3–B4": "tier1",
    "Tier 2 — C3–B6": "tier2",
    "Tier 3 — C2–B6 (no < / >)": "tier3",
    "Full range — A0–C8 (may use < / >)": "tier4",
}
UNLOCK_LABELS_REVERSE = {value: key for key, value in UNLOCK_LABELS.items()}
MAPPING_LABELS = {
    "Octave fold (recommended)": "octave",
    "Nearest playable note": "nearest",
    "Auto-transpose whole song, then fold": "transpose",
    "Skip notes that cannot be played": "skip",
}
MAPPING_LABELS_REVERSE = {value: key for key, value in MAPPING_LABELS.items()}
CHORD_LABELS = {
    "All notes": 0,
    "Melody only": 1,
    "Bass + melody": 2,
    "Bass + melody + 1 harmony": 3,
    "Bass + melody + 2 harmonies": 4,
}
CHORD_LABELS_REVERSE = {value: key for key, value in CHORD_LABELS.items()}

MIDI_EXTENSIONS = {".mid", ".midi"}

INPUT_BACKEND_LABELS = {
    "Win32 scan code (recommended)": "scan",
    "Pynput compatibility": "pynput",
    "Win32 virtual key": "virtual",
    "Legacy keybd_event": "legacy",
}
INPUT_BACKEND_LABELS_REVERSE = {value: key for key, value in INPUT_BACKEND_LABELS.items()}

CUSTOM_DEFAULTS: dict[str, object] = {
    "mode": "stable",
    "unlock_tier": "tier3",
    "mapping": "octave",
    "chord_limit": 0,
    "speed": 85,
    "length": 150,
    "minimum_note": 120,
    "page_delay": 220,
    "modifier_lead": 55,
    "pedal": False,
    "ignore_percussion": True,
}


def _application_directory() -> Path:
    """Return the folder containing the EXE, or this source file while developing."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _default_midi_folder() -> Path:
    """Create the fixed MIDI library beside the app, with a Documents fallback."""
    portable = _application_directory() / "MIDI"
    try:
        portable.mkdir(parents=True, exist_ok=True)
        probe = portable / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return portable
    except OSError:
        fallback = Path.home() / "Documents" / APP_NAME / "MIDI"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _natural_sort_key(text: str) -> list[object]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", text)]


def scan_midi_folder(folder: str | Path) -> list[Path]:
    """Return MIDI files recursively, sorted naturally by relative path."""
    root = Path(folder)
    if not root.exists() or not root.is_dir():
        return []
    files = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.casefold() in MIDI_EXTENSIONS
    ]
    return sorted(
        files,
        key=lambda path: _natural_sort_key(path.relative_to(root).as_posix()),
    )


def _duration_text(seconds: float) -> str:
    total = max(0, round(seconds))
    minutes, secs = divmod(total, 60)
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self._style = ttk.Style(self)
        self._dark_mode: bool | None = None
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("880x760")
        self.minsize(820, 690)

        self.player = MidiPlayer()
        self.current_plan = None
        self.ui_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._last_f10 = False
        self._input_test_running = False
        self._analysis_job: str | None = None
        self._suspend_auto_analysis = True
        self._active_profile_code = "tier3"
        self._custom_settings: dict[str, object] = dict(CUSTOM_DEFAULTS)

        self.file_var = tk.StringVar()
        self.midi_folder_var = tk.StringVar(value=str(_default_midi_folder()))
        self.midi_display_var = tk.StringVar()
        self._midi_lookup: dict[str, Path] = {}

        self.profile_var = tk.StringVar(value=PROFILE_LABELS_REVERSE["tier3"])
        self.mode_var = tk.StringVar(value=MODE_LABELS_REVERSE["stable"])
        self.unlock_var = tk.StringVar(value=UNLOCK_LABELS_REVERSE["tier3"])
        self.speed_var = tk.IntVar(value=85)
        self.length_var = tk.IntVar(value=150)
        self.minimum_note_var = tk.IntVar(value=120)
        self.page_delay_var = tk.IntVar(value=220)
        self.modifier_lead_var = tk.IntVar(value=55)
        self.start_delay_var = tk.DoubleVar(value=3.0)
        self.mapping_var = tk.StringVar(value=MAPPING_LABELS_REVERSE["octave"])
        self.chord_var = tk.StringVar(value=CHORD_LABELS_REVERSE[0])
        self.pedal_var = tk.BooleanVar(value=False)
        self.percussion_var = tk.BooleanVar(value=True)
        self.minimize_var = tk.BooleanVar(value=True)
        self.input_backend_var = tk.StringVar(value=INPUT_BACKEND_LABELS_REVERSE["scan"])

        self.status_var = tk.StringVar(value="Add a MIDI to the library, then press Reload.")
        self.analysis_var = tk.StringVar(value="Song preview updates automatically.")
        self.profile_summary_var = tk.StringVar()
        self.notice_var = tk.StringVar(
            value=(
                "Before Start: open the in-game piano, select the MIDDLE page + Default octave, "
                "then focus the game during the countdown."
            )
        )
        self.admin_var = tk.StringVar(value="Administrator access: checking…")

        self._build_ui()
        self._attach_variable_traces()
        self._load_config()
        self.admin_var.set(
            "Administrator access: Yes — game input enabled"
            if is_running_as_admin()
            else "Administrator access: No — reopen as Administrator"
        )
        self._suspend_auto_analysis = False
        self._apply_profile_ui(schedule=False)
        self._schedule_analysis()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._drain_ui_queue)
        self.after(60, self._poll_f10)
        self.after(1500, self._poll_system_theme)

    def _apply_system_theme(self, force: bool = False) -> None:
        dark = system_prefers_dark_mode()
        if force or dark != self._dark_mode:
            self._dark_mode = dark
            apply_theme(self, self._style, dark)

    def _poll_system_theme(self) -> None:
        self._apply_system_theme()
        self.after(1500, self._poll_system_theme)

    def _build_ui(self) -> None:
        self._apply_system_theme(force=True)

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text=APP_NAME, style="Title.TLabel").pack(side="left")
        ttk.Label(header, text=f"by {APP_AUTHOR}", style="Author.TLabel").pack(
            side="left", padx=(10, 0), pady=(8, 0)
        )
        ttk.Label(
            outer,
            text="Simple MIDI keyboard player for Blue Protocol: Star Resonance",
        ).pack(anchor="w")
        ttk.Label(outer, textvariable=self.admin_var, style="Hint.TLabel").pack(
            anchor="w", pady=(2, 10)
        )

        notice = ttk.LabelFrame(outer, text="Before playback", padding=9)
        notice.pack(fill="x", pady=(0, 10))
        ttk.Label(
            notice,
            textvariable=self.notice_var,
            wraplength=790,
            justify="left",
        ).pack(anchor="w")

        profile_frame = ttk.LabelFrame(outer, text="1. Choose your unlocked-key profile", padding=10)
        profile_frame.pack(fill="x", pady=(0, 10))
        profile_frame.columnconfigure(1, weight=1)
        ttk.Label(profile_frame, text="Profile").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.profile_combo = ttk.Combobox(
            profile_frame,
            textvariable=self.profile_var,
            values=list(PROFILE_LABELS),
            state="readonly",
            width=42,
        )
        self.profile_combo.grid(row=0, column=1, sticky="ew")
        self.profile_combo.bind("<<ComboboxSelected>>", lambda _event: self._profile_changed())
        ttk.Label(
            profile_frame,
            textvariable=self.profile_summary_var,
            wraplength=760,
            justify="left",
            style="Hint.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        file_frame = ttk.LabelFrame(outer, text="2. Choose a song", padding=10)
        file_frame.pack(fill="x", pady=(0, 10))
        file_frame.columnconfigure(0, weight=1)

        self.midi_combo = ttk.Combobox(
            file_frame,
            textvariable=self.midi_display_var,
            state="readonly",
            values=(),
        )
        self.midi_combo.grid(row=0, column=0, sticky="ew")
        self.midi_combo.bind("<<ComboboxSelected>>", lambda _event: self._midi_selected())
        ttk.Button(file_frame, text="Open Folder", command=self._open_midi_folder).grid(
            row=0, column=1, padx=(8, 0)
        )
        ttk.Button(file_frame, text="Reload", command=self._reload_midi_library).grid(
            row=0, column=2, padx=(8, 0)
        )
        ttk.Label(
            file_frame,
            textvariable=self.midi_folder_var,
            style="Hint.TLabel",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(7, 0))

        self.custom_settings_frame = ttk.LabelFrame(
            outer,
            text="Custom profile settings",
            padding=10,
        )
        self.custom_settings_frame.columnconfigure(1, weight=1)
        self.custom_settings_frame.columnconfigure(3, weight=1)
        self._build_custom_settings(self.custom_settings_frame)

        self.analysis_frame = ttk.LabelFrame(outer, text="Song preview — updates automatically", padding=10)
        self.analysis_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(
            self.analysis_frame,
            textvariable=self.analysis_var,
            wraplength=790,
            justify="left",
        ).pack(anchor="w")

        run_frame = ttk.LabelFrame(outer, text="3. Play", padding=10)
        run_frame.pack(fill="x", pady=(0, 8))
        run_frame.columnconfigure(5, weight=1)

        ttk.Label(run_frame, text="Start delay").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(
            run_frame,
            from_=0,
            to=30,
            increment=0.5,
            textvariable=self.start_delay_var,
            width=6,
        ).grid(row=0, column=1, sticky="w", padx=(6, 2))
        ttk.Label(run_frame, text="sec").grid(row=0, column=2, sticky="w")
        ttk.Checkbutton(
            run_frame,
            text="Minimize after Start",
            variable=self.minimize_var,
            command=self._save_config,
        ).grid(row=0, column=3, sticky="w", padx=(18, 0))

        self.start_button = ttk.Button(run_frame, text="▶ Start", command=self._start)
        self.start_button.grid(row=0, column=6, padx=(10, 0))
        self.stop_button = ttk.Button(
            run_frame,
            text="■ Stop (F10)",
            command=self._stop,
            state="disabled",
        )
        self.stop_button.grid(row=0, column=7, padx=(8, 0))

        ttk.Label(run_frame, text="Input method").grid(row=1, column=0, sticky="w", pady=(9, 0))
        self.input_backend_combo = ttk.Combobox(
            run_frame,
            textvariable=self.input_backend_var,
            values=list(INPUT_BACKEND_LABELS),
            state="readonly",
            width=30,
        )
        self.input_backend_combo.grid(
            row=1, column=1, columnspan=3, sticky="w", padx=(6, 0), pady=(9, 0)
        )
        self.input_backend_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._save_config()
        )
        self.test_button = ttk.Button(
            run_frame,
            text="Test input (3s)",
            command=self._test_input,
        )
        self.test_button.grid(row=1, column=6, padx=(10, 0), pady=(9, 0))
        ttk.Button(run_frame, text="Reset", command=self._reset_defaults).grid(
            row=1, column=7, padx=(8, 0), pady=(9, 0)
        )

        self.progress = ttk.Progressbar(outer, maximum=1.0, mode="determinate")
        self.progress.pack(fill="x", pady=(2, 6))
        ttk.Label(outer, textvariable=self.status_var).pack(anchor="w")

        ttk.Separator(outer).pack(fill="x", pady=10)
        ttk.Label(
            outer,
            text=(
                "F10 is an emergency stop. Tier 1–3 lock safe settings and never press < or >. "
                "Choose Custom only for manual tuning or full-range page switching. "
                f"The app follows the Windows light/dark theme automatically. Input ABI: {input_abi_diagnostics()}."
            ),
            wraplength=800,
            style="Hint.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                f"Created by {APP_AUTHOR}. Independent MIDI-only implementation inspired by "
                "Sanheiii/ok-star-resonance. AGPL-3.0."
            ),
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(4, 0))

    def _build_custom_settings(self, settings: ttk.LabelFrame) -> None:
        ttk.Label(settings, text="Playback style").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.mode_combo = ttk.Combobox(
            settings,
            textvariable=self.mode_var,
            values=list(MODE_LABELS),
            state="readonly",
            width=35,
        )
        self.mode_combo.grid(row=0, column=1, columnspan=3, sticky="ew", pady=4)

        ttk.Label(settings, text="Unlocked range").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.unlock_combo = ttk.Combobox(
            settings,
            textvariable=self.unlock_var,
            values=list(UNLOCK_LABELS),
            state="readonly",
            width=25,
        )
        self.unlock_combo.grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(settings, text="Page delay").grid(row=1, column=2, sticky="w", padx=(22, 8), pady=4)
        self.page_delay_spin = ttk.Spinbox(
            settings,
            from_=40,
            to=1000,
            increment=10,
            textvariable=self.page_delay_var,
            width=7,
        )
        self.page_delay_spin.grid(row=1, column=3, sticky="w")
        ttk.Label(settings, text="ms").grid(row=1, column=3, sticky="w", padx=(62, 0))

        ttk.Label(settings, text="Fit unavailable notes").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        self.mapping_combo = ttk.Combobox(
            settings,
            textvariable=self.mapping_var,
            values=list(MAPPING_LABELS),
            state="readonly",
            width=35,
        )
        self.mapping_combo.grid(row=2, column=1, columnspan=3, sticky="ew", pady=4)

        ttk.Label(settings, text="Chord detail").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=4)
        self.chord_combo = ttk.Combobox(
            settings,
            textvariable=self.chord_var,
            values=list(CHORD_LABELS),
            state="readonly",
            width=27,
        )
        self.chord_combo.grid(row=3, column=1, sticky="w", pady=4)

        ttk.Label(settings, text="Ctrl/Shift lead").grid(row=3, column=2, sticky="w", padx=(22, 8), pady=4)
        ttk.Spinbox(
            settings,
            from_=10,
            to=500,
            increment=5,
            textvariable=self.modifier_lead_var,
            width=7,
        ).grid(row=3, column=3, sticky="w")
        ttk.Label(settings, text="ms").grid(row=3, column=3, sticky="w", padx=(62, 0))

        ttk.Label(settings, text="Speed").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Spinbox(settings, from_=25, to=200, textvariable=self.speed_var, width=7).grid(
            row=4, column=1, sticky="w"
        )
        ttk.Label(settings, text="%  (85 = slower)").grid(row=4, column=1, sticky="w", padx=(62, 0))

        ttk.Label(settings, text="Note length").grid(row=4, column=2, sticky="w", padx=(22, 8), pady=4)
        ttk.Spinbox(settings, from_=50, to=300, textvariable=self.length_var, width=7).grid(
            row=4, column=3, sticky="w"
        )
        ttk.Label(settings, text="%").grid(row=4, column=3, sticky="w", padx=(62, 0))

        ttk.Label(settings, text="Minimum note").grid(row=5, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Spinbox(
            settings,
            from_=20,
            to=1000,
            textvariable=self.minimum_note_var,
            width=7,
        ).grid(row=5, column=1, sticky="w")
        ttk.Label(settings, text="ms").grid(row=5, column=1, sticky="w", padx=(62, 0))

        ttk.Checkbutton(
            settings,
            text="Ignore percussion/drum channel",
            variable=self.percussion_var,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(7, 0))
        ttk.Checkbutton(
            settings,
            text="Use MIDI sustain-pedal events",
            variable=self.pedal_var,
        ).grid(row=6, column=2, columnspan=2, sticky="w", padx=(22, 0), pady=(7, 0))

    def _attach_variable_traces(self) -> None:
        variables = (
            self.mode_var,
            self.unlock_var,
            self.speed_var,
            self.length_var,
            self.minimum_note_var,
            self.page_delay_var,
            self.modifier_lead_var,
            self.mapping_var,
            self.chord_var,
            self.pedal_var,
            self.percussion_var,
        )
        for variable in variables:
            variable.trace_add("write", self._custom_variable_changed)
        self.start_delay_var.trace_add("write", lambda *_args: self._save_config_if_ready())
        self.minimize_var.trace_add("write", lambda *_args: self._save_config_if_ready())

    def _profile_code(self) -> str:
        return PROFILE_LABELS.get(self.profile_var.get(), "tier3")

    def _mode_code(self) -> str:
        return MODE_LABELS.get(self.mode_var.get(), "stable")

    def _unlock_code(self) -> str:
        return UNLOCK_LABELS.get(self.unlock_var.get(), "tier3")

    def _input_backend_code(self) -> str:
        return INPUT_BACKEND_LABELS.get(self.input_backend_var.get(), "scan")

    def _capture_settings(self) -> dict[str, object]:
        return {
            "mode": self._mode_code(),
            "unlock_tier": self._unlock_code(),
            "mapping": MAPPING_LABELS.get(self.mapping_var.get(), "octave"),
            "chord_limit": CHORD_LABELS.get(self.chord_var.get(), 0),
            "speed": int(self.speed_var.get()),
            "length": int(self.length_var.get()),
            "minimum_note": int(self.minimum_note_var.get()),
            "page_delay": int(self.page_delay_var.get()),
            "modifier_lead": int(self.modifier_lead_var.get()),
            "pedal": bool(self.pedal_var.get()),
            "ignore_percussion": bool(self.percussion_var.get()),
        }

    def _apply_settings(self, settings: dict[str, object]) -> None:
        self.mode_var.set(MODE_LABELS_REVERSE.get(str(settings.get("mode", "stable")), MODE_LABELS_REVERSE["stable"]))
        self.unlock_var.set(
            UNLOCK_LABELS_REVERSE.get(
                str(settings.get("unlock_tier", "tier3")),
                UNLOCK_LABELS_REVERSE["tier3"],
            )
        )
        self.mapping_var.set(
            MAPPING_LABELS_REVERSE.get(
                str(settings.get("mapping", "octave")),
                MAPPING_LABELS_REVERSE["octave"],
            )
        )
        self.chord_var.set(
            CHORD_LABELS_REVERSE.get(int(settings.get("chord_limit", 0)), CHORD_LABELS_REVERSE[0])
        )
        self.speed_var.set(int(settings.get("speed", 85)))
        self.length_var.set(int(settings.get("length", 150)))
        self.minimum_note_var.set(int(settings.get("minimum_note", 120)))
        self.page_delay_var.set(int(settings.get("page_delay", 220)))
        self.modifier_lead_var.set(int(settings.get("modifier_lead", 55)))
        self.pedal_var.set(bool(settings.get("pedal", False)))
        self.percussion_var.set(bool(settings.get("ignore_percussion", True)))

    def _profile_changed(self) -> None:
        if self._suspend_auto_analysis:
            return
        previous = self._active_profile_code
        selected = self._profile_code()
        if previous == "custom":
            self._custom_settings = self._capture_settings()

        self._suspend_auto_analysis = True
        try:
            if selected == "custom":
                self._apply_settings(self._custom_settings)
            else:
                self._apply_settings(get_fixed_profile(selected).settings())
            self._active_profile_code = selected
            self._apply_profile_ui(schedule=False)
        finally:
            self._suspend_auto_analysis = False

        self._schedule_analysis()
        self._save_config()

    def _apply_profile_ui(self, schedule: bool = True) -> None:
        profile_code = self._profile_code()
        self._active_profile_code = profile_code

        if profile_code == "custom":
            self.profile_summary_var.set(
                "Advanced profile. All playback settings are editable. Choose Full range A0–C8 "
                "only when you want to experiment with < / > page switching."
            )
            self.custom_settings_frame.pack_forget()
            self.custom_settings_frame.pack(
                fill="x",
                pady=(0, 10),
                before=self.analysis_frame,
            )
            self._refresh_custom_mode_choices()
        else:
            profile = get_fixed_profile(profile_code)
            self.profile_summary_var.set(profile.summary + " Settings are locked for this profile.")
            self.custom_settings_frame.pack_forget()

        mode = self._mode_code()
        tier = self._unlock_code()
        profile = get_unlock_profile(tier)  # type: ignore[arg-type]
        if mode == "full" and tier == "tier4":
            self.notice_var.set(
                f"{profile.label}: open the piano on the MIDDLE page + Default octave. "
                "Custom Full range may use < / > when low or high notes require another page."
            )
        else:
            self.notice_var.set(
                f"{profile.label}: open the piano on the MIDDLE page + Default octave. "
                "This range never needs < or > page switching."
            )

        if schedule:
            self._schedule_analysis()

    def _refresh_custom_mode_choices(self) -> None:
        allowed = allowed_modes_for_unlock(self._unlock_code())
        labels = [MODE_LABELS_REVERSE[code] for code in allowed]
        self.mode_combo.configure(values=labels)
        if self._mode_code() not in allowed:
            self.mode_var.set(MODE_LABELS_REVERSE["stable"])
        use_pages = self._mode_code() in {"full", "ensemble"} and self._unlock_code() == "tier4"
        self.page_delay_spin.configure(state="normal" if use_pages else "disabled")

    def _custom_variable_changed(self, *_args: object) -> None:
        if self._suspend_auto_analysis:
            return
        if self._profile_code() == "custom":
            self._suspend_auto_analysis = True
            try:
                self._refresh_custom_mode_choices()
                self._custom_settings = self._capture_settings()
            finally:
                self._suspend_auto_analysis = False
        self._schedule_analysis()
        self._save_config_if_ready()

    def _schedule_analysis(self, delay_ms: int = 180) -> None:
        if self._suspend_auto_analysis:
            return
        if self._analysis_job is not None:
            try:
                self.after_cancel(self._analysis_job)
            except tk.TclError:
                pass
        self._analysis_job = self.after(delay_ms, self._analyze)

    def _save_config_if_ready(self) -> None:
        if not self._suspend_auto_analysis:
            self._save_config()

    def _config_path(self) -> Path:
        if os.name == "nt":
            base = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
        else:
            base = Path.home() / ".config" / "bpsr-midi-lite"
        base.mkdir(parents=True, exist_ok=True)
        return base / CONFIG_FILE

    def _legacy_config_path(self) -> Path:
        return _application_directory() / CONFIG_FILE

    def _load_config(self) -> None:
        path = self._config_path()
        if not path.exists() and self._legacy_config_path().exists():
            path = self._legacy_config_path()

        data: dict[str, object] = {}
        config_existed = path.exists()
        if config_existed:
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                data = {}

        legacy_settings = {
            "mode": str(data.get("mode", "stable")),
            "unlock_tier": str(data.get("unlock_tier", "tier3")),
            "mapping": str(data.get("mapping", "octave")),
            "chord_limit": int(data.get("chord_limit", 0)),
            "speed": int(data.get("speed", 85)),
            "length": int(data.get("length", 150)),
            "minimum_note": int(data.get("minimum_note", 120)),
            "page_delay": int(data.get("page_delay", 220)),
            "modifier_lead": int(data.get("modifier_lead", 55)),
            "pedal": bool(data.get("pedal", False)),
            "ignore_percussion": bool(data.get("ignore_percussion", True)),
        }
        saved_custom = data.get("custom_settings")
        if isinstance(saved_custom, dict):
            self._custom_settings = {**CUSTOM_DEFAULTS, **saved_custom}
        else:
            self._custom_settings = {**CUSTOM_DEFAULTS, **legacy_settings}

        saved_profile = str(data.get("profile", ""))
        # v0.5.0 exposed Tier 4 as a fixed profile. Keep those users on the
        # equivalent editable Custom full-range setup after the profile cleanup.
        if saved_profile == "tier4":
            saved_profile = "custom"
            self._custom_settings = {
                **self._custom_settings,
                "mode": "full",
                "unlock_tier": "tier4",
            }
        if saved_profile not in {"tier1", "tier2", "tier3", "custom"}:
            # Preserve a user's old manually tuned v0.4.x settings. Brand-new
            # installs start on the simple Tier 3 preset.
            saved_profile = "custom" if config_existed else "tier3"
        self.profile_var.set(PROFILE_LABELS_REVERSE[saved_profile])
        self._active_profile_code = saved_profile

        if saved_profile == "custom":
            self._apply_settings(self._custom_settings)
        else:
            self._apply_settings(get_fixed_profile(saved_profile).settings())

        self.start_delay_var.set(float(data.get("start_delay", 3.0)))
        self.minimize_var.set(bool(data.get("minimize", True)))
        input_backend = str(data.get("input_backend", "scan"))
        self.input_backend_var.set(
            INPUT_BACKEND_LABELS_REVERSE.get(input_backend, INPUT_BACKEND_LABELS_REVERSE["scan"])
        )

        folder = _default_midi_folder()
        self.midi_folder_var.set(str(folder))
        preferred = str(data.get("selected_midi", "")).strip()
        self._reload_midi_library(analyze=False, preferred_display=preferred)

    def _save_config(self) -> None:
        if self._suspend_auto_analysis:
            return
        if self._profile_code() == "custom":
            self._custom_settings = self._capture_settings()
        current = self._capture_settings()
        data = {
            "profile": self._profile_code(),
            "custom_settings": self._custom_settings,
            "selected_midi": self.midi_display_var.get(),
            "start_delay": self.start_delay_var.get(),
            "minimize": self.minimize_var.get(),
            "input_backend": self._input_backend_code(),
            **current,
        }
        try:
            self._config_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _plan_options(self) -> PlanOptions:
        return PlanOptions(
            mode=self._mode_code(),  # type: ignore[arg-type]
            speed_percent=int(self.speed_var.get()),
            note_length_percent=int(self.length_var.get()),
            minimum_note_ms=int(self.minimum_note_var.get()),
            page_switch_delay_ms=int(self.page_delay_var.get()),
            octave_switch_lead_ms=int(self.modifier_lead_var.get()),
            unlock_tier=self._unlock_code(),  # type: ignore[arg-type]
            mapping_method=MAPPING_LABELS.get(self.mapping_var.get(), "octave"),  # type: ignore[arg-type]
            max_notes_per_chord=CHORD_LABELS.get(self.chord_var.get(), 0),
            use_sustain_pedal=bool(self.pedal_var.get()),
            ignore_percussion=bool(self.percussion_var.get()),
        )

    def _open_midi_folder(self) -> None:
        folder = Path(self.midi_folder_var.get())
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Could not open the MIDI folder:\n{exc}")

    def _reload_midi_library(
        self,
        analyze: bool = True,
        preferred_display: str | None = None,
    ) -> None:
        folder = Path(self.midi_folder_var.get())
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.status_var.set(f"Could not use MIDI folder: {exc}")
            return

        previous = preferred_display or self.midi_display_var.get()
        files = scan_midi_folder(folder)
        self._midi_lookup = {
            path.relative_to(folder).as_posix(): path
            for path in files
        }
        values = list(self._midi_lookup)
        self.midi_combo.configure(values=values)

        selected = previous if previous in self._midi_lookup else (values[0] if values else "")
        self.midi_display_var.set(selected)
        self.file_var.set(str(self._midi_lookup[selected]) if selected else "")

        if not values:
            self.current_plan = None
            self.analysis_var.set(
                "No MIDI files found. Click Open Folder, copy in .mid or .midi files, then click Reload."
            )
            self.status_var.set("MIDI library is empty.")
            return

        self.status_var.set(f"Loaded {len(values)} song(s). Previewing the selected MIDI…")
        if analyze:
            self._schedule_analysis(20)

    def _midi_selected(self) -> None:
        selected = self.midi_display_var.get()
        path = self._midi_lookup.get(selected)
        self.file_var.set(str(path) if path is not None else "")
        self._schedule_analysis(20)
        self._save_config()

    def _analyze(self) -> None:
        self._analysis_job = None
        path = self.file_var.get()
        if not path or not Path(path).exists():
            self.current_plan = None
            return
        try:
            plan = build_plan(path, self._plan_options())
        except Exception as exc:  # noqa: BLE001
            self.current_plan = None
            self.analysis_var.set(f"Could not preview this MIDI:\n{exc}")
            self.status_var.set(str(exc))
            return

        self.current_plan = plan
        profile_name = self.profile_var.get().split(" — ", 1)[0]
        page_rate = plan.page_switches / max(plan.duration / 60.0, 0.001)
        original_range = f"{midi_note_name(plan.source_min_pitch)}–{midi_note_name(plan.source_max_pitch)}"
        played_range = f"{midi_note_name(plan.planned_min_pitch)}–{midi_note_name(plan.planned_max_pitch)}"

        if plan.page_switches == 0:
            page_line = "No < / > page switching"
        else:
            page_line = (
                f"{plan.page_switches:,} page-key press(es) ({page_rate:.1f}/min) • "
                f"{plan.added_delay:.2f}s timing compensation"
            )

        changes = []
        if plan.folded_notes:
            changes.append(f"{plan.folded_notes:,} remapped")
        if plan.skipped_notes:
            changes.append(f"{plan.skipped_notes:,} skipped")
        if plan.filtered_notes:
            changes.append(f"{plan.filtered_notes:,} simplified/filtered")
        change_text = " • ".join(changes) if changes else "No notes changed"

        warning = ""
        if page_rate > 20:
            warning = "\n⚠ Frequent page changes: a Custom Stable profile may sound smoother."

        self.analysis_var.set(
            f"Ready • {profile_name} • {plan.note_count:,} played notes • {_duration_text(plan.duration)}\n"
            f"Original range {original_range} → played range {played_range} • {change_text}\n"
            f"{page_line} • {plan.octave_switches:,} Ctrl/Shift switch(es){warning}"
        )
        self.status_var.set("Ready. Press Start, then focus the game during the countdown.")
        self._save_config()

    def _require_admin_for_input(self) -> bool:
        if is_running_as_admin():
            return True
        messagebox.showerror(
            APP_NAME,
            "BPSR MIDI Lite is not running as Administrator.\n\n"
            "Close it, then right-click the EXE and choose 'Run as administrator'. "
            "The official build normally requests this automatically.",
        )
        return False

    def _test_input(self) -> None:
        if os.name != "nt":
            messagebox.showerror(APP_NAME, "Keyboard injection is supported only on Windows.")
            return
        if self.player.is_playing or self._input_test_running:
            messagebox.showinfo(APP_NAME, "Stop playback before running the input test.")
            return
        if not self._require_admin_for_input():
            return

        self._input_test_running = True
        self.test_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.status_var.set("Input test starts in 3 seconds. Focus Notepad or the game piano.")
        if self.minimize_var.get():
            self.after(250, self.iconify)

        def worker() -> None:
            error: str | None = None
            sender: WindowsKeySender | None = None
            try:
                for remaining in (3, 2, 1):
                    self.ui_queue.put(("test_status", f"Input test in {remaining}… focus the target window"))
                    time.sleep(1.0)
                sender = WindowsKeySender(self._input_backend_code())
                for key in ("a", "s", "d", "f"):
                    sender.tap(key, hold_seconds=0.080, gap_seconds=0.120)
                sender.release_all()
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
            details = sender.description if error is None and sender is not None else ""
            self.ui_queue.put(("test_finished", (error, details)))

        threading.Thread(target=worker, daemon=True).start()

    def _start(self) -> None:
        if os.name != "nt":
            messagebox.showerror(APP_NAME, "Playback is supported only on Windows.")
            return
        if not self._require_admin_for_input():
            return
        self._analyze()
        if self.current_plan is None:
            messagebox.showerror(APP_NAME, "Choose a valid MIDI from the library first.")
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
            messagebox.showerror(APP_NAME, str(exc))
            return

        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.test_button.configure(state="disabled")
        self.progress["value"] = 0
        self._save_config()
        if self.minimize_var.get():
            self.after(250, self.iconify)

    def _stop(self) -> None:
        self.player.stop()
        self.status_var.set("Stopping and releasing keys…")

    def _thread_status(self, text: str, progress: float) -> None:
        self.ui_queue.put(("status", (text, progress)))

    def _thread_finished(self, error: str | None) -> None:
        self.ui_queue.put(("finished", error))

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "status":
                    text, progress = payload  # type: ignore[misc]
                    self.status_var.set(str(text))
                    self.progress["value"] = float(progress)
                elif kind == "test_status":
                    self.status_var.set(str(payload))
                elif kind == "test_finished":
                    self._input_test_running = False
                    self.start_button.configure(state="normal")
                    self.test_button.configure(state="normal")
                    self.deiconify()
                    self.lift()
                    error, details = payload  # type: ignore[misc]
                    if error:
                        self.status_var.set(f"Input test error: {error}")
                        messagebox.showerror(APP_NAME, str(error))
                    else:
                        backend = BACKEND_NAMES.get(self._input_backend_code(), "selected method")
                        self.status_var.set(f"Input test sent A S D F using {backend}. {details}")
                elif kind == "finished":
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.test_button.configure(state="normal")
                    self.deiconify()
                    self.lift()
                    if payload:
                        self.status_var.set(f"Playback error: {payload}")
                        messagebox.showerror(APP_NAME, str(payload))
                    elif self.player.stop_event.is_set():
                        self.status_var.set("Stopped. All keys released and keyboard reset.")
                    else:
                        self.status_var.set("Playback completed. Keyboard reset to middle/default.")
        except queue.Empty:
            pass
        self.after(50, self._drain_ui_queue)

    def _poll_f10(self) -> None:
        pressed = f10_is_pressed()
        if pressed and not self._last_f10 and self.player.is_playing:
            self._stop()
        self._last_f10 = pressed
        self.after(60, self._poll_f10)

    def _reset_defaults(self) -> None:
        if self._profile_code() == "custom":
            self._custom_settings = dict(CUSTOM_DEFAULTS)
            self._suspend_auto_analysis = True
            try:
                self._apply_settings(self._custom_settings)
                self._refresh_custom_mode_choices()
            finally:
                self._suspend_auto_analysis = False
            self._schedule_analysis()
        else:
            self.profile_var.set(PROFILE_LABELS_REVERSE["tier3"])
            self._profile_changed()
        self.start_delay_var.set(3.0)
        self.minimize_var.set(True)
        self.input_backend_var.set(INPUT_BACKEND_LABELS_REVERSE["scan"])
        self._save_config()

    def _on_close(self) -> None:
        if self.player.is_playing:
            self.player.stop()
            deadline = time.time() + 1.5
            while self.player.is_playing and time.time() < deadline:
                self.update()
                time.sleep(0.02)
        self._save_config()
        self.destroy()


def dry_run(path: str, options: PlanOptions) -> int:
    plan = build_plan(path, options)
    print(f"File: {path}")
    print(f"Mode: {plan.mode}")
    print(f"Unlock tier: {plan.unlock_tier or 'custom'}")
    print(
        "Available range:",
        f"{midi_note_name(plan.effective_min_pitch)}-{midi_note_name(plan.effective_max_pitch)}",
    )
    print(f"Notes: {plan.note_count}")
    print(f"Duration: {plan.duration:.3f}s")
    print(
        "Range:",
        f"{midi_note_name(plan.source_min_pitch)}-{midi_note_name(plan.source_max_pitch)}",
        "->",
        f"{midi_note_name(plan.planned_min_pitch)}-{midi_note_name(plan.planned_max_pitch)}",
    )
    print(f"Page-key presses: {plan.page_switches}")
    print(f"Octave switches: {plan.octave_switches}")
    print(f"Remapped/folded notes: {plan.folded_notes}")
    print(f"Skipped notes: {plan.skipped_notes}")
    print(f"Song transpose: {plan.transposed_semitones:+d} semitones")
    print(f"Added delay: {plan.added_delay:.3f}s")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--dry-run", metavar="MIDI", help="Analyze a MIDI without sending keys.")
    parser.add_argument("--mode", choices=("stable", "full", "ensemble"), default="stable")
    parser.add_argument("--speed", type=int, default=85)
    parser.add_argument("--length", type=int, default=150)
    parser.add_argument("--page-delay", type=int, default=220)
    parser.add_argument("--modifier-lead", type=int, default=55)
    parser.add_argument(
        "--unlock-tier",
        choices=("tier1", "tier2", "tier3", "tier4"),
        default="tier3",
        help="tier1=C3-B4, tier2=C3-B6, tier3=C2-B6, tier4=Custom full A0-C8",
    )
    parser.add_argument(
        "--mapping",
        choices=("octave", "nearest", "transpose", "skip"),
        default="octave",
    )
    parser.add_argument("--chord-limit", type=int, default=0)
    args = parser.parse_args()

    if args.dry_run:
        return dry_run(
            args.dry_run,
            PlanOptions(
                mode=args.mode,
                speed_percent=args.speed,
                note_length_percent=args.length,
                page_switch_delay_ms=args.page_delay,
                octave_switch_lead_ms=args.modifier_lead,
                unlock_tier=args.unlock_tier,
                mapping_method=args.mapping,
                max_notes_per_chord=args.chord_limit,
            ),
        )

    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
