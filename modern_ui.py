from __future__ import annotations

from tkinter import ttk
from typing import Any


def _apply_modern_styles(app: Any) -> None:
    """Apply a compact Fluent-inspired style using the app's current light/dark mode."""
    style = app._style
    dark = bool(app._dark_mode)

    background = "#111827" if dark else "#F4F6F8"
    surface = "#1F2937" if dark else "#FFFFFF"
    surface_alt = "#273449" if dark else "#F8FAFC"
    foreground = "#F8FAFC" if dark else "#172033"
    muted = "#AAB4C3" if dark else "#667085"
    border = "#37465D" if dark else "#D8DEE8"
    accent = "#60A5FA" if dark else "#2563EB"
    accent_hover = "#7DB6FB" if dark else "#1D4ED8"
    danger = "#F87171" if dark else "#C24141"
    danger_hover = "#FB8B8B" if dark else "#A93434"

    app.configure(background=background)

    style.configure("Modern.TFrame", background=background)
    style.configure("Surface.TFrame", background=surface)
    style.configure("SurfaceAlt.TFrame", background=surface_alt)

    style.configure(
        "Card.TLabelframe",
        background=surface,
        bordercolor=border,
        relief="solid",
        borderwidth=1,
        padding=12,
    )
    style.configure(
        "Card.TLabelframe.Label",
        background=surface,
        foreground=foreground,
        font=("Segoe UI Semibold", 11),
        padding=(0, 0, 0, 6),
    )

    style.configure(
        "ModernTitle.TLabel",
        background=background,
        foreground=foreground,
        font=("Segoe UI Semibold", 22),
    )
    style.configure(
        "ModernSubtitle.TLabel",
        background=background,
        foreground=muted,
        font=("Segoe UI", 10),
    )
    style.configure(
        "ModernVersion.TLabel",
        background=surface_alt,
        foreground=muted,
        font=("Segoe UI Semibold", 9),
        padding=(8, 4),
    )
    style.configure(
        "CardText.TLabel",
        background=surface,
        foreground=foreground,
        font=("Segoe UI", 10),
    )
    style.configure(
        "CardMuted.TLabel",
        background=surface,
        foreground=muted,
        font=("Segoe UI", 9),
    )
    style.configure(
        "InfoStrip.TLabel",
        background=surface_alt,
        foreground=foreground,
        font=("Segoe UI", 10),
        padding=(14, 10),
    )
    style.configure(
        "Footer.TLabel",
        background=background,
        foreground=muted,
        font=("Segoe UI", 9),
    )

    style.configure(
        "Primary.TButton",
        background=accent,
        foreground="#FFFFFF",
        bordercolor=accent,
        focusthickness=0,
        padding=(18, 10),
        font=("Segoe UI Semibold", 10),
    )
    style.map(
        "Primary.TButton",
        background=[("active", accent_hover), ("disabled", border)],
        foreground=[("disabled", muted)],
        bordercolor=[("active", accent_hover), ("disabled", border)],
    )
    style.configure(
        "Danger.TButton",
        background=danger,
        foreground="#FFFFFF",
        bordercolor=danger,
        focusthickness=0,
        padding=(14, 10),
        font=("Segoe UI Semibold", 10),
    )
    style.map(
        "Danger.TButton",
        background=[("active", danger_hover), ("disabled", border)],
        foreground=[("disabled", muted)],
        bordercolor=[("active", danger_hover), ("disabled", border)],
    )
    style.configure(
        "Utility.TButton",
        padding=(10, 7),
        font=("Segoe UI", 9),
    )
    style.configure(
        "Modern.Horizontal.TProgressbar",
        troughcolor=surface_alt,
        background=accent,
        bordercolor=surface_alt,
        lightcolor=accent,
        darkcolor=accent,
        thickness=8,
    )


def _field_label(parent: Any, text: str, row: int, column: int = 0, **grid: Any) -> None:
    ttk.Label(parent, text=text, style="CardMuted.TLabel").grid(
        row=row,
        column=column,
        sticky="w",
        pady=(0, 5),
        **grid,
    )


def _modern_build_custom_settings(self: Any, settings: Any) -> None:
    settings.columnconfigure(0, weight=1)

    ttk.Label(
        settings,
        text="Advanced controls. Fixed profiles are recommended for most songs.",
        style="CardMuted.TLabel",
        wraplength=520,
        justify="left",
    ).grid(row=0, column=0, sticky="w", pady=(0, 10))

    tabs = ttk.Notebook(settings)
    tabs.grid(row=1, column=0, sticky="nsew")

    notes_tab = ttk.Frame(tabs, style="Surface.TFrame", padding=12)
    timing_tab = ttk.Frame(tabs, style="Surface.TFrame", padding=12)
    tabs.add(notes_tab, text="Notes")
    tabs.add(timing_tab, text="Timing")

    notes_tab.columnconfigure(0, weight=1)
    notes_tab.columnconfigure(1, weight=1)

    _field_label(notes_tab, "Playback mode", 0, 0)
    self.mode_combo = ttk.Combobox(
        notes_tab,
        textvariable=self.mode_var,
        values=list(self._modern_module.MODE_LABELS),
        state="readonly",
    )
    self.mode_combo.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))

    _field_label(notes_tab, "Unlocked range", 2, 0, padx=(0, 7))
    _field_label(notes_tab, "Chord detail", 2, 1, padx=(7, 0))
    self.unlock_combo = ttk.Combobox(
        notes_tab,
        textvariable=self.unlock_var,
        values=list(self._modern_module.UNLOCK_LABELS_BY_INSTRUMENT["keyboard"]),
        state="readonly",
    )
    self.unlock_combo.grid(row=3, column=0, sticky="ew", padx=(0, 7), pady=(0, 10))
    self.chord_combo = ttk.Combobox(
        notes_tab,
        textvariable=self.chord_var,
        values=list(self._modern_module.STANDARD_CHORD_LABELS),
        state="readonly",
    )
    self.chord_combo.grid(row=3, column=1, sticky="ew", padx=(7, 0), pady=(0, 10))

    _field_label(notes_tab, "Fit unavailable notes", 4, 0)
    self.mapping_combo = ttk.Combobox(
        notes_tab,
        textvariable=self.mapping_var,
        values=list(self._modern_module.MAPPING_LABELS),
        state="readonly",
    )
    self.mapping_combo.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 10))

    checks = ttk.Frame(notes_tab, style="Surface.TFrame")
    checks.grid(row=6, column=0, columnspan=2, sticky="ew")
    ttk.Checkbutton(
        checks,
        text="Ignore drum channel",
        variable=self.percussion_var,
    ).pack(side="left")
    ttk.Checkbutton(
        checks,
        text="Use MIDI sustain pedal",
        variable=self.pedal_var,
    ).pack(side="left", padx=(18, 0))

    timing_tab.columnconfigure(0, weight=1)
    timing_tab.columnconfigure(1, weight=1)

    _field_label(timing_tab, "Page-change wait", 0, 0, padx=(0, 7))
    _field_label(timing_tab, "Ctrl / Shift lead", 0, 1, padx=(7, 0))
    page_wrap = ttk.Frame(timing_tab, style="Surface.TFrame")
    page_wrap.grid(row=1, column=0, sticky="w", padx=(0, 7), pady=(0, 12))
    self.page_delay_spin = ttk.Spinbox(
        page_wrap,
        from_=40,
        to=1000,
        increment=10,
        textvariable=self.page_delay_var,
        width=8,
    )
    self.page_delay_spin.pack(side="left")
    ttk.Label(page_wrap, text="ms", style="CardMuted.TLabel").pack(side="left", padx=(6, 0))

    modifier_wrap = ttk.Frame(timing_tab, style="Surface.TFrame")
    modifier_wrap.grid(row=1, column=1, sticky="w", padx=(7, 0), pady=(0, 12))
    ttk.Spinbox(
        modifier_wrap,
        from_=10,
        to=500,
        increment=5,
        textvariable=self.modifier_lead_var,
        width=8,
    ).pack(side="left")
    ttk.Label(modifier_wrap, text="ms", style="CardMuted.TLabel").pack(side="left", padx=(6, 0))

    timing_values = ttk.Frame(timing_tab, style="Surface.TFrame")
    timing_values.grid(row=2, column=0, columnspan=2, sticky="ew")
    for column in range(3):
        timing_values.columnconfigure(column, weight=1)

    for column, (label, variable, from_value, to_value, suffix) in enumerate(
        (
            ("Speed", self.speed_var, 25, 200, "%"),
            ("Note length", self.length_var, 50, 300, "%"),
            ("Minimum note", self.minimum_note_var, 20, 1000, "ms"),
        )
    ):
        box = ttk.Frame(timing_values, style="Surface.TFrame")
        box.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 7, 0))
        ttk.Label(box, text=label, style="CardMuted.TLabel").pack(anchor="w", pady=(0, 5))
        value_row = ttk.Frame(box, style="Surface.TFrame")
        value_row.pack(anchor="w")
        ttk.Spinbox(
            value_row,
            from_=from_value,
            to=to_value,
            textvariable=variable,
            width=7,
        ).pack(side="left")
        ttk.Label(value_row, text=suffix, style="CardMuted.TLabel").pack(side="left", padx=(5, 0))

def _modern_build_ui(self: Any) -> None:
    self._apply_system_theme(force=True)
    self.geometry("1040x920")
    self.minsize(920, 740)

    outer = ttk.Frame(self, style="Modern.TFrame", padding=(22, 18, 22, 14))
    outer.pack(fill="both", expand=True)

    header = ttk.Frame(outer, style="Modern.TFrame")
    header.pack(fill="x", pady=(0, 16))
    title_group = ttk.Frame(header, style="Modern.TFrame")
    title_group.pack(side="left", fill="x", expand=True)
    ttk.Label(title_group, text=self._modern_module.APP_NAME, style="ModernTitle.TLabel").pack(anchor="w")
    ttk.Label(
        title_group,
        text="Play MIDI through Keyboard, Guitar, or Bass in Blue Protocol: Star Resonance",
        style="ModernSubtitle.TLabel",
    ).pack(anchor="w", pady=(3, 0))
    ttk.Label(
        header,
        text=f"v{self._modern_module.APP_VERSION}",
        style="ModernVersion.TLabel",
    ).pack(side="right", anchor="n", pady=(4, 0))

    ttk.Label(
        outer,
        textvariable=self.notice_var,
        style="InfoStrip.TLabel",
        wraplength=970,
        justify="left",
    ).pack(fill="x", pady=(0, 16))

    content = ttk.Frame(outer, style="Modern.TFrame")
    content.pack(fill="both", expand=True)
    content.columnconfigure(0, weight=3)
    content.columnconfigure(1, weight=2)
    content.rowconfigure(0, weight=1)

    left = ttk.Frame(content, style="Modern.TFrame")
    left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
    right = ttk.Frame(content, style="Modern.TFrame")
    right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

    setup = ttk.LabelFrame(left, text="Instrument setup", style="Card.TLabelframe")
    setup.pack(fill="x", pady=(0, 12))
    setup.columnconfigure(0, weight=1)
    setup.columnconfigure(1, weight=1)

    _field_label(setup, "Instrument", 0, 0, padx=(0, 8))
    _field_label(setup, "Unlock profile", 0, 1, padx=(8, 0))
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
        style="CardMuted.TLabel",
        wraplength=560,
        justify="left",
    ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))

    library = ttk.LabelFrame(left, text="Song library", style="Card.TLabelframe")
    library.pack(fill="x", pady=(0, 12))
    library.columnconfigure(0, weight=1)
    _field_label(library, "Selected MIDI", 0, 0)
    self.midi_combo = ttk.Combobox(
        library,
        textvariable=self.midi_display_var,
        state="readonly",
        values=(),
    )
    self.midi_combo.grid(row=1, column=0, columnspan=3, sticky="ew")
    self.midi_combo.bind("<<ComboboxSelected>>", lambda _event: self._midi_selected())

    tools = ttk.Frame(library, style="Surface.TFrame")
    tools.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
    ttk.Button(
        tools,
        text="Open MIDI folder",
        style="Utility.TButton",
        command=self._open_midi_folder,
    ).pack(side="left")
    ttk.Button(
        tools,
        text="Refresh",
        style="Utility.TButton",
        command=self._reload_midi_library,
    ).pack(side="left", padx=(8, 0))
    ttk.Button(
        tools,
        text="Find songs online",
        style="Utility.TButton",
        command=self._open_online_sequencer,
    ).pack(side="right")
    ttk.Label(
        library,
        text="Best results: simple piano, melody, or solo-instrument MIDI files.",
        style="CardMuted.TLabel",
        wraplength=560,
        justify="left",
    ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(10, 0))

    self.custom_settings_frame = ttk.LabelFrame(
        left,
        text="Custom profile",
        style="Card.TLabelframe",
    )
    self._build_custom_settings(self.custom_settings_frame)

    playback = ttk.LabelFrame(right, text="Playback", style="Card.TLabelframe")
    playback.pack(fill="x", pady=(0, 12))
    playback.columnconfigure(0, weight=1)
    playback.columnconfigure(1, weight=1)

    _field_label(playback, "Countdown", 0, 0, padx=(0, 8))
    _field_label(playback, "Keyboard input", 0, 1, padx=(8, 0))
    delay_row = ttk.Frame(playback, style="Surface.TFrame")
    delay_row.grid(row=1, column=0, sticky="w", padx=(0, 8))
    ttk.Spinbox(
        delay_row,
        from_=0,
        to=30,
        increment=0.5,
        textvariable=self.start_delay_var,
        width=7,
    ).pack(side="left")
    ttk.Label(delay_row, text="seconds", style="CardMuted.TLabel").pack(side="left", padx=(6, 0))
    self.input_backend_combo = ttk.Combobox(
        playback,
        textvariable=self.input_backend_var,
        values=list(self._modern_module.INPUT_BACKEND_LABELS),
        state="readonly",
    )
    self.input_backend_combo.grid(row=1, column=1, sticky="ew", padx=(8, 0))
    self.input_backend_combo.bind(
        "<<ComboboxSelected>>", lambda _event: self._save_config()
    )

    ttk.Checkbutton(
        playback,
        text="Minimize app after Play",
        variable=self.minimize_var,
        command=self._save_config,
    ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(14, 0))

    action_row = ttk.Frame(playback, style="Surface.TFrame")
    action_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(16, 0))
    action_row.columnconfigure(0, weight=1)
    action_row.columnconfigure(1, weight=1)
    self.start_button = ttk.Button(
        action_row,
        text="Play",
        style="Primary.TButton",
        command=self._start,
    )
    self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
    self.stop_button = ttk.Button(
        action_row,
        text="Stop  ·  F10",
        style="Danger.TButton",
        command=self._stop,
        state="disabled",
    )
    self.stop_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))

    self.progress = ttk.Progressbar(
        playback,
        maximum=1.0,
        mode="determinate",
        style="Modern.Horizontal.TProgressbar",
    )
    self.progress.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(18, 8))
    ttk.Label(
        playback,
        textvariable=self.status_var,
        style="CardText.TLabel",
        wraplength=350,
        justify="left",
    ).grid(row=5, column=0, columnspan=2, sticky="w")

    ttk.Separator(playback).grid(row=6, column=0, columnspan=2, sticky="ew", pady=16)
    ttk.Label(
        playback,
        text="Keep BPSR focused while the song is playing. F10 stops playback and releases all keys.",
        style="CardMuted.TLabel",
        wraplength=350,
        justify="left",
    ).grid(row=7, column=0, columnspan=2, sticky="w")
    ttk.Button(
        playback,
        text="Restore defaults",
        style="Utility.TButton",
        command=self._reset_defaults,
    ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(14, 0))

    self.analysis_frame = ttk.LabelFrame(right, text="Song check", style="Card.TLabelframe")
    self.analysis_frame.pack(fill="x")
    self.suitability_label = ttk.Label(
        self.analysis_frame,
        textvariable=self.suitability_var,
        style="Good.TLabel",
    )
    self.suitability_label.pack(anchor="w", pady=(0, 6))
    ttk.Label(
        self.analysis_frame,
        textvariable=self.analysis_var,
        style="CardText.TLabel",
        wraplength=350,
        justify="left",
    ).pack(anchor="w")

    footer = ttk.Frame(outer, style="Modern.TFrame")
    footer.pack(fill="x", pady=(14, 0))
    ttk.Label(
        footer,
        text="Administrator permission is required for reliable BPSR input.",
        style="Footer.TLabel",
    ).pack(side="left")
    ttk.Label(
        footer,
        text=f"{self._modern_module.APP_AUTHOR}  ·  AGPL-3.0  ·  Settings save automatically",
        style="Footer.TLabel",
    ).pack(side="right")

    # Internal compatibility only. The old player lifecycle still toggles this widget,
    # but the input-test feature is no longer presented in the interface.
    self.test_button = ttk.Button(self)


def install_modern_ui(app_module: Any) -> None:
    """Install the modern UI on the existing application without changing playback logic."""
    app_class = app_module.App
    original_apply_system_theme = app_class._apply_system_theme

    def apply_system_theme(self: Any, force: bool = False) -> None:
        original_apply_system_theme(self, force)
        _apply_modern_styles(self)

    def apply_profile_ui(self: Any, schedule: bool = True) -> None:
        instrument = self._instrument_code()
        profile_code = self._profile_code()
        self._active_instrument_code = instrument
        self._active_profile_code = profile_code
        self._profile_by_instrument[instrument] = profile_code
        self.unlock_combo.configure(values=list(self._unlock_labels()))
        self.chord_combo.configure(values=list(self._chord_labels()))

        if profile_code == "custom":
            if instrument == "bass":
                summary = "Advanced Bass controls for Default and High Octave ranges."
            else:
                summary = "Advanced controls. Full-range modes may use the < and > page keys."
            self.profile_summary_var.set(summary)
            self.custom_settings_frame.pack_forget()
            self.custom_settings_frame.pack(fill="x", pady=(0, 12))
            self._refresh_custom_mode_choices()
        else:
            profile = app_module.get_fixed_profile(instrument, profile_code)
            self.profile_summary_var.set(profile.summary)
            self.custom_settings_frame.pack_forget()

        mode = self._mode_code()
        tier = self._unlock_code()
        unlock_profile = app_module.get_unlock_profile(tier, instrument)
        if instrument == "bass":
            if tier == "tier2":
                notice = (
                    f"Open Bass in Default mode. {unlock_profile.label} uses High Octave automatically "
                    "and resets it after playback."
                )
            else:
                notice = f"Open Bass in Default mode before pressing Play. Profile: {unlock_profile.label}."
        elif mode == "full" and tier == "tier4":
            notice = (
                f"Open {instrument.title()} on the middle page with Default octave. "
                "This custom full-range setup may use < and >."
            )
        else:
            notice = (
                f"Open {instrument.title()} on the middle page with Default octave, then press Play "
                "and focus BPSR during the countdown."
            )
        self.notice_var.set(notice)

        if schedule:
            self._schedule_analysis()

    app_class._modern_module = app_module
    app_class._apply_system_theme = apply_system_theme
    app_class._build_ui = _modern_build_ui
    app_class._build_custom_settings = _modern_build_custom_settings
    app_class._apply_profile_ui = apply_profile_ui
