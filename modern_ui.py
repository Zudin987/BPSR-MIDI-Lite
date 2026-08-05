from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable


THEME_NAMES = (
    "Light",
    "Dark",
    "Dracula",
    "Nord",
    "Catppuccin Mocha",
    "Solarized Dark",
    "Tokyo Night",
)
DEFAULT_THEME = "Dark"

# Centralized UI tokens. The extra themes adapt established developer palettes
# to this app's rounded desktop controls rather than changing any MIDI behavior.
THEME_PALETTES: dict[str, dict[str, str | bool]] = {
    "Light": {
        "is_dark": False,
        "background": "#F4F4F7",
        "surface": "#FFFFFF",
        "surface_alt": "#F7F7FA",
        "surface_hover": "#F0F0F6",
        "disabled_fill": "#E6E6EB",
        "foreground": "#17171B",
        "muted": "#686C76",
        "border": "#DFDFE7",
        "accent": "#5E6AD2",
        "accent_hover": "#505CC7",
        "accent_text": "#FFFFFF",
        "danger": "#F7F7FA",
        "danger_hover": "#EEEEF4",
        "danger_border": "#DFDFE7",
        "danger_text": "#606579",
        "danger_label": "#AF4048",
        "success": "#23845E",
        "warning": "#996A1E",
        "focus": "#5E6AD2",
    },
    "Dark": {
        "is_dark": True,
        "background": "#050506",
        "surface": "#0B0B0E",
        "surface_alt": "#101014",
        "surface_hover": "#17171D",
        "disabled_fill": "#141419",
        "foreground": "#EDEDEF",
        "muted": "#8A8F98",
        "border": "#25252D",
        "accent": "#5E6AD2",
        "accent_hover": "#6872D9",
        "accent_text": "#FFFFFF",
        "danger": "#101014",
        "danger_hover": "#17171D",
        "danger_border": "#25252D",
        "danger_text": "#A8ACC4",
        "danger_label": "#D66066",
        "success": "#62C79B",
        "warning": "#D7AD68",
        "focus": "#7C86E8",
    },
    "Dracula": {
        "is_dark": True,
        "background": "#282A36",
        "surface": "#30323F",
        "surface_alt": "#44475A",
        "surface_hover": "#50546A",
        "disabled_fill": "#3A3D4F",
        "foreground": "#F8F8F2",
        "muted": "#A7ADCB",
        "border": "#6272A4",
        "accent": "#BD93F9",
        "accent_hover": "#C9A7FA",
        "accent_text": "#282A36",
        "danger": "#44475A",
        "danger_hover": "#50546A",
        "danger_border": "#6272A4",
        "danger_text": "#F8F8F2",
        "danger_label": "#FF5555",
        "success": "#50FA7B",
        "warning": "#F1FA8C",
        "focus": "#8BE9FD",
    },
    "Nord": {
        "is_dark": True,
        "background": "#2E3440",
        "surface": "#3B4252",
        "surface_alt": "#434C5E",
        "surface_hover": "#4C566A",
        "disabled_fill": "#394150",
        "foreground": "#ECEFF4",
        "muted": "#D8DEE9",
        "border": "#4C566A",
        "accent": "#88C0D0",
        "accent_hover": "#8FBCBB",
        "accent_text": "#2E3440",
        "danger": "#434C5E",
        "danger_hover": "#4C566A",
        "danger_border": "#5B6579",
        "danger_text": "#ECEFF4",
        "danger_label": "#BF616A",
        "success": "#A3BE8C",
        "warning": "#EBCB8B",
        "focus": "#81A1C1",
    },
    "Catppuccin Mocha": {
        "is_dark": True,
        "background": "#1E1E2E",
        "surface": "#181825",
        "surface_alt": "#313244",
        "surface_hover": "#45475A",
        "disabled_fill": "#292A3B",
        "foreground": "#CDD6F4",
        "muted": "#A6ADC8",
        "border": "#45475A",
        "accent": "#CBA6F7",
        "accent_hover": "#B4BEFE",
        "accent_text": "#1E1E2E",
        "danger": "#313244",
        "danger_hover": "#45475A",
        "danger_border": "#585B70",
        "danger_text": "#CDD6F4",
        "danger_label": "#F38BA8",
        "success": "#A6E3A1",
        "warning": "#F9E2AF",
        "focus": "#89B4FA",
    },
    "Solarized Dark": {
        "is_dark": True,
        "background": "#002B36",
        "surface": "#073642",
        "surface_alt": "#0B404C",
        "surface_hover": "#124C58",
        "disabled_fill": "#173C45",
        "foreground": "#EEE8D5",
        "muted": "#93A1A1",
        "border": "#586E75",
        "accent": "#2AA198",
        "accent_hover": "#3AB1A7",
        "accent_text": "#002B36",
        "danger": "#073642",
        "danger_hover": "#124C58",
        "danger_border": "#586E75",
        "danger_text": "#93A1A1",
        "danger_label": "#DC322F",
        "success": "#859900",
        "warning": "#B58900",
        "focus": "#2AA198",
    },
    "Tokyo Night": {
        "is_dark": True,
        "background": "#1A1B26",
        "surface": "#24283B",
        "surface_alt": "#292E42",
        "surface_hover": "#3B4261",
        "disabled_fill": "#252A3C",
        "foreground": "#C0CAF5",
        "muted": "#A9B1D6",
        "border": "#3B4261",
        "accent": "#7AA2F7",
        "accent_hover": "#BB9AF7",
        "accent_text": "#1A1B26",
        "danger": "#292E42",
        "danger_hover": "#3B4261",
        "danger_border": "#565F89",
        "danger_text": "#C0CAF5",
        "danger_label": "#F7768E",
        "success": "#9ECE6A",
        "warning": "#E0AF68",
        "focus": "#7DCFFF",
    },
}


def _rounded_polygon(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, radius: float, **kwargs: Any) -> int:
    """Draw a smooth rounded rectangle without adding another UI dependency."""
    radius = max(2.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    points = (
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    )
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


def _register_rounded_widget(app: Any, widget: Any) -> None:
    widgets = getattr(app, "_modern_rounded_widgets", None)
    if widgets is None:
        widgets = []
        app._modern_rounded_widgets = widgets
    widgets.append(widget)


class _RoundedPanel(tk.Frame):
    """Rounded surface that can contain ordinary ttk widgets."""

    def __init__(
        self,
        parent: Any,
        app: Any,
        *,
        fill_key: str = "surface",
        outside_key: str = "background",
        border_key: str | None = "border",
        radius: int = 16,
        padding: tuple[int, int] = (14, 12),
        title: str | None = None,
    ) -> None:
        self._app = app
        self._fill_key = fill_key
        self._outside_key = outside_key
        self._border_key = border_key
        self._radius = radius
        palette = app._modern_palette
        super().__init__(parent, background=palette[outside_key], borderwidth=0, highlightthickness=0)

        self._canvas = tk.Canvas(
            self,
            background=palette[outside_key],
            borderwidth=0,
            highlightthickness=0,
        )
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)

        self._inner = tk.Frame(self, background=palette[fill_key], borderwidth=0, highlightthickness=0)
        self._inner.pack(fill="both", expand=True, padx=padding[0], pady=padding[1])

        if title:
            ttk.Label(self._inner, text=title, style="CardTitle.TLabel").pack(anchor="w", pady=(0, 10))

        frame_style = "SurfaceAlt.TFrame" if fill_key == "surface_alt" else "Surface.TFrame"
        self.content = ttk.Frame(self._inner, style=frame_style)
        self.content.pack(fill="both", expand=True)

        self.bind("<Configure>", self._redraw, add="+")
        _register_rounded_widget(app, self)
        self.after_idle(self._redraw)

    def _redraw(self, _event: Any = None) -> None:
        if not self.winfo_exists():
            return
        palette = self._app._modern_palette
        width = max(2, self.winfo_width())
        height = max(2, self.winfo_height())
        self._canvas.delete("rounded-panel")
        outline = palette[self._border_key] if self._border_key else palette[self._fill_key]
        _rounded_polygon(
            self._canvas,
            1,
            1,
            width - 1,
            height - 1,
            self._radius,
            fill=palette[self._fill_key],
            outline=outline,
            width=1,
            tags="rounded-panel",
        )
        self._canvas.tag_lower("rounded-panel")

    def apply_palette(self) -> None:
        palette = self._app._modern_palette
        self.configure(background=palette[self._outside_key])
        self._canvas.configure(background=palette[self._outside_key])
        self._inner.configure(background=palette[self._fill_key])
        self._redraw()


class _RoundedButton(tk.Canvas):
    """Small Canvas button compatible with the existing start/stop lifecycle."""

    def __init__(
        self,
        parent: Any,
        app: Any,
        *,
        text: str,
        command: Callable[[], None],
        role: str = "secondary",
        state: str = "normal",
        height: int = 36,
        width: int = 120,
        radius: int = 10,
        background_key: str = "surface",
    ) -> None:
        self._app = app
        self._text = text
        self._command = command
        self._role = role
        self._state = state
        self._hovered = False
        self._radius = radius
        self._background_key = background_key
        palette = app._modern_palette
        super().__init__(
            parent,
            height=height,
            width=width,
            background=palette[background_key],
            borderwidth=0,
            highlightthickness=0,
            cursor="hand2" if state != "disabled" else "arrow",
            takefocus=True,
        )
        self.bind("<Configure>", self._redraw, add="+")
        self.bind("<Enter>", self._enter, add="+")
        self.bind("<Leave>", self._leave, add="+")
        self.bind("<ButtonRelease-1>", self._activate, add="+")
        self.bind("<Return>", self._activate, add="+")
        self.bind("<space>", self._activate, add="+")
        _register_rounded_widget(app, self)
        self.after_idle(self._redraw)

    def _colours(self) -> tuple[str, str, str]:
        palette = self._app._modern_palette
        if self._state == "disabled":
            return palette["disabled_fill"], palette["border"], palette["muted"]
        if self._role == "primary":
            return (palette["accent_hover"] if self._hovered else palette["accent"], palette["accent"], palette["accent_text"])
        if self._role == "danger":
            return (
                palette["danger_hover"] if self._hovered else palette["danger"],
                palette["danger_border"],
                palette["danger_text"],
            )
        return (palette["surface_hover"] if self._hovered else palette["surface_alt"], palette["border"], palette["foreground"])

    def _redraw(self, _event: Any = None) -> None:
        if not self.winfo_exists():
            return
        fill, outline, text = self._colours()
        width = max(2, self.winfo_width())
        height = max(2, self.winfo_height())
        self.delete("all")
        _rounded_polygon(self, 1, 1, width - 1, height - 1, self._radius, fill=fill, outline=outline, width=1)
        font = ("Segoe UI Semibold", 10) if self._role in {"primary", "danger"} else ("Segoe UI", 9)
        self.create_text(width / 2, height / 2, text=self._text, fill=text, font=font)

    def _enter(self, _event: Any = None) -> None:
        if self._state != "disabled":
            self._hovered = True
            self._redraw()

    def _leave(self, _event: Any = None) -> None:
        self._hovered = False
        self._redraw()

    def _activate(self, _event: Any = None) -> None:
        if self._state != "disabled" and self._command:
            self._command()

    def configure(self, cnf: Any = None, **kwargs: Any) -> Any:
        if cnf:
            kwargs.update(cnf)
        redraw = False
        if "state" in kwargs:
            self._state = str(kwargs.pop("state"))
            self.configure(cursor="arrow" if self._state == "disabled" else "hand2")
            redraw = True
        if "text" in kwargs:
            self._text = str(kwargs.pop("text"))
            redraw = True
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        result = super().configure(**kwargs) if kwargs else None
        if redraw:
            self._redraw()
        return result

    config = configure

    def state(self, statespec: Any = None) -> tuple[str, ...]:
        if statespec is not None:
            disabled = any(str(value) == "disabled" for value in statespec)
            enabled = any(str(value) == "!disabled" for value in statespec)
            if disabled:
                self.configure(state="disabled")
            elif enabled:
                self.configure(state="normal")
        return ("disabled",) if self._state == "disabled" else ()

    def apply_palette(self) -> None:
        self.configure(background=self._app._modern_palette[self._background_key])
        self._redraw()


class _RoundedProgress(tk.Canvas):
    def __init__(self, parent: Any, app: Any, *, maximum: float = 1.0, height: int = 8) -> None:
        self._app = app
        self._maximum = float(maximum)
        self._value = 0.0
        palette = app._modern_palette
        super().__init__(
            parent,
            height=height,
            background=palette["surface"],
            borderwidth=0,
            highlightthickness=0,
        )
        self.bind("<Configure>", self._redraw, add="+")
        _register_rounded_widget(app, self)

    def _redraw(self, _event: Any = None) -> None:
        width = max(2, self.winfo_width())
        height = max(2, self.winfo_height())
        palette = self._app._modern_palette
        self.delete("all")
        radius = height / 2
        _rounded_polygon(self, 0, 0, width, height, radius, fill=palette["surface_alt"], outline=palette["surface_alt"])
        ratio = 0.0 if self._maximum <= 0 else max(0.0, min(1.0, self._value / self._maximum))
        fill_width = width * ratio
        if fill_width > 1:
            _rounded_polygon(self, 0, 0, max(height, fill_width), height, radius, fill=palette["accent"], outline=palette["accent"])

    def __setitem__(self, key: str, value: Any) -> None:
        if key == "value":
            self._value = float(value)
            self._redraw()
            return
        if key == "maximum":
            self._maximum = float(value)
            self._redraw()
            return
        super().__setitem__(key, value)

    def __getitem__(self, key: str) -> Any:
        if key == "value":
            return self._value
        if key == "maximum":
            return self._maximum
        return super().__getitem__(key)

    def apply_palette(self) -> None:
        self.configure(background=self._app._modern_palette["surface"])
        self._redraw()


def _selected_theme_name(app: Any) -> str:
    name = str(getattr(app, "_selected_theme", DEFAULT_THEME))
    return name if name in THEME_PALETTES else DEFAULT_THEME


def _apply_modern_styles(app: Any) -> None:
    """Apply the selected palette to the rounded desktop interface."""
    style = app._style
    theme_name = _selected_theme_name(app)
    palette = dict(THEME_PALETTES[theme_name])
    dark = bool(palette.pop("is_dark"))
    app._selected_theme = theme_name
    app._dark_mode = dark

    app._modern_palette = palette
    app.configure(background=palette["background"])

    # Clam allows the same token palette to style inputs consistently on Windows.
    if "clam" in set(style.theme_names()):
        style.theme_use("clam")

    style.configure(".", font=("Segoe UI", 9), background=palette["background"], foreground=palette["foreground"])
    style.configure("Modern.TFrame", background=palette["background"])
    style.configure("Surface.TFrame", background=palette["surface"])
    style.configure("SurfaceAlt.TFrame", background=palette["surface_alt"])

    style.configure(
        "Card.TLabelframe",
        background=palette["surface"],
        bordercolor=palette["border"],
        relief="solid",
        borderwidth=1,
        padding=12,
    )
    style.configure(
        "Card.TLabelframe.Label",
        background=palette["surface"],
        foreground=palette["foreground"],
        font=("Segoe UI Semibold", 11),
        padding=(0, 0, 0, 6),
    )

    style.configure("ModernTitle.TLabel", background=palette["background"], foreground=palette["foreground"], font=("Segoe UI Semibold", 22))
    style.configure("ModernSubtitle.TLabel", background=palette["background"], foreground=palette["muted"], font=("Segoe UI", 10))
    style.configure("ModernAuthor.TLabel", background=palette["background"], foreground=palette["accent"], font=("Segoe UI Semibold", 10))
    style.configure("CardTitle.TLabel", background=palette["surface"], foreground=palette["foreground"], font=("Segoe UI Semibold", 11))
    style.configure("ModernVersion.TLabel", background=palette["surface_alt"], foreground=palette["muted"], font=("Consolas", 9, "bold"))
    style.configure("CardText.TLabel", background=palette["surface"], foreground=palette["foreground"], font=("Segoe UI", 10))
    style.configure("CardMuted.TLabel", background=palette["surface"], foreground=palette["muted"], font=("Segoe UI", 9))
    style.configure("InfoStrip.TLabel", background=palette["surface_alt"], foreground=palette["foreground"], font=("Segoe UI", 10))
    style.configure("Footer.TLabel", background=palette["background"], foreground=palette["muted"], font=("Segoe UI", 9))

    # Native inputs keep keyboard/accessibility behavior while matching the reference colors.
    for widget_style in ("TCombobox", "TEntry", "TSpinbox"):
        style.configure(
            widget_style,
            fieldbackground=palette["surface_alt"],
            background=palette["surface_alt"],
            foreground=palette["foreground"],
            bordercolor=palette["border"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
            insertcolor=palette["foreground"],
            arrowcolor=palette["muted"],
            padding=(8, 6),
        )
        style.map(
            widget_style,
            fieldbackground=[
                ("focus", palette["surface_hover"]),
                ("readonly", palette["surface_alt"]),
                ("disabled", palette["disabled_fill"]),
            ],
            bordercolor=[("focus", palette["focus"]), ("active", palette["accent"])],
            foreground=[("disabled", palette["muted"]), ("readonly", palette["foreground"])],
        )

    style.configure("TCheckbutton", background=palette["surface"], foreground=palette["foreground"], focuscolor=palette["focus"], padding=(0, 2))
    style.map("TCheckbutton", background=[("active", palette["surface"])], foreground=[("disabled", palette["muted"])])
    style.configure("TSeparator", background=palette["border"])

    style.configure("TNotebook", background=palette["surface"], borderwidth=0, tabmargins=(0, 0, 0, 8))
    style.configure("TNotebook.Tab", background=palette["surface_alt"], foreground=palette["muted"], padding=(12, 6), borderwidth=0, font=("Segoe UI Semibold", 9))
    style.map(
        "TNotebook.Tab",
        background=[("selected", palette["accent"]), ("active", palette["surface_hover"])],
        foreground=[("selected", palette["accent_text"]), ("active", palette["foreground"])],
    )

    style.configure(
        "Primary.TButton",
        background=palette["accent"],
        foreground=palette["accent_text"],
        bordercolor=palette["accent"],
        focusthickness=0,
        padding=(18, 10),
        font=("Segoe UI Semibold", 10),
    )
    style.map(
        "Primary.TButton",
        background=[("active", palette["accent_hover"]), ("disabled", palette["border"])],
        foreground=[("disabled", palette["muted"])],
        bordercolor=[("active", palette["accent_hover"]), ("disabled", palette["border"])],
    )
    style.configure(
        "Danger.TButton",
        background=palette["danger"],
        foreground=palette["danger_text"],
        bordercolor=palette["danger_border"],
        focusthickness=0,
        padding=(14, 10),
        font=("Segoe UI Semibold", 10),
    )
    style.map(
        "Danger.TButton",
        background=[("active", palette["danger_hover"]), ("disabled", palette["disabled_fill"])],
        foreground=[("disabled", palette["muted"])],
        bordercolor=[("active", palette["accent"]), ("disabled", palette["border"])],
    )
    style.configure("Utility.TButton", padding=(10, 7), font=("Segoe UI", 9))
    style.configure(
        "Modern.Horizontal.TProgressbar",
        troughcolor=palette["surface_alt"],
        background=palette["accent"],
        bordercolor=palette["surface_alt"],
        lightcolor=palette["accent"],
        darkcolor=palette["accent"],
        thickness=8,
    )

    style.configure("Good.TLabel", background=palette["surface"], foreground=palette["success"], font=("Segoe UI Semibold", 10))
    style.configure("Warning.TLabel", background=palette["surface"], foreground=palette["warning"], font=("Segoe UI Semibold", 10))
    style.configure("Danger.TLabel", background=palette["surface"], foreground=palette["danger_label"], font=("Segoe UI Semibold", 10))

    app.option_add("*TCombobox*Listbox.background", palette["surface_alt"])
    app.option_add("*TCombobox*Listbox.foreground", palette["foreground"])
    app.option_add("*TCombobox*Listbox.selectBackground", palette["accent"])
    app.option_add("*TCombobox*Listbox.selectForeground", palette["accent_text"])

    live_widgets = []
    for widget in getattr(app, "_modern_rounded_widgets", []):
        try:
            if widget.winfo_exists():
                widget.apply_palette()
                live_widgets.append(widget)
        except tk.TclError:
            pass
    app._modern_rounded_widgets = live_widgets

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
    title_line = ttk.Frame(title_group, style="Modern.TFrame")
    title_line.pack(anchor="w")
    ttk.Label(title_line, text=self._modern_module.APP_NAME, style="ModernTitle.TLabel").pack(side="left")
    ttk.Label(title_line, text="by MrEz", style="ModernAuthor.TLabel").pack(side="left", padx=(10, 0), pady=(8, 0))
    ttk.Label(
        title_group,
        text="Play MIDI through Keyboard, Guitar, or Bass in Blue Protocol: Star Resonance",
        style="ModernSubtitle.TLabel",
    ).pack(anchor="w", pady=(3, 0))

    theme_controls = ttk.Frame(header, style="Modern.TFrame")
    theme_controls.pack(side="right", anchor="n")

    version_panel = _RoundedPanel(
        theme_controls,
        self,
        fill_key="surface_alt",
        border_key="border",
        radius=11,
        padding=(9, 5),
    )
    version_panel.pack(anchor="e", pady=(4, 7))
    ttk.Label(
        version_panel.content,
        text=f"v{self._modern_module.APP_VERSION}",
        style="ModernVersion.TLabel",
    ).pack()

    self.theme_var = tk.StringVar(value=_selected_theme_name(self))
    self.theme_combo = ttk.Combobox(
        theme_controls,
        textvariable=self.theme_var,
        values=THEME_NAMES,
        state="readonly",
        width=18,
    )
    self.theme_combo.pack(anchor="e")
    self.theme_combo.bind("<<ComboboxSelected>>", lambda _event: self._theme_changed())

    notice_panel = _RoundedPanel(
        outer,
        self,
        fill_key="surface_alt",
        border_key="border",
        radius=14,
        padding=(14, 10),
    )
    notice_panel.pack(fill="x", pady=(0, 16))
    ttk.Label(
        notice_panel.content,
        textvariable=self.notice_var,
        style="InfoStrip.TLabel",
        wraplength=940,
        justify="left",
    ).pack(fill="x")

    content = ttk.Frame(outer, style="Modern.TFrame")
    content.pack(fill="both", expand=True)
    content.columnconfigure(0, weight=3)
    content.columnconfigure(1, weight=2)
    content.rowconfigure(0, weight=1)

    left = ttk.Frame(content, style="Modern.TFrame")
    left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
    right = ttk.Frame(content, style="Modern.TFrame")
    right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

    setup_card = _RoundedPanel(left, self, title="Instrument setup")
    setup_card.pack(fill="x", pady=(0, 12))
    setup = setup_card.content
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

    library_card = _RoundedPanel(left, self, title="Song library")
    library_card.pack(fill="x", pady=(0, 12))
    library = library_card.content
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
    _RoundedButton(
        tools, self, text="Open MIDI folder", command=self._open_midi_folder, width=126, height=34
    ).pack(side="left")
    _RoundedButton(
        tools, self, text="Refresh", command=self._reload_midi_library, width=78, height=34
    ).pack(side="left", padx=(8, 0))
    _RoundedButton(
        tools, self, text="Find songs online", command=self._open_online_sequencer, width=132, height=34
    ).pack(side="right")
    ttk.Label(
        library,
        text="Best results: simple piano, melody, or solo-instrument MIDI files.",
        style="CardMuted.TLabel",
        wraplength=560,
        justify="left",
    ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(10, 0))

    self.custom_settings_frame = _RoundedPanel(left, self, title="Custom profile")
    self._build_custom_settings(self.custom_settings_frame.content)

    playback_card = _RoundedPanel(right, self, title="Playback")
    playback_card.pack(fill="x", pady=(0, 12))
    playback = playback_card.content
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
    self.start_button = _RoundedButton(
        action_row, self, text="Play", role="primary", command=self._start, height=40
    )
    self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
    self.stop_button = _RoundedButton(
        action_row, self, text="Stop  ·  F10", role="danger", command=self._stop, state="disabled", height=40
    )
    self.stop_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))

    self.progress = _RoundedProgress(playback, self, maximum=1.0, height=8)
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
    _RoundedButton(
        playback, self, text="Restore defaults", command=self._reset_defaults, width=118, height=34
    ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(14, 0))

    self.analysis_frame = _RoundedPanel(right, self, title="Song check")
    self.analysis_frame.pack(fill="x")
    analysis = self.analysis_frame.content
    self.suitability_label = ttk.Label(
        analysis,
        textvariable=self.suitability_var,
        style="Good.TLabel",
    )
    self.suitability_label.pack(anchor="w", pady=(0, 6))
    ttk.Label(
        analysis,
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
        text="AGPL-3.0  ·  Settings save automatically",
        style="Footer.TLabel",
    ).pack(side="right")

    # Internal compatibility only. The old player lifecycle still toggles this widget,
    # but the input-test feature is no longer presented in the interface.
    self.test_button = ttk.Button(self)


def install_modern_ui(app_module: Any) -> None:
    """Install the themed rounded UI without changing MIDI or input behavior."""
    app_class = app_module.App
    original_load_config = app_class._load_config
    original_save_config = app_class._save_config

    def apply_selected_theme(self: Any, force: bool = False) -> None:
        del force  # Kept for compatibility with the original method signature.
        theme_name = _selected_theme_name(self)
        dark = bool(THEME_PALETTES[theme_name]["is_dark"])
        self._dark_mode = dark
        app_module.apply_theme(self, self._style, dark)
        _apply_modern_styles(self)

    def poll_system_theme(self: Any) -> None:
        # Theme choice is explicit now; do not follow Windows appearance changes.
        return None

    def theme_changed(self: Any) -> None:
        selected = str(self.theme_var.get())
        if selected not in THEME_PALETTES:
            selected = DEFAULT_THEME
            self.theme_var.set(selected)
        self._selected_theme = selected
        self._apply_system_theme(force=True)
        self._save_config()

    def load_config(self: Any) -> None:
        saved_theme = DEFAULT_THEME
        try:
            data = json.loads(self._config_path().read_text(encoding="utf-8"))
            if isinstance(data, dict):
                candidate = str(data.get("theme", DEFAULT_THEME))
                if candidate in THEME_PALETTES:
                    saved_theme = candidate
        except (OSError, ValueError, TypeError):
            pass

        self._selected_theme = saved_theme
        original_load_config(self)
        self.theme_var.set(saved_theme)
        self._apply_system_theme(force=True)

    def save_config(self: Any) -> None:
        original_save_config(self)
        if self._suspend_auto_analysis:
            return
        try:
            path = self._config_path()
            data: dict[str, Any] = {}
            if path.exists():
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            data["theme"] = _selected_theme_name(self)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except (OSError, ValueError, TypeError):
            pass

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
    app_class._apply_system_theme = apply_selected_theme
    app_class._poll_system_theme = poll_system_theme
    app_class._theme_changed = theme_changed
    app_class._load_config = load_config
    app_class._save_config = save_config
    app_class._build_ui = _modern_build_ui
    app_class._build_custom_settings = _modern_build_custom_settings
    app_class._apply_profile_ui = apply_profile_ui
