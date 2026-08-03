from __future__ import annotations

import argparse
import json
import os
import queue
import re
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from midi_engine import PlanOptions, build_plan, get_unlock_profile, midi_note_name
from player import MidiPlayer
from win_input import f10_is_pressed


APP_NAME = "BPSR MIDI Lite"
APP_VERSION = "0.4.1"
CONFIG_FILE = "bpsr_midi_lite.json"

MODE_LABELS = {
    "Stable — middle page, no arrows": "stable",
    "Full range solo — smart arrows + timing compensation": "full",
    "Ensemble-safe — preserve timeline, fold unsafe jumps": "ensemble",
}
MODE_LABELS_REVERSE = {value: key for key, value in MODE_LABELS.items()}
UNLOCK_LABELS = {
    "Tier 1 — C3–B4 (Beginner)": "tier1",
    "Tier 2 — C3–B6": "tier2",
    "Tier 3 — A0–B6": "tier3",
    "Tier 4 — A0–C8 (Full unlock)": "tier4",
}
UNLOCK_LABELS_REVERSE = {value: key for key, value in UNLOCK_LABELS.items()}
MAPPING_LABELS = {
    "Octave fold — preserve note names": "octave",
    "Nearest playable note — clamp outliers": "nearest",
    "Auto-transpose song, then octave fold": "transpose",
    "Skip notes outside the chosen state": "skip",
}
MAPPING_LABELS_REVERSE = {value: key for key, value in MAPPING_LABELS.items()}
CHORD_LABELS = {
    "All notes": 0,
    "Melody only (top note)": 1,
    "Bass + top note": 2,
    "Bass + top 2 notes": 3,
    "Bass + top 3 notes": 4,
}
CHORD_LABELS_REVERSE = {value: key for key, value in CHORD_LABELS.items()}

MIDI_EXTENSIONS = {".mid", ".midi"}


def _application_directory() -> Path:
    """Return the folder containing the EXE, or this source file while developing."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _default_midi_folder() -> Path:
    """Create a portable MIDI folder beside the app, with a Documents fallback."""
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


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("860x790")
        self.minsize(800, 720)

        self.player = MidiPlayer()
        self.current_plan = None
        self.ui_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._last_f10 = False

        self.file_var = tk.StringVar()
        self.midi_folder_var = tk.StringVar(value=str(_default_midi_folder()))
        self.midi_display_var = tk.StringVar()
        self._midi_lookup: dict[str, Path] = {}
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
        self.status_var = tk.StringVar(value="Choose a MIDI from the library.")
        self.analysis_var = tk.StringVar(value="")
        self.notice_var = tk.StringVar()

        self._build_ui()
        self._load_config()
        self._mode_changed()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._drain_ui_queue)
        self.after(60, self._poll_f10)

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text=APP_NAME, font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="Single-purpose MIDI keyboard player for Blue Protocol: Star Resonance",
        ).pack(anchor="w", pady=(0, 12))

        notice = ttk.LabelFrame(outer, text="Before playback", padding=10)
        notice.pack(fill="x", pady=(0, 12))
        ttk.Label(
            notice,
            textvariable=self.notice_var,
            wraplength=700,
            justify="left",
        ).pack(anchor="w")

        file_frame = ttk.LabelFrame(outer, text="MIDI library", padding=10)
        file_frame.pack(fill="x", pady=(0, 10))
        file_frame.columnconfigure(0, weight=1)

        self.midi_combo = ttk.Combobox(
            file_frame,
            textvariable=self.midi_display_var,
            state="readonly",
            values=(),
        )
        self.midi_combo.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.midi_combo.bind("<<ComboboxSelected>>", lambda _event: self._midi_selected())
        ttk.Button(file_frame, text="Analyze", command=self._analyze).grid(
            row=0, column=3, padx=(8, 0)
        )

        ttk.Entry(
            file_frame,
            textvariable=self.midi_folder_var,
            state="readonly",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(file_frame, text="Choose Folder…", command=self._choose_midi_folder).grid(
            row=1, column=1, padx=(8, 0), pady=(8, 0)
        )
        ttk.Button(file_frame, text="Open Folder", command=self._open_midi_folder).grid(
            row=1, column=2, padx=(8, 0), pady=(8, 0)
        )
        ttk.Button(file_frame, text="Reload", command=self._reload_midi_library).grid(
            row=1, column=3, padx=(8, 0), pady=(8, 0)
        )

        settings = ttk.LabelFrame(outer, text="Playback settings", padding=10)
        settings.pack(fill="x", pady=(0, 10))
        settings.columnconfigure(1, weight=1)
        settings.columnconfigure(3, weight=1)

        ttk.Label(settings, text="Mode").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.mode_combo = ttk.Combobox(
            settings,
            textvariable=self.mode_var,
            values=list(MODE_LABELS),
            state="readonly",
            width=42,
        )
        self.mode_combo.grid(row=0, column=1, columnspan=3, sticky="ew", pady=4)
        self.mode_combo.bind("<<ComboboxSelected>>", lambda _event: self._mode_changed())

        ttk.Label(settings, text="Unlocked keys").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.unlock_combo = ttk.Combobox(
            settings,
            textvariable=self.unlock_var,
            values=list(UNLOCK_LABELS),
            state="readonly",
            width=30,
        )
        self.unlock_combo.grid(row=1, column=1, sticky="w", pady=4)
        self.unlock_combo.bind("<<ComboboxSelected>>", lambda _event: self._mode_changed())

        ttk.Label(settings, text="Page-switch delay").grid(row=1, column=2, sticky="w", padx=(24, 8), pady=4)
        self.page_delay_spin = ttk.Spinbox(
            settings,
            from_=40,
            to=1000,
            increment=10,
            textvariable=self.page_delay_var,
            width=8,
        )
        self.page_delay_spin.grid(row=1, column=3, sticky="w")
        ttk.Label(settings, text="ms").grid(row=1, column=3, sticky="w", padx=(72, 0))

        ttk.Label(settings, text="Mapping").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        self.mapping_combo = ttk.Combobox(
            settings,
            textvariable=self.mapping_var,
            values=list(MAPPING_LABELS),
            state="readonly",
            width=34,
        )
        self.mapping_combo.grid(row=2, column=1, columnspan=3, sticky="ew", pady=4)
        self.mapping_combo.bind("<<ComboboxSelected>>", lambda _event: self._settings_changed())

        ttk.Label(settings, text="Chord limit").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=4)
        self.chord_combo = ttk.Combobox(
            settings,
            textvariable=self.chord_var,
            values=list(CHORD_LABELS),
            state="readonly",
            width=24,
        )
        self.chord_combo.grid(row=3, column=1, sticky="w", pady=4)
        self.chord_combo.bind("<<ComboboxSelected>>", lambda _event: self._settings_changed())

        ttk.Label(settings, text="Modifier lead").grid(row=3, column=2, sticky="w", padx=(24, 8), pady=4)
        ttk.Spinbox(
            settings,
            from_=10,
            to=500,
            increment=5,
            textvariable=self.modifier_lead_var,
            width=8,
        ).grid(row=3, column=3, sticky="w")
        ttk.Label(settings, text="ms").grid(row=3, column=3, sticky="w", padx=(72, 0))

        ttk.Label(settings, text="Speed").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Spinbox(settings, from_=25, to=200, textvariable=self.speed_var, width=8).grid(row=4, column=1, sticky="w")
        ttk.Label(settings, text="%  (85 = slower)").grid(row=4, column=1, sticky="w", padx=(72, 0))

        ttk.Label(settings, text="Note length").grid(row=4, column=2, sticky="w", padx=(24, 8), pady=4)
        ttk.Spinbox(settings, from_=50, to=300, textvariable=self.length_var, width=8).grid(row=4, column=3, sticky="w")
        ttk.Label(settings, text="%  (default 150)").grid(row=4, column=3, sticky="w", padx=(72, 0))

        ttk.Label(settings, text="Minimum note").grid(row=5, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Spinbox(settings, from_=20, to=1000, textvariable=self.minimum_note_var, width=8).grid(row=5, column=1, sticky="w")
        ttk.Label(settings, text="ms").grid(row=5, column=1, sticky="w", padx=(72, 0))

        ttk.Label(settings, text="Start delay").grid(row=5, column=2, sticky="w", padx=(24, 8), pady=4)
        ttk.Spinbox(settings, from_=0, to=30, increment=0.5, textvariable=self.start_delay_var, width=8).grid(row=5, column=3, sticky="w")
        ttk.Label(settings, text="seconds").grid(row=5, column=3, sticky="w", padx=(72, 0))

        ttk.Checkbutton(
            settings,
            text="Ignore percussion channel",
            variable=self.percussion_var,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(7, 0))
        ttk.Checkbutton(
            settings,
            text="Use MIDI sustain-pedal events",
            variable=self.pedal_var,
        ).grid(row=6, column=2, columnspan=2, sticky="w", padx=(24, 0), pady=(7, 0))
        ttk.Checkbutton(
            settings,
            text="Minimize after Start",
            variable=self.minimize_var,
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(4, 0))

        analysis = ttk.LabelFrame(outer, text="MIDI analysis", padding=10)
        analysis.pack(fill="x", pady=(0, 10))
        ttk.Label(
            analysis,
            textvariable=self.analysis_var,
            wraplength=700,
            justify="left",
        ).pack(anchor="w")

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(2, 8))
        self.start_button = ttk.Button(controls, text="▶ Start", command=self._start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(
            controls,
            text="■ Stop (F10)",
            command=self._stop,
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Reset defaults", command=self._reset_defaults).pack(side="right")

        self.progress = ttk.Progressbar(outer, maximum=1.0, mode="determinate")
        self.progress.pack(fill="x", pady=(0, 7))
        ttk.Label(outer, textvariable=self.status_var).pack(anchor="w")

        ttk.Separator(outer).pack(fill="x", pady=12)
        ttk.Label(
            outer,
            text=(
                "F10 is an emergency stop. Choose the unlock tier that matches your character. "
                "For best input compatibility, run both the game and this app normally, not as Administrator."
            ),
            wraplength=710,
            foreground="#555555",
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text="Independent MIDI-only implementation inspired by Sanheiii/ok-star-resonance. AGPL-3.0.",
            foreground="#777777",
        ).pack(anchor="w", pady=(4, 0))

    def _mode_code(self) -> str:
        return MODE_LABELS.get(self.mode_var.get(), "stable")

    def _unlock_code(self) -> str:
        return UNLOCK_LABELS.get(self.unlock_var.get(), "tier3")

    def _mode_changed(self) -> None:
        mode = self._mode_code()
        tier = self._unlock_code()
        profile = get_unlock_profile(tier)  # type: ignore[arg-type]

        if tier == "tier1":
            stable_range = "C3–B4"
        elif tier == "tier2":
            stable_range = "C3–B6"
        else:
            stable_range = "C2–B6"

        if mode == "stable":
            self.notice_var.set(
                f"Selected: {profile.label}. Open the piano on the MIDDLE page + Default octave. "
                f"Stable mode never presses < or > and auto-fits every MIDI into {stable_range}."
            )
            self.page_delay_spin.configure(state="disabled")
        elif mode == "full":
            if tier in {"tier1", "tier2"}:
                self.notice_var.set(
                    f"Selected: {profile.label}. This tier does not need keyboard pages, so Full range solo "
                    "uses only the keys/modifier states available inside your unlocked range and never presses < or >."
                )
                self.page_delay_spin.configure(state="disabled")
            else:
                self.notice_var.set(
                    f"Selected: {profile.label}. Start on the MIDDLE page + Default octave. Full range solo "
                    "preserves unlocked pitches, schedules < / > during gaps, and adds compensation time when needed."
                )
                self.page_delay_spin.configure(state="normal")
        else:
            if tier in {"tier1", "tier2"}:
                self.notice_var.set(
                    f"Selected: {profile.label}. No page switching is required at this tier. Ensemble-safe "
                    "keeps the original timeline and remaps only notes outside your unlocked range."
                )
                self.page_delay_spin.configure(state="disabled")
            else:
                self.notice_var.set(
                    f"Selected: {profile.label}. Start on the MIDDLE page + Default octave. Ensemble-safe "
                    "changes page only when an existing gap is long enough; unsafe notes use your mapping choice."
                )
                self.page_delay_spin.configure(state="normal")
        self._settings_changed()

    def _settings_changed(self) -> None:
        if self.file_var.get() and Path(self.file_var.get()).exists():
            self.after_idle(self._analyze)

    def _config_path(self) -> Path:
        # Store settings in the user's profile so folder selection stays saved
        # even when the EXE is moved or placed in a protected directory.
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
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                data = {}

        mode = str(data.get("mode", "stable"))
        self.mode_var.set(MODE_LABELS_REVERSE.get(mode, MODE_LABELS_REVERSE["stable"]))
        saved_tier = str(data.get("unlock_tier", ""))
        if saved_tier not in UNLOCK_LABELS_REVERSE:
            legacy_range = str(data.get("range", "A0–B6"))
            saved_tier = "tier4" if "C8" in legacy_range else "tier3"
        self.unlock_var.set(
            UNLOCK_LABELS_REVERSE.get(saved_tier, UNLOCK_LABELS_REVERSE["tier3"])
        )
        self.speed_var.set(int(data.get("speed", 85)))
        self.length_var.set(int(data.get("length", 150)))
        self.minimum_note_var.set(int(data.get("minimum_note", 120)))
        self.page_delay_var.set(int(data.get("page_delay", 220)))
        self.modifier_lead_var.set(int(data.get("modifier_lead", 55)))
        self.start_delay_var.set(float(data.get("start_delay", 3.0)))
        mapping = str(data.get("mapping", "octave"))
        self.mapping_var.set(
            MAPPING_LABELS_REVERSE.get(mapping, MAPPING_LABELS_REVERSE["octave"])
        )
        legacy_melody = bool(data.get("melody_only", False))
        chord_limit = int(data.get("chord_limit", 1 if legacy_melody else 0))
        self.chord_var.set(CHORD_LABELS_REVERSE.get(chord_limit, CHORD_LABELS_REVERSE[0]))
        self.pedal_var.set(bool(data.get("pedal", False)))
        self.percussion_var.set(bool(data.get("ignore_percussion", True)))
        self.minimize_var.set(bool(data.get("minimize", True)))

        saved_folder = str(data.get("midi_folder", "")).strip()
        folder = Path(saved_folder) if saved_folder else _default_midi_folder()
        if not folder.exists() or not folder.is_dir():
            folder = _default_midi_folder()
        self.midi_folder_var.set(str(folder))

        preferred = str(data.get("selected_midi", "")).strip()
        if not preferred:
            legacy_file = str(data.get("file", "")).strip()
            if legacy_file and Path(legacy_file).exists():
                try:
                    preferred = Path(legacy_file).relative_to(folder).as_posix()
                except ValueError:
                    preferred = ""
        self._reload_midi_library(analyze=False, preferred_display=preferred)

    def _save_config(self) -> None:
        data = {
            "file": self.file_var.get(),
            "midi_folder": self.midi_folder_var.get(),
            "selected_midi": self.midi_display_var.get(),
            "mode": self._mode_code(),
            "unlock_tier": self._unlock_code(),
            "speed": self.speed_var.get(),
            "length": self.length_var.get(),
            "minimum_note": self.minimum_note_var.get(),
            "page_delay": self.page_delay_var.get(),
            "modifier_lead": self.modifier_lead_var.get(),
            "start_delay": self.start_delay_var.get(),
            "mapping": MAPPING_LABELS.get(self.mapping_var.get(), "octave"),
            "chord_limit": CHORD_LABELS.get(self.chord_var.get(), 0),
            "pedal": self.pedal_var.get(),
            "ignore_percussion": self.percussion_var.get(),
            "minimize": self.minimize_var.get(),
        }
        try:
            self._config_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _options(self) -> PlanOptions:
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

    def _show_native_dialog(self, callback):  # type: ignore[no-untyped-def]
        """Keep a native file/folder dialog in front of the game and this app."""
        self.deiconify()
        self.lift()
        self.focus_force()
        try:
            self.attributes("-topmost", True)
            self.update_idletasks()
            return callback()
        finally:
            self.attributes("-topmost", False)
            self.lift()

    def _choose_midi_folder(self) -> None:
        current = Path(self.midi_folder_var.get())
        initial = current if current.exists() else _default_midi_folder()
        path = self._show_native_dialog(
            lambda: filedialog.askdirectory(
                parent=self,
                title="Choose MIDI library folder",
                initialdir=str(initial),
                mustexist=True,
            )
        )
        if not path:
            return
        self.midi_folder_var.set(str(Path(path).resolve()))
        self._reload_midi_library()
        self._save_config()

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
            self.analysis_var.set("")
            self.status_var.set(
                "No MIDI files found. Put .mid or .midi files in the folder, then click Reload."
            )
            return

        self.status_var.set(f"Loaded {len(values)} MIDI file(s) from the library.")
        if analyze:
            self._analyze()

    def _midi_selected(self) -> None:
        selected = self.midi_display_var.get()
        path = self._midi_lookup.get(selected)
        if path is None:
            self.file_var.set("")
            return
        self.file_var.set(str(path))
        self._analyze()

    def _analyze(self) -> None:
        try:
            plan = build_plan(self.file_var.get(), self._options())
        except Exception as exc:  # noqa: BLE001
            self.current_plan = None
            self.analysis_var.set("")
            self.status_var.set(str(exc))
            return

        self.current_plan = plan
        mode_name = {
            "stable": "Stable",
            "full": "Full range solo",
            "ensemble": "Ensemble-safe",
        }[plan.mode]
        mapping_name = self.mapping_var.get().split(" — ", 1)[0]
        transpose_text = (
            f"{plan.transposed_semitones:+d} semitones"
            if plan.transposed_semitones
            else "none"
        )
        page_rate = plan.page_switches / max(plan.duration / 60.0, 0.001)
        unlock_name = get_unlock_profile(plan.unlock_tier).label if plan.unlock_tier else "Custom range"
        self.analysis_var.set(
            f"Mode: {mode_name}    Unlock: {unlock_name}    Mapping: {mapping_name}\n"
            f"Notes: {plan.note_count:,}    "
            f"Duration: {plan.duration / 60:.1f} min\n"
            f"Source range: {midi_note_name(plan.source_min_pitch)}–{midi_note_name(plan.source_max_pitch)}    "
            f"Available in this mode: {midi_note_name(plan.effective_min_pitch)}–{midi_note_name(plan.effective_max_pitch)}\n"
            f"Played range: {midi_note_name(plan.planned_min_pitch)}–{midi_note_name(plan.planned_max_pitch)}    "
            f"Song transpose: {transpose_text}\n"
            f"Page-key presses: {plan.page_switches:,} ({page_rate:.1f}/min)    "
            f"Ctrl/Shift switches: {plan.octave_switches:,}    Timing compensation: {plan.added_delay:.2f}s\n"
            f"Remapped/folded notes: {plan.folded_notes:,}    Skipped notes: {plan.skipped_notes:,}    "
            f"Duplicates merged: {plan.merged_notes:,}    Filtered notes: {plan.filtered_notes:,}"
        )
        if plan.mode == "stable":
            self.status_var.set("Ready. This plan contains no < / > events.")
        elif plan.mode == "full":
            if plan.page_switches == 0:
                self.status_var.set("Ready. This unlock tier and MIDI require no < / > page presses.")
            elif page_rate > 20:
                self.status_var.set(
                    "Ready, but this MIDI needs frequent page changes. Stable mode may sound smoother."
                )
            else:
                self.status_var.set(
                    "Ready. Each < / > press is separately scheduled and timing-compensated."
                )
        else:
            if plan.page_switches == 0:
                self.status_var.set("Ready. The source timeline is preserved with no page presses.")
            else:
                self.status_var.set("Ready. Unsafe page jumps are remapped without changing the timeline.")
        self._save_config()

    def _start(self) -> None:
        if os.name != "nt":
            messagebox.showerror(APP_NAME, "Playback is supported only on Windows.")
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
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(APP_NAME, str(exc))
            return

        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
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
                elif kind == "finished":
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.deiconify()
                    self.lift()
                    if payload:
                        self.status_var.set(f"Playback error: {payload}")
                        messagebox.showerror(APP_NAME, str(payload))
                    elif self.player.stop_event.is_set():
                        self.status_var.set("Stopped. All keys released and keyboard reset to middle/default.")
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
        self.mode_var.set(MODE_LABELS_REVERSE["stable"])
        self.unlock_var.set(UNLOCK_LABELS_REVERSE["tier3"])
        self.speed_var.set(85)
        self.length_var.set(150)
        self.minimum_note_var.set(120)
        self.page_delay_var.set(220)
        self.modifier_lead_var.set(55)
        self.start_delay_var.set(3.0)
        self.mapping_var.set(MAPPING_LABELS_REVERSE["octave"])
        self.chord_var.set(CHORD_LABELS_REVERSE[0])
        self.pedal_var.set(False)
        self.percussion_var.set(True)
        self.minimize_var.set(True)
        self._mode_changed()

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
        help="tier1=C3-B4, tier2=C3-B6, tier3=A0-B6, tier4=A0-C8",
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
