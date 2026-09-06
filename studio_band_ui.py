"""Studio-only Audio → Band Accurate tab, with optional engine controls tucked away."""
from __future__ import annotations

import json
import os
import queue
import threading
import time
import tkinter as tk
import webbrowser
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from studio_band.arrange import ArrangementSettings, PARTS, load_drum_profile
from studio_band.export import copy_export
from studio_band.pipeline import BandPipeline, ConversionSettings
from studio_band.preview import PreviewPlayer
from studio_band.progress import ProgressEvent, as_progress_event, progress_context, progress_line
from studio_band.protocol import Cancelled, RuntimeSetupError, StageError
from studio_band.resolver import MusicResolver, ResolverConfig, ResolverTrack, SearchReport
from studio_band.runtime import RUNTIMES, detect_hardware
from studio_band.storage import atomic_json, read_json


def _fit_toplevel(window, preferred_width: int, preferred_height: int,
                  minimum_width: int = 640, minimum_height: int = 480) -> str:
    """Keep a dialog inside a small desktop, leaving room for Windows chrome."""
    screen_width = max(320, window.winfo_screenwidth())
    screen_height = max(300, window.winfo_screenheight())
    width = min(preferred_width, max(320, screen_width - 40))
    height = min(preferred_height, max(300, screen_height - 100))
    x = max(0, (screen_width - width) // 2)
    y = max(0, (screen_height - height) // 3)
    geometry = f"{width}x{height}+{x}+{y}"
    window.geometry(geometry)
    window.minsize(min(minimum_width, width), min(minimum_height, height))
    return geometry


def _scrollable_body(window, padding=14):
    """Create a vertically scrollable themed body and preserve nested widget wheels."""
    shell = ttk.Frame(window)
    shell.pack(fill="both", expand=True)
    background = ttk.Style(window).lookup("TFrame", "background") or window.cget("background")
    canvas = tk.Canvas(shell, borderwidth=0, highlightthickness=0, background=background)
    scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    body = ttk.Frame(canvas, padding=padding)
    body_id = canvas.create_window((0, 0), window=body, anchor="nw")

    def refresh(_event=None):
        bounds = canvas.bbox("all")
        if bounds:
            canvas.configure(scrollregion=bounds)

    body.bind("<Configure>", refresh, add="+")
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(body_id, width=event.width), add="+")

    def wheel(event):
        try:
            widget_class = event.widget.winfo_class()
        except (AttributeError, tk.TclError):
            widget_class = ""
        if widget_class in {"Treeview", "Text", "Listbox", "TCombobox", "TSpinbox", "Spinbox"}:
            return None
        delta = getattr(event, "delta", 0)
        if delta:
            steps = -int(delta / 120) or (-1 if delta > 0 else 1)
        elif getattr(event, "num", None) == 4:
            steps = -1
        elif getattr(event, "num", None) == 5:
            steps = 1
        else:
            return None
        canvas.yview_scroll(steps, "units")
        return "break"

    window.bind("<MouseWheel>", wheel, add="+")
    window.bind("<Button-4>", wheel, add="+")
    window.bind("<Button-5>", wheel, add="+")
    window.after_idle(refresh)
    return canvas, body, scrollbar


def _job_error(exc: Exception, task: str) -> dict[str, object]:
    cancelled = isinstance(exc, Cancelled)
    if cancelled:
        summary = str(exc)
        heading = "Cancelled"
    elif isinstance(exc, RuntimeSetupError):
        summary = f"Conversion/setup failed · {exc.message}"
        heading = "Runtime setup failed"
    elif isinstance(exc, StageError):
        summary = f"{task.title()} failed · {exc.message}"
        heading = f"{exc.stage} failed"
    else:
        summary = f"{task.title()} failed · {str(exc) or type(exc).__name__}"
        heading = "Unexpected failure"
    details = getattr(exc, "details", "") or str(exc)
    technical = json.dumps(
        {
            "summary": summary,
            "stage": getattr(exc, "stage", task),
            "exception": type(exc).__name__,
            "retryable": bool(getattr(exc, "retryable", True)),
        },
        indent=2,
        ensure_ascii=False,
    )
    if details:
        technical += "\n\nTechnical log\n-------------\n" + str(details)
    return {"summary": summary, "heading": heading, "technical": technical, "cancelled": cancelled}


class BandAudioTab:
    def __init__(self, app):
        self.app, self.pipeline = app, BandPipeline()
        self.resolver_config = ResolverConfig.from_environment()
        self.resolver = MusicResolver(self.resolver_config)
        self.events, self.cancel, self.preview = queue.Queue(), threading.Event(), PreviewPlayer()
        self.busy, self.manifest, self.record, self.details = False, None, None, ""
        self.active_task, self.acquired_path, self.source_metadata = "", None, None
        self.job_thread, self.job_started_at, self.last_activity_at = None, 0.0, 0.0
        self.current_progress, self._last_elapsed_second = None, -1
        self.progress_history: list[str] = []
        self.source_setup_window = None
        self.search_results: dict[str, ResolverTrack] = {}
        self.path = tk.StringVar(app)
        self.music_query = tk.StringVar(app)
        self.storefront = tk.StringVar(app, value=self.resolver_config.storefront)
        self.resolver_status = tk.StringVar(app, value=(
            "Search Apple catalogue metadata, your Bandcamp collection, or licensed MassiveMusic. "
            "Local audio above always remains available."
        ))
        self.melody = tk.StringVar(app, value="Auto")
        self.quality = tk.StringVar(app, value="Auto")
        self.device = tk.StringVar(app, value="auto")
        self.cross_check = tk.BooleanVar(app, value=True)
        self.install = tk.BooleanVar(app, value=True)
        self.status = tk.StringVar(app, value="Choose or drop a song to create four playable band parts.")
        self.progress_context_var = tk.StringVar(app, value="Ready")
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
        self.workspace_default_geometry = _fit_toplevel(self.workspace, 980, 780)
        self.workspace.protocol("WM_DELETE_WINDOW", self.hide_workspace)
        # Conversion progress is fixed below the scrollable workspace so the
        # current stage, percentage, elapsed time and Details remain visible at
        # 1280x720 and compact window sizes.
        self.progress_panel = ttk.Frame(self.workspace, padding=(12, 7, 12, 9))
        self.progress_panel.pack(side="bottom", fill="x")
        self.progress_panel.columnconfigure(0, weight=1)
        self.progress_context_label = ttk.Label(
            self.progress_panel, textvariable=self.progress_context_var,
            style="Hint.TLabel", justify="left", wraplength=720,
        )
        self.progress_context_label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.progress_details_button = ttk.Button(
            self.progress_panel, text="Details…", command=self.show_details,
        )
        self.progress_details_button.grid(row=0, column=1, sticky="e")
        self.bar = ttk.Progressbar(self.progress_panel, mode="determinate", maximum=100, value=0)
        self.bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 4))
        self.progress_status_label = ttk.Label(
            self.progress_panel, textvariable=self.status, justify="left", wraplength=720,
        )
        self.progress_status_label.grid(row=2, column=0, columnspan=2, sticky="ew")

        def wrap_progress(event):
            width = max(260, int(event.width) - 115)
            self.progress_context_label.configure(wraplength=width)
            self.progress_status_label.configure(wraplength=max(260, int(event.width) - 20))

        self.progress_panel.bind("<Configure>", wrap_progress, add="+")
        self.workspace_canvas, body, self.workspace_scrollbar = _scrollable_body(self.workspace)
        body.columnconfigure(0, weight=1)
        source = ttk.LabelFrame(body, text="Audio source · local file is always supported", padding=9)
        source.grid(row=0, column=0, sticky="nsew")
        source.columnconfigure(0, weight=1)
        row = ttk.Frame(source)
        row.grid(row=0, column=0, sticky="ew")
        row.columnconfigure(0, weight=1)
        entry = ttk.Entry(row, textvariable=self.path)
        entry.grid(row=0, column=0, sticky="ew")
        self.manual_button = ttk.Button(row, text="Choose local audio…", command=self.browse)
        self.manual_button.grid(row=0, column=1, padx=(6, 0))
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD
            TkinterDnD._require(app)
            entry.drop_target_register(DND_FILES)
            entry.dnd_bind("<<Drop>>", self.drop)
        except (ImportError, RuntimeError, tk.TclError):
            # Elevated Windows apps cannot always receive Explorer file drops;
            # the file picker is always available, including without TkDnD.
            pass
        ttk.Label(source, text="or find an exact track", style="Hint.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 3))
        search = ttk.Frame(source)
        search.grid(row=2, column=0, sticky="ew")
        search.columnconfigure(0, weight=1)
        self.music_search_entry = ttk.Entry(search, textvariable=self.music_query)
        self.music_search_entry.grid(row=0, column=0, sticky="ew")
        self.music_search_entry.bind("<Return>", lambda _event: self.search_music())
        ttk.Combobox(search, textvariable=self.storefront, values=("MY", "ID", "SG", "JP", "US"),
                     state="readonly", width=5).grid(row=0, column=1, padx=(6, 0))
        self.search_button = ttk.Button(search, text="Search music", command=self.search_music)
        self.search_button.grid(row=0, column=2, padx=(6, 0))
        ttk.Button(search, text="Source setup", command=self.source_setup).grid(row=0, column=3, padx=(6, 0))
        results = ttk.Frame(source)
        results.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        results.columnconfigure(0, weight=1)
        self.source_tree = ttk.Treeview(results, columns=("artist", "provider", "availability"),
                                        show="tree headings", height=4, selectmode="browse")
        self.source_tree.heading("#0", text="Track")
        self.source_tree.heading("artist", text="Artist")
        self.source_tree.heading("provider", text="Source")
        self.source_tree.heading("availability", text="Audio")
        self.source_tree.column("#0", width=275, minwidth=150, stretch=True)
        self.source_tree.column("artist", width=190, minwidth=100, stretch=True)
        self.source_tree.column("provider", width=125, minwidth=90, stretch=False)
        self.source_tree.column("availability", width=190, minwidth=140, stretch=False)
        self.source_tree.grid(row=0, column=0, sticky="ew")
        self.source_scrollbar = ttk.Scrollbar(results, orient="vertical", command=self.source_tree.yview)
        self.source_scrollbar.grid(row=0, column=1, sticky="ns")
        self.source_tree.configure(yscrollcommand=self.source_scrollbar.set)
        self.source_tree.bind("<<TreeviewSelect>>", lambda _event: self.source_selected())
        source_actions = ttk.Frame(source)
        source_actions.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        self.acquire_button = ttk.Button(source_actions, text="Acquire & Analyze", command=self.acquire_selected,
                                         state="disabled")
        self.acquire_button.pack(side="left")
        self.open_source_button = ttk.Button(source_actions, text="Open provider", command=self.open_selected_source,
                                             state="disabled")
        self.open_source_button.pack(side="left", padx=6)
        self.resolver_status_label = ttk.Label(source, textvariable=self.resolver_status, style="Hint.TLabel",
                                               wraplength=760, justify="left")
        self.resolver_status_label.grid(row=5, column=0, sticky="ew", pady=(5, 0))
        source.bind("<Configure>", lambda event: self.resolver_status_label.configure(
            wraplength=max(260, event.width - 24)), add="+")
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
        self.summary = ttk.Treeview(body, columns=("notes", "melody", "rejected", "simplified", "shifted"), show="tree headings", height=4)
        self.summary.heading("#0", text="Part")
        self.summary.column("#0", width=100, stretch=True)
        for name, label in (("notes", "Notes / hits"), ("melody", "Melody"), ("rejected", "Low confidence"), ("simplified", "Simplified"), ("shifted", "Range shifted")):
            self.summary.heading(name, text=label)
            self.summary.column(name, width=105, minwidth=65, anchor="center")
        self.summary.grid(row=4, column=0, sticky="ew", pady=8)
        listen = ttk.Frame(body)
        listen.grid(row=5, column=0, sticky="w")
        ttk.Button(listen, text="▶ Full Band", command=lambda: self.audition(set(PARTS))).pack(side="left")
        for part in PARTS:
            ttk.Button(listen, text=part.title(), command=lambda p=part: self.audition({p}), width=8).pack(side="left", padx=3)
        ttk.Button(listen, text="Stop", command=self.preview.stop, width=6).pack(side="left")
        muted = ttk.Frame(body)
        muted.grid(row=6, column=0, sticky="w", pady=3)
        ttk.Label(muted, text="Mute for next preview:").pack(side="left")
        for part in PARTS:
            ttk.Checkbutton(muted, text=part.title(), variable=self.mutes[part]).pack(side="left", padx=4)
        footer = ttk.Frame(body)
        footer.grid(row=7, column=0, sticky="w", pady=(6, 0))
        self.save_button = ttk.Button(footer, text="Export all files", command=self.save, state="disabled")
        self.save_button.pack(side="left")
        self.use_button = ttk.Button(footer, text="Use Full Band in BPSR", command=self.use, state="disabled")
        self.use_button.pack(side="left", padx=6)
        self.tab.bind("<Destroy>", lambda event: self.close() if event.widget is self.tab else None)
        self.app.after(100, self.poll)

        def hardware():
            info = detect_hardware()
            self.events.put(("hardware", "GPU detected · each model checks CUDA support" if info.cuda else "CPU mode - conversion will be slower"))
            self.pipeline.store.cleanup()
            self.resolver.store.cleanup()
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
            self.acquired_path, self.source_metadata = None, None
            self.status.set("Local audio selected. Adjust options, then click Analyze & Convert.")

    def drop(self, event):
        files = self.app.tk.splitlist(event.data)
        if not self.busy and files:
            self.path.set(files[0])
            self.acquired_path, self.source_metadata = None, None
            self.status.set("Local audio selected. Adjust options, then click Analyze & Convert.")
        return event.action

    def _selected_source(self):
        selection = self.source_tree.selection()
        return self.search_results.get(str(selection[0])) if selection else None

    def source_selected(self):
        track = self._selected_source()
        self.acquire_button.configure(state="normal" if track and track.can_acquire and not self.busy else "disabled")
        self.open_source_button.configure(state="normal" if track and track.store_url and not self.busy else "disabled")
        if track:
            self.resolver_status.set(
                "Full audio can be acquired from this entitled account." if track.can_acquire else
                "Discovery only. Open the provider, obtain an authorised file, then choose it locally."
            )

    def _refresh_resolver(self):
        country = self.storefront.get().strip().upper()
        self.resolver_config = replace(self.resolver_config, storefront=country)
        self.resolver = MusicResolver(self.resolver_config, self.resolver.store)

    def search_music(self):
        if self.busy:
            return
        query = self.music_query.get().strip()
        try:
            self._refresh_resolver()
        except ValueError as exc:
            self.resolver_status.set(str(exc))
            return
        self.source_tree.delete(*self.source_tree.get_children())
        self.search_results.clear()
        self.acquire_button.configure(state="disabled")
        self.open_source_button.configure(state="disabled")
        self.resolver_status.set("Searching legal music sources…")
        self.start(lambda: self.resolver.search(query, cancel=self.cancel,
                                                progress=lambda text: self.events.put(("progress", text))),
                   "search_done", "music search")

    def show_search_results(self, report: SearchReport):
        provider_names = {"apple_music": "Apple Music", "apple_catalog": "Apple catalogue",
                          "massive_music": "MassiveMusic", "bandcamp_collection": "Bandcamp collection"}
        availability = {"metadata_only": "Discovery only", "catalogue_only": "Catalogue / purchase",
                        "entitled_partner_download": "Entitled download", "owned_collection_download": "Owned download"}
        for index, track in enumerate(report.tracks):
            iid = f"source:{index}"
            self.search_results[iid] = track
            self.source_tree.insert("", "end", iid=iid, text=track.title,
                                    values=(track.artist or "—", provider_names.get(track.provider, track.provider),
                                            availability.get(track.acquisition, track.acquisition)))
        warning = f" {len(report.warnings)} setup note(s); see Technical details." if report.warnings else ""
        self.resolver_status.set(f"Found {len(report.tracks)} result(s). Select one.{warning}")
        if report.warnings:
            self.details = json.dumps({"music_source_notes": report.warnings}, indent=2, ensure_ascii=False)

    def open_selected_source(self):
        track = self._selected_source()
        if not track or not track.store_url:
            self.resolver_status.set("This result has no safe provider page.")
            return
        try:
            opened = bool(webbrowser.open(track.store_url, new=2, autoraise=True))
        except webbrowser.Error:
            opened = False
        self.resolver_status.set("Opened the provider in your browser." if opened else "Could not open your web browser.")

    def acquire_selected(self):
        track = self._selected_source()
        if not track or not track.can_acquire or self.busy:
            self.resolver_status.set("Choose an owned or licensed downloadable result first.")
            return
        allowed = messagebox.askyesno(
            "Confirm audio rights",
            "Only continue if this account owns the track or your licence permits local audio analysis and MIDI conversion.\n\n"
            "Studio will never use an Apple preview or streaming-only audio.",
            parent=self.workspace,
        )
        if not allowed:
            return
        self.start(lambda: self.resolver.acquire(track, cancel=self.cancel,
                                                 progress=lambda text: self.events.put(("progress", text))),
                   "acquired", "audio acquisition")

    def source_setup(self):
        if self.busy:
            return None
        if self.source_setup_window is not None and self.source_setup_window.winfo_exists():
            self.source_setup_window.deiconify()
            self.source_setup_window.lift()
            return self.source_setup_window
        window = tk.Toplevel(self.workspace)
        self.source_setup_window = window
        window.title("Music source setup · session only")
        window.transient(self.workspace)
        _fit_toplevel(window, 720, 520, 520, 400)
        window._scroll_canvas, content, window._scrollbar = _scrollable_body(window)

        def close():
            self.source_setup_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", close)
        intro = ttk.Label(content, text=(
            "Apple is discovery-only. Bandcamp uses your Fan Settings → Subsonic collection. "
            "MassiveMusic requires a commercial partner agreement and an entitled user. "
            "Secrets stay only in memory for this Studio session."
        ), wraplength=670, justify="left")
        intro.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        fields = [
            ("Apple developer token (optional)", "apple_token"),
            ("MassiveMusic consumer key", "massive_consumer_key"),
            ("MassiveMusic consumer secret", "massive_consumer_secret"),
            ("MassiveMusic user ID", "massive_user_id"),
            ("MassiveMusic user token (optional)", "massive_user_token"),
            ("MassiveMusic token secret (optional)", "massive_user_token_secret"),
            ("Bandcamp Subsonic username", "bandcamp_username"),
            ("Bandcamp Subsonic password", "bandcamp_password"),
            ("Bandcamp OpenSubsonic API key", "bandcamp_api_key"),
        ]
        values = {}
        for row, (label, name) in enumerate(fields, 1):
            ttk.Label(content, text=label).grid(row=row, column=0, sticky="w", pady=3)
            value = tk.StringVar(window, value=getattr(self.resolver_config, name))
            values[name] = value
            secret = any(word in name for word in ("token", "secret", "password", "api_key"))
            ttk.Entry(content, textvariable=value, show="•" if secret else "").grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=3)
        content.columnconfigure(1, weight=1)
        environment_note = ttk.Label(content, text=(
            "For repeat use, set the matching BPSR_APPLE_MUSIC_*, BPSR_MASSIVEMUSIC_* or "
            "BPSR_BANDCAMP_* environment variables. Credentials are never written to Arrangement.json."
        ), style="Hint.TLabel", wraplength=670, justify="left")
        environment_note.grid(row=len(fields)+1, column=0, columnspan=2, sticky="ew", pady=(10, 6))
        content.bind("<Configure>", lambda event: (
            intro.configure(wraplength=max(260, event.width - 28)),
            environment_note.configure(wraplength=max(260, event.width - 28))), add="+")

        def apply():
            try:
                self.resolver_config = ResolverConfig(storefront=self.storefront.get(),
                                                       **{name: value.get().strip() for name, value in values.items()})
                self.resolver = MusicResolver(self.resolver_config, self.resolver.store)
            except ValueError as exc:
                messagebox.showerror("Invalid music source setup", str(exc), parent=window)
                return
            close()
            self.resolver_status.set("Music source setup applied for this Studio session.")
        actions = ttk.Frame(content)
        actions.grid(row=len(fields)+2, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Button(actions, text="Apply for this session", command=apply).pack(side="left")
        ttk.Button(actions, text="Cancel", command=close).pack(side="left", padx=6)
        return window

    def arrangement_settings(self):
        return ArrangementSettings(self.melody.get().lower(), {p:v.get() for p,v in self.tiers.items()})

    def _render_progress(self, *, force: bool = False):
        if self.current_progress is None or not self.job_started_at:
            return
        elapsed = max(0.0, time.monotonic() - self.job_started_at)
        second = int(elapsed)
        if not force and second == self._last_elapsed_second:
            return
        self._last_elapsed_second = second
        self.status.set(progress_line(self.current_progress, elapsed))
        self.progress_context_var.set(progress_context(self.current_progress))

    def _accept_progress(self, value):
        event = as_progress_event(value)
        self.current_progress = event
        self.last_activity_at = time.monotonic()
        elapsed = max(0.0, self.last_activity_at - self.job_started_at) if self.job_started_at else 0.0
        self.progress_history.append(f"{elapsed:8.1f}s  {event.message}")
        self.progress_history = self.progress_history[-200:]
        if event.overall is not None:
            self.bar.stop()
            self.bar.configure(mode="determinate", maximum=100, value=event.overall)
        elif self.busy:
            self.bar.configure(mode="indeterminate", maximum=100, value=0)
            self.bar.start(12)
        self._render_progress(force=True)

    def request_cancel(self):
        if not self.busy:
            return
        self.cancel.set()
        self.cancel_button.configure(state="disabled")
        overall = getattr(self.current_progress, "overall", None)
        self.current_progress = ProgressEvent(
            "Cancelling safely", phase="Cancelling", activity="waiting", overall=overall,
            indeterminate=True,
        )
        self._render_progress(force=True)

    def _restore_controls(self, *, retry: bool = False, cancelled: bool = False):
        self.busy = False
        self.bar.stop()
        self.cancel_button.configure(state="disabled")
        idle_text = getattr(self, "_convert_idle_text", "Analyze & Convert")
        self.convert_button.configure(state="normal", text="Retry conversion" if retry and not cancelled else idle_text)
        self.search_button.configure(state="normal")
        self.rearrange_button.configure(state="normal" if self.manifest else "disabled")
        self.source_selected()

    def start(self, action, success_kind="done", task="conversion"):
        if self.busy:
            return
        self.busy = True
        self.active_task = task
        self.cancel = threading.Event()
        current_button_text = str(self.convert_button.cget("text"))
        if current_button_text != "Retry conversion":
            self._convert_idle_text = current_button_text
        self.job_started_at = self.last_activity_at = time.monotonic()
        self._last_elapsed_second = -1
        self.progress_history = []
        self.preview.stop()
        self.convert_button.configure(state="disabled")
        self.rearrange_button.configure(state="disabled")
        self.search_button.configure(state="disabled")
        self.acquire_button.configure(state="disabled")
        self.open_source_button.configure(state="disabled")
        self.cancel_button.configure(command=self.request_cancel, state="normal")
        if task == "conversion":
            self._accept_progress(ProgressEvent(
                "Checking runtime components", stage_id="runtime_setup", phase="Preparing conversion",
                activity="check", overall=0, stage_fraction=0.0, indeterminate=True,
            ))
        else:
            self._accept_progress(ProgressEvent(
                task.title(), phase=task.title(), activity="processing", indeterminate=True,
            ))
        def worker():
            try:
                self.events.put((success_kind, action()))
            except Exception as exc:
                self.events.put(("error", _job_error(exc, task)))
        self.job_thread = threading.Thread(target=worker, daemon=True, name="studio-band-job")
        self.job_thread.start()

    def convert(self):
        source = Path(self.path.get().strip().strip('"'))
        metadata = self.source_metadata if self.acquired_path and source == self.acquired_path else None
        settings = ConversionSettings(self.quality.get().lower(), self.device.get(), self.install.get(),
                                      self.cross_check.get(), self.arrangement_settings())
        self.start(lambda: self.pipeline.convert(source, settings, cancel=self.cancel, source_metadata=metadata,
                                                 progress=lambda text: self.events.put(("progress", text))),
                   "done", "conversion")

    def rearrange(self):
        if self.manifest:
            settings, manifest = self.arrangement_settings(), self.manifest
            self.status.set("Re-arranging cached musical evidence…")
            self.start(lambda: self.pipeline.rearrange(manifest, settings), task="rearrangement")

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "hardware":
                    self.hardware.set(value)
                elif kind == "progress":
                    self._accept_progress(value)
                elif kind in {"done", "error", "search_done", "acquired"}:
                    error = value if kind == "error" else None
                    cancelled = bool(error and error.get("cancelled"))
                    self._restore_controls(retry=kind == "error" and self.active_task == "conversion",
                                           cancelled=cancelled)
                    if kind == "done":
                        self.bar.configure(mode="determinate", maximum=100, value=100)
                        self.progress_context_var.set("Complete — the requested work finished.")
                        if value:
                            self.show_result(Path(value))
                    elif kind == "search_done":
                        self.bar.configure(mode="determinate", maximum=100, value=0)
                        self.progress_context_var.set("Ready")
                        self.show_search_results(value)
                    elif kind == "acquired":
                        self.bar.configure(mode="determinate", maximum=100, value=0)
                        self.acquired_path, self.source_metadata = Path(value.path), value.metadata
                        self.path.set(str(value.path))
                        self.resolver_status.set("Authorised audio acquired and checksum-cached. Starting Audio → Band…")
                        self.app.after(10, self.convert)
                    elif kind == "error":
                        self.status.set(str(error["summary"]))
                        self.progress_context_var.set(
                            "Cancelled — completed analysis remains cached." if cancelled else
                            "Failed — open Details for the technical log. Controls are ready to retry."
                        )
                        if self.active_task in {"music search", "audio acquisition"}:
                            self.resolver_status.set(str(error["summary"]))
                        history = "\n".join(self.progress_history)
                        self.details = str(error["technical"]) + ("\n\nProgress history\n----------------\n" + history if history else "")
        except queue.Empty:
            pass
        except (tk.TclError, ValueError, OSError, KeyError) as exc:
            self.status.set(str(exc))
        if self.busy:
            self._render_progress()
            if self.job_thread is not None and not self.job_thread.is_alive() and self.events.empty():
                failure = _job_error(RuntimeError("The background job stopped without returning a result."), self.active_task)
                self.events.put(("error", failure))
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
                        (f" {len(warnings)} quality note(s) in Details." if warnings else ""))
        self.progress_context_var.set("Complete — 100%. The arrangement is ready to preview or export.")
        engines = record.get("providers", {}).get("engines", [])
        self.hardware.set("GPU acceleration active" if any(e.get("device") == "cuda" for e in engines) else "CPU mode - conversion will be slower")
        self.details = json.dumps({"audio_source": record.get("source"), "quality_notes": warnings, "providers": record.get("providers"),
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
        window.transient(self.workspace)
        _fit_toplevel(window, 780, 520, 480, 340)
        content = ttk.Frame(window, padding=10)
        content.pack(fill="both", expand=True)
        text = tk.Text(content, width=80, height=24, wrap="word")
        scrollbar = ttk.Scrollbar(content, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        text.insert("1.0", self.details or "No conversion details yet.")
        text.configure(state="disabled")

    def advanced(self):
        window = tk.Toplevel(self.workspace)
        window.title("Audio → Band · Advanced")
        window.transient(self.workspace)
        _fit_toplevel(window, 720, 560, 520, 400)
        window._scroll_canvas, content, window._scrollbar = _scrollable_body(window)
        intro = ttk.Label(content, text="Models download into separate runtimes on first use. Downloads may be several GB.", wraplength=650)
        intro.pack(anchor="w")
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
        engine_note = ttk.Label(content, text="Standard: Demucs 6 stems. HQ: BS-RoFormer vocals, then Demucs instruments. Piano: Transkun V2. Beat: Beat This! Cross-check: MR-MT3.\nADTOF is a user-installed option; its port has no declared license. HQ weights and optional engines are downloaded separately, not included in this executable.", wraplength=650, justify="left")
        engine_note.pack(anchor="w", pady=8)
        content.bind("<Configure>", lambda event: (
            intro.configure(wraplength=max(260, event.width - 28)),
            engine_note.configure(wraplength=max(260, event.width - 28))), add="+")
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
            self.start(work, task="runtime setup")
        ttk.Button(content, text="Install recommended runtimes", command=install).pack(anchor="w", pady=4)
        repair_row = ttk.Frame(content)
        repair_row.pack(anchor="w", pady=4)
        repair_name = tk.StringVar(window, value="separator")
        ttk.Combobox(repair_row, textvariable=repair_name, values=tuple(RUNTIMES), state="readonly", width=12).pack(side="left")
        def repair():
            name, device = repair_name.get(), self.device.get()
            window.destroy()
            self.start(lambda: self.pipeline.runtimes.install(name, device=device, repair=True, cancel=self.cancel,
                                                              progress=lambda x: self.events.put(("progress", x))),
                       task="runtime setup")
        ttk.Button(repair_row, text="Install / repair selected", command=repair).pack(side="left", padx=6)
        ttk.Button(content, text="Drum mapping", command=self.edit_drums).pack(anchor="w", pady=4)

    def edit_drums(self):
        window = tk.Toplevel(self.app)
        window.title("BPSR drum mapping · provisional")
        window.transient(self.workspace)
        _fit_toplevel(window, 760, 560, 480, 360)
        target = self.pipeline.runtimes.root / "profiles" / "bpsr_drums.json"
        profile = load_drum_profile(target if target.exists() else None)
        content = ttk.Frame(window, padding=8)
        content.pack(fill="both", expand=True)
        note = ttk.Label(content, text="Pad range C4-B5 is verified; the semantic mapping still needs in-game calibration.", wraplength=700)
        note.pack(anchor="w", pady=(0, 6))
        editor = ttk.Frame(content)
        editor.pack(fill="both", expand=True)
        text = tk.Text(editor, width=75, height=22, wrap="none")
        yscroll = ttk.Scrollbar(editor, orient="vertical", command=text.yview)
        xscroll = ttk.Scrollbar(editor, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        editor.rowconfigure(0, weight=1)
        editor.columnconfigure(0, weight=1)
        content.bind("<Configure>", lambda event: note.configure(wraplength=max(260, event.width - 20)), add="+")
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
        ttk.Button(content, text="Save mapping", command=save).pack(anchor="w", pady=(8, 0))

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
