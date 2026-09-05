"""Studio-only Audio → Band Accurate tab, with optional engine controls tucked away."""
from __future__ import annotations

import json
import os
import queue
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from studio_band.arrange import ArrangementSettings, PARTS, load_drum_profile
from studio_band.export import copy_export
from studio_band.pipeline import BandPipeline, ConversionSettings
from studio_band.preview import PreviewPlayer
from studio_band.protocol import Cancelled
from studio_band.runtime import RUNTIMES, detect_hardware
from studio_band.storage import atomic_json, read_json


class BandAudioTab:
    def __init__(self, app):
        self.app, self.pipeline = app, BandPipeline()
        self.events, self.cancel, self.preview = queue.Queue(), threading.Event(), PreviewPlayer()
        self.busy, self.manifest, self.record, self.details = False, None, None, ""
        self.path = tk.StringVar(app)
        self.melody = tk.StringVar(app, value="Auto")
        self.quality = tk.StringVar(app, value="Auto")
        self.device = tk.StringVar(app, value="auto")
        self.cross_check = tk.BooleanVar(app, value=True)
        self.install = tk.BooleanVar(app, value=True)
        self.status = tk.StringVar(app, value="Choose or drop a song to create four playable band parts.")
        self.hardware = tk.StringVar(app, value="Checking audio acceleration…")
        self.mutes = {p: tk.BooleanVar(app, value=False) for p in PARTS}
        self.tiers = {p: tk.StringVar(app, value=t) for p,t in {"piano": "tier4", "guitar": "tier3", "bass": "tier2"}.items()}
        self.tab = ttk.Frame(app.song_source_notebook, padding=(10, 8))
        app.song_source_notebook.add(self.tab, text="Audio → Band")
        ttk.Label(self.tab, text="Turn a song into Piano, Guitar, Bass and Drums.", wraplength=320).pack(anchor="w", pady=(0, 8))
        ttk.Button(self.tab, text="Open Audio → Band workspace", command=self.open_workspace).pack(anchor="w")
        ttk.Label(self.tab, textvariable=self.status, wraplength=320).pack(anchor="w", pady=8)
        # The established MIDI Library is fixed at 400 px. Give analysis and
        # preview a separate resizable workspace instead of clipping its controls.
        self.workspace = tk.Toplevel(app)
        self.workspace.withdraw()
        self.workspace.title("Studio · Audio → Band Accurate")
        self.workspace.geometry("860x620")
        self.workspace.minsize(760, 540)
        self.workspace.protocol("WM_DELETE_WINDOW", self.hide_workspace)
        body = ttk.Frame(self.workspace, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        row = ttk.Frame(body)
        row.grid(row=0, column=0, sticky="ew")
        row.columnconfigure(0, weight=1)
        entry = ttk.Entry(row, textvariable=self.path)
        entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(row, text="Choose song", command=self.browse).grid(row=0, column=1, padx=(6, 0))
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD
            TkinterDnD._require(app)
            entry.drop_target_register(DND_FILES)
            entry.dnd_bind("<<Drop>>", self.drop)
        except (ImportError, RuntimeError, tk.TclError):
            # Elevated Windows apps cannot always receive Explorer file drops;
            # the file picker is always available, including without TkDnD.
            pass
        controls = ttk.Frame(body)
        controls.grid(row=1, column=0, sticky="w", pady=8)
        ttk.Label(controls, text="Main Melody").grid(row=0, column=0, sticky="w")
        ttk.Combobox(controls, textvariable=self.melody, values=("Auto", "Piano", "Guitar"), width=9, state="readonly").grid(row=0, column=1, padx=(6, 18))
        ttk.Label(controls, text="Stem Quality").grid(row=0, column=2)
        ttk.Combobox(controls, textvariable=self.quality, values=("Auto", "Standard", "HQ"), width=10, state="readonly").grid(row=0, column=3, padx=6)
        ttk.Button(controls, text="Advanced", command=self.advanced).grid(row=0, column=4, padx=8)
        ttk.Label(body, textvariable=self.hardware, style="Hint.TLabel").grid(row=2, column=0, sticky="w")
        ttk.Label(body, text="First use downloads several GB of models.", style="Hint.TLabel").grid(row=2, column=0, sticky="e")
        actions = ttk.Frame(body)
        actions.grid(row=3, column=0, sticky="w", pady=(8, 4))
        self.convert_button = ttk.Button(actions, text="Analyze & Convert", command=self.convert)
        self.convert_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, text="Cancel", command=lambda: self.cancel.set(), state="disabled")
        self.cancel_button.pack(side="left", padx=6)
        ttk.Button(actions, text="Open arrangement", command=self.open_arrangement).pack(side="left", padx=6)
        self.rearrange_button = ttk.Button(actions, text="Apply melody / category", command=self.rearrange, state="disabled")
        self.rearrange_button.pack(side="left")
        self.bar = ttk.Progressbar(body, mode="indeterminate")
        self.bar.grid(row=4, column=0, sticky="ew", pady=5)
        status = ttk.Label(body, textvariable=self.status, wraplength=720, justify="left")
        status.grid(row=5, column=0, sticky="w")
        body.bind("<Configure>", lambda event: status.configure(wraplength=max(300, event.width-10)))
        self.summary = ttk.Treeview(body, columns=("notes", "melody", "rejected", "simplified", "shifted"), show="tree headings", height=4)
        self.summary.heading("#0", text="Part")
        self.summary.column("#0", width=100, stretch=True)
        for name, label in (("notes", "Notes / hits"), ("melody", "Melody"), ("rejected", "Low confidence"), ("simplified", "Simplified"), ("shifted", "Range shifted")):
            self.summary.heading(name, text=label)
            self.summary.column(name, width=105, minwidth=65, anchor="center")
        self.summary.grid(row=6, column=0, sticky="ew", pady=8)
        listen = ttk.Frame(body)
        listen.grid(row=7, column=0, sticky="w")
        ttk.Button(listen, text="▶ Full Band", command=lambda: self.audition(set(PARTS))).pack(side="left")
        for part in PARTS:
            ttk.Button(listen, text=part.title(), command=lambda p=part: self.audition({p}), width=8).pack(side="left", padx=3)
        ttk.Button(listen, text="Stop", command=self.preview.stop, width=6).pack(side="left")
        muted = ttk.Frame(body)
        muted.grid(row=8, column=0, sticky="w", pady=3)
        ttk.Label(muted, text="Mute for next preview:").pack(side="left")
        for part in PARTS:
            ttk.Checkbutton(muted, text=part.title(), variable=self.mutes[part]).pack(side="left", padx=4)
        footer = ttk.Frame(body)
        footer.grid(row=9, column=0, sticky="w", pady=(6, 0))
        self.save_button = ttk.Button(footer, text="Export all files", command=self.save, state="disabled")
        self.save_button.pack(side="left")
        self.use_button = ttk.Button(footer, text="Use Full Band in BPSR", command=self.use, state="disabled")
        self.use_button.pack(side="left", padx=6)
        ttk.Button(footer, text="Technical details", command=self.show_details).pack(side="left")
        self.tab.bind("<Destroy>", lambda event: self.close() if event.widget is self.tab else None)
        self.app.after(100, self.poll)

        def hardware():
            info = detect_hardware()
            self.events.put(("hardware", "GPU detected · each model checks CUDA support" if info.cuda else "CPU mode - conversion will be slower"))
            self.pipeline.store.cleanup()
        threading.Thread(target=hardware, daemon=True).start()

    def open_workspace(self):
        self.workspace.deiconify()
        self.workspace.lift()

    def hide_workspace(self):
        self.preview.stop()
        self.workspace.withdraw()

    def browse(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(parent=self.app, title="Choose a song", filetypes=[("Audio", "*.mp3 *.wav *.flac *.m4a *.ogg")])
        if path:
            self.path.set(path)

    def drop(self, event):
        files = self.app.tk.splitlist(event.data)
        if not self.busy and files:
            self.path.set(files[0])
        return event.action

    def arrangement_settings(self):
        return ArrangementSettings(self.melody.get().lower(), {p:v.get() for p,v in self.tiers.items()})

    def start(self, action):
        if self.busy:
            return
        self.busy = True
        self.cancel = threading.Event()
        self.preview.stop()
        self.convert_button.configure(state="disabled")
        self.rearrange_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.bar.start(12)
        def worker():
            try:
                self.events.put(("done", action()))
            except Exception as exc:
                self.events.put(("error", (str(exc), getattr(exc, "details", ""), isinstance(exc, Cancelled))))
        threading.Thread(target=worker, daemon=True, name="studio-band-job").start()

    def convert(self):
        source = Path(self.path.get().strip().strip('"'))
        settings = ConversionSettings(self.quality.get().lower(), self.device.get(), self.install.get(),
                                      self.cross_check.get(), self.arrangement_settings())
        self.start(lambda: self.pipeline.convert(source, settings, cancel=self.cancel,
                                                 progress=lambda text: self.events.put(("progress", text))))

    def rearrange(self):
        if self.manifest:
            settings, manifest = self.arrangement_settings(), self.manifest
            self.status.set("Re-arranging cached musical evidence…")
            self.start(lambda: self.pipeline.rearrange(manifest, settings))

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "hardware":
                    self.hardware.set(value)
                elif kind == "progress":
                    self.status.set(value)
                elif kind in {"done", "error"}:
                    self.busy = False
                    self.bar.stop()
                    self.cancel_button.configure(state="disabled")
                    self.convert_button.configure(state="normal", text="Analyze & Convert" if kind == "done" else "Retry conversion")
                    if kind == "done" and value:
                        self.show_result(Path(value))
                    elif kind == "error":
                        self.status.set(value[0])
                        self.details = value[1] or value[0]
                    self.rearrange_button.configure(state="normal" if self.manifest else "disabled")
        except queue.Empty:
            pass
        except (tk.TclError, ValueError, OSError, KeyError) as exc:
            self.status.set(str(exc))
        if self.tab.winfo_exists():
            self.app.after(100, self.poll)

    def show_result(self, path):
        record = read_json(path)
        if record.get("schema_version") != 1 or "master_song" not in record:
            raise ValueError("This is not a supported Studio arrangement")
        self.manifest, self.record = path, record
        self.summary.delete(*self.summary.get_children())
        for part in PARTS:
            s = record["summary"][part]
            self.summary.insert("", "end", text=part.title(), values=(s["notes"], "Yes" if s["main_melody"] else "-", s["low_confidence_rejected"], s["simplified"], s["range_shifted"]))
        warnings = record.get("warnings", [])
        assignment = record["melody_assignment"]["part"]
        self.status.set(f"Ready · Main melody: {assignment.title() if assignment else 'not detected'}." +
                        (f" {len(warnings)} quality note(s) in Technical details." if warnings else ""))
        engines = record.get("providers", {}).get("engines", [])
        self.hardware.set("GPU acceleration active" if any(e.get("device") == "cuda" for e in engines) else "CPU mode - conversion will be slower")
        self.details = json.dumps({"quality_notes": warnings, "providers": record.get("providers"),
                                   "melody_assignment": record["melody_assignment"]}, indent=2, ensure_ascii=False)
        self.save_button.configure(state="normal")
        self.use_button.configure(state="normal")
        self.rearrange_button.configure(state="normal")

    def open_arrangement(self):
        if self.busy:
            return
        selected = filedialog.askopenfilename(parent=self.app, title="Open arrangement", filetypes=[("Studio Arrangement", "*.json")])
        if selected:
            try:
                self.show_result(Path(selected))
            except (OSError, ValueError, KeyError) as exc:
                self.status.set(str(exc))

    def audition(self, parts):
        if not self.record:
            self.status.set("Convert or open an arrangement to preview it.")
            return
        try:
            self.preview.play(self.record, {p for p in parts if not self.mutes[p].get()},
                              lambda error: self.events.put(("progress", error)))
        except (RuntimeError, KeyError, ValueError) as exc:
            self.status.set(str(exc))

    def save(self):
        if not self.manifest:
            return
        folder = filedialog.askdirectory(parent=self.app, title="Export four parts, Full Band and Arrangement.json")
        if folder:
            try:
                destination = copy_export(self.manifest, Path(folder))
                self.status.set("Exported: " + str(destination))
            except (OSError, ValueError) as exc:
                self.status.set(str(exc))

    def use(self):
        if self.manifest and self.record:
            name = self.record["files"]["full"]
            if Path(name).name != name:
                self.status.set("Invalid arrangement filename")
                return
            self.app.file_var.set(str(self.manifest.parent / name))
            self.app._schedule_analysis(20)
            self.app.status_var.set("Full Band loaded. Select your Band part, then use the normal BPSR playback controls.")

    def show_details(self):
        window = tk.Toplevel(self.workspace)
        window.title("Audio conversion details")
        text = tk.Text(window, width=100, height=30, wrap="word")
        text.pack(fill="both", expand=True)
        text.insert("1.0", self.details or "No conversion details yet.")
        text.configure(state="disabled")

    def advanced(self):
        window = tk.Toplevel(self.workspace)
        window.title("Audio → Band · Advanced")
        content = ttk.Frame(window, padding=14)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="Models download into separate runtimes on first use. Downloads may be several GB.", wraplength=650).pack(anchor="w")
        ttk.Checkbutton(content, text="Install missing recommended models automatically", variable=self.install).pack(anchor="w", pady=4)
        ttk.Checkbutton(content, text="Independent musical cross-check", variable=self.cross_check).pack(anchor="w")
        ttk.Combobox(content, textvariable=self.device, values=("auto", "cpu", "cuda"), state="readonly", width=12).pack(anchor="w", pady=6)
        for part in self.tiers:
            row = ttk.Frame(content)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=part.title()+" category", width=20).pack(side="left")
            values = ("tier1", "tier2", "tier3", "tier4") if part == "piano" else ("tier1", "tier2", "tier3") if part == "guitar" else ("tier1", "tier2")
            ttk.Combobox(row, textvariable=self.tiers[part], values=values, state="readonly", width=10).pack(side="left")
        for row in self.pipeline.runtimes.statuses():
            ttk.Label(content, text=f"{row['runtime']}: {row['status']}").pack(anchor="w")
        ttk.Label(content, text="Standard: Demucs 6 stems. HQ: BS-RoFormer vocals, then Demucs instruments. Piano: Transkun V2. Beat: Beat This! Cross-check: MR-MT3.\nADTOF is a user-installed option; its port has no declared license. HQ weights and optional engines are downloaded separately, not included in this executable.", wraplength=650, justify="left").pack(anchor="w", pady=8)
        def install():
            requested_device = self.device.get()
            window.destroy()
            def work():
                info = detect_hardware()
                for name in ("separator", "piano", "beat", "mt3"):
                    self.pipeline.runtimes.install(name, device="cuda" if info.cuda and requested_device != "cpu" else "cpu",
                                                   cancel=self.cancel, progress=lambda x: self.events.put(("progress", x)))
                self.events.put(("progress", "Recommended model runtimes are ready. Models load when first used."))
                return None
            self.start(work)
        ttk.Button(content, text="Install recommended runtimes", command=install).pack(anchor="w", pady=4)
        repair_row = ttk.Frame(content)
        repair_row.pack(anchor="w", pady=4)
        repair_name = tk.StringVar(window, value="separator")
        ttk.Combobox(repair_row, textvariable=repair_name, values=tuple(RUNTIMES), state="readonly", width=12).pack(side="left")
        def repair():
            name, device = repair_name.get(), self.device.get()
            window.destroy()
            self.start(lambda: self.pipeline.runtimes.install(name, device=device, repair=True, cancel=self.cancel,
                                                              progress=lambda x: self.events.put(("progress", x))))
        ttk.Button(repair_row, text="Install / repair selected", command=repair).pack(side="left", padx=6)
        ttk.Button(content, text="Drum mapping", command=self.edit_drums).pack(anchor="w", pady=4)

    def edit_drums(self):
        window = tk.Toplevel(self.app)
        window.title("BPSR drum mapping · provisional")
        target = self.pipeline.runtimes.root / "profiles" / "bpsr_drums.json"
        profile = load_drum_profile(target if target.exists() else None)
        ttk.Label(window, text="Pad range C4-B5 is verified; the semantic mapping still needs in-game calibration.", padding=8).pack()
        text = tk.Text(window, width=85, height=25)
        text.pack(fill="both", expand=True)
        text.insert("1.0", json.dumps(profile, indent=2))
        def save():
            try:
                value = json.loads(text.get("1.0", "end"))
                temporary = target.with_suffix(".candidate.json")
                atomic_json(temporary, value)
                try:
                    load_drum_profile(temporary)
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
                window.destroy()
                self.status.set("Drum mapping saved. Apply melody / category re-exports using the new mapping.")
            except (OSError, ValueError, KeyError) as exc:
                messagebox.showerror("Invalid drum profile", str(exc), parent=window)
        ttk.Button(window, text="Save mapping", command=save).pack(pady=8)

    def close(self):
        self.cancel.set()
        self.preview.stop()


def install_band_audio(app_module):
    cls = app_module.App
    if getattr(cls, "_studio_band_audio_installed", False):
        return
    original = cls._build_ui
    def build_ui(self):
        original(self)
        self._studio_band_audio = BandAudioTab(self)
    cls._build_ui = build_ui
    import studio_ui
    original_changed = studio_ui._source_tab_changed
    def source_changed(app):
        audio = getattr(app, "_studio_band_audio", None)
        if audio and app.song_source_notebook.select() == str(audio.tab):
            app.song_source_var.set("audio_band")
            import online_ui
            online_ui._resize_source_notebook(app)
            return
        original_changed(app)
    studio_ui._source_tab_changed = source_changed
    cls._studio_band_audio_installed = True
