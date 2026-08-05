from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable


# Linear / Modern visual layer for the existing BPSR MIDI Lite application.
# Playback, MIDI analysis, saved settings, and keyboard input stay in app.py.


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{max(0, min(255, channel)):02x}" for channel in rgb)


def _blend(first: str, second: str, amount: float) -> str:
    amount = max(0.0, min(1.0, amount))
    a = _hex_to_rgb(first)
    b = _hex_to_rgb(second)
    return _rgb_to_hex(tuple(round(x + (y - x) * amount) for x, y in zip(a, b)))


def _rounded_polygon(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
    **kwargs: Any,
) -> int:
    """Draw a smooth rounded rectangle without another UI dependency."""
    radius = max(2.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    points = (
        x1 + radius,
        y1,
        x2 - radius,
        y1,
        x2,
        y1,
        x2,
        y1 + radius,
        x2,
        y2 - radius,
        x2,
        y2,
        x2 - radius,
        y2,
        x1 + radius,
        y2,
        x1,
        y2,
        x1,
        y2 - radius,
        x1,
        y1 + radius,
        x1,
        y1,
    )
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


def _register_visual(app: Any, widget: Any) -> None:
    visuals = getattr(app, "_modern_visuals", None)
    if visuals is None:
        visuals = []
        app._modern_visuals = visuals
    visuals.append(widget)


def _register_panel(app: Any, panel: Any) -> None:
    panels = getattr(app, "_modern_panels", None)
    if panels is None:
        panels = []
        app._modern_panels = panels
    panels.append(panel)


class _AmbientBackdrop(tk.Canvas):
    """Low-cost ambient light, grid, and pointer glow behind the application."""

    def __init__(self, parent: Any, app: Any) -> None:
        self._app = app
        self._phase = 0.0
        self._pointer = (-9999.0, -9999.0)
        self._redraw_job: str | None = None
        palette = app._modern_palette
        super().__init__(
            parent,
            background=palette["background"],
            borderwidth=0,
            highlightthickness=0,
        )
        self.place(x=0, y=0, relwidth=1, relheight=1)
        self.tk.call("lower", self._w)
        self.bind("<Configure>", self._queue_redraw, add="+")
        app.bind_all("<Motion>", self._pointer_moved, add="+")
        _register_visual(app, self)
        self.after(180, self._animate)

    def _pointer_moved(self, event: Any) -> None:
        try:
            self._pointer = (
                float(event.x_root - self.winfo_rootx()),
                float(event.y_root - self.winfo_rooty()),
            )
        except tk.TclError:
            return
        for panel in list(getattr(self._app, "_modern_panels", [])):
            try:
                panel.pointer_moved(event.x_root, event.y_root)
            except (tk.TclError, AttributeError):
                pass
        self._queue_redraw()

    def _animate(self) -> None:
        try:
            if self.winfo_exists() and self._app.state() != "iconic":
                playing = bool(getattr(getattr(self._app, "player", None), "is_playing", False))
                delay = 450 if playing else 180
                self._phase = (self._phase + 0.115 * (delay / 180.0)) % (math.tau)
                self._queue_redraw()
        except tk.TclError:
            return
        self.after(delay if "delay" in locals() else 180, self._animate)

    def _queue_redraw(self, _event: Any = None) -> None:
        if self._redraw_job is None:
            self._redraw_job = self.after_idle(self._redraw)

    def _soft_blob(
        self,
        cx: float,
        cy: float,
        width: float,
        height: float,
        colour: str,
        strength: float,
        steps: int = 11,
    ) -> None:
        palette = self._app._modern_palette
        base = palette["background"]
        for index in range(steps, 0, -1):
            ratio = index / steps
            tint = strength * (1.0 - ratio * 0.82)
            fill = _blend(base, colour, tint)
            self.create_oval(
                cx - width * ratio / 2,
                cy - height * ratio / 2,
                cx + width * ratio / 2,
                cy + height * ratio / 2,
                fill=fill,
                outline="",
                tags="ambient",
            )

    def _redraw(self) -> None:
        self._redraw_job = None
        if not self.winfo_exists():
            return
        palette = self._app._modern_palette
        width = max(2, self.winfo_width())
        height = max(2, self.winfo_height())
        self.delete("ambient")

        # Vertical depth: near-black base with a slightly brighter top.
        stripes = 42
        for index in range(stripes):
            y1 = height * index / stripes
            y2 = height * (index + 1) / stripes + 1
            mix = index / max(1, stripes - 1)
            fill = _blend(palette["background_top"], palette["background"], mix)
            self.create_rectangle(0, y1, width, y2, fill=fill, outline="", tags="ambient")

        # Slow ambient pools. Low refresh rate keeps the UI lightweight during playback.
        sway = math.sin(self._phase) * 18
        lift = math.cos(self._phase * 0.83) * 12
        self._soft_blob(width * 0.58 + sway, -30 + lift, width * 0.82, height * 0.56, palette["accent"], 0.19)
        self._soft_blob(width * 0.08 - sway * 0.5, height * 0.46, width * 0.52, height * 0.56, palette["ambient_purple"], 0.10)
        self._soft_blob(width * 0.93 + sway * 0.35, height * 0.56, width * 0.42, height * 0.48, palette["ambient_blue"], 0.09)

        # Pointer spotlight is deliberately weak and only visible around open space.
        px, py = self._pointer
        if -200 < px < width + 200 and -200 < py < height + 200:
            self._soft_blob(px, py, 310, 310, palette["accent"], 0.075, steps=8)

        grid = palette["grid"]
        for x in range(0, width + 1, 64):
            self.create_line(x, 0, x, height, fill=grid, width=1, tags="ambient")
        for y in range(0, height + 1, 64):
            self.create_line(0, y, width, y, fill=grid, width=1, tags="ambient")
        self.tag_lower("ambient")

    def apply_palette(self) -> None:
        self.configure(background=self._app._modern_palette["background"])
        self._queue_redraw()


class _RoundedPanel(tk.Frame):
    """Layered rounded card with subtle hover depth and optional accent emphasis."""

    def __init__(
        self,
        parent: Any,
        app: Any,
        *,
        fill_key: str = "surface",
        outside_key: str = "background",
        radius: int = 16,
        padding: tuple[int, int] = (18, 16),
        title: str | None = None,
        eyebrow: str | None = None,
        variant: str = "default",
    ) -> None:
        self._app = app
        self._fill_key = fill_key
        self._outside_key = outside_key
        self._radius = radius
        self._variant = variant
        self._hovered = False
        self._cursor_ratio = 0.5
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

        if eyebrow:
            ttk.Label(self._inner, text=eyebrow.upper(), style="Eyebrow.TLabel").pack(anchor="w", pady=(0, 5))
        if title:
            ttk.Label(self._inner, text=title, style="CardTitle.TLabel").pack(anchor="w", pady=(0, 12))

        frame_style = "SurfaceAlt.TFrame" if fill_key == "surface_alt" else "Surface.TFrame"
        self.content = ttk.Frame(self._inner, style=frame_style)
        self.content.pack(fill="both", expand=True)

        self.bind("<Configure>", self._redraw, add="+")
        self.bind("<FocusIn>", lambda _event: self._set_hover(True), add="+")
        self.bind("<FocusOut>", lambda _event: self._set_hover(False), add="+")
        _register_visual(app, self)
        _register_panel(app, self)
        self.after_idle(self._redraw)

    def pointer_moved(self, x_root: int, y_root: int) -> None:
        if not self.winfo_ismapped():
            return
        left = self.winfo_rootx()
        top = self.winfo_rooty()
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        inside = left <= x_root <= left + width and top <= y_root <= top + height
        ratio = max(0.0, min(1.0, (x_root - left) / width))
        changed = inside != self._hovered or (inside and abs(ratio - self._cursor_ratio) > 0.05)
        self._hovered = inside
        self._cursor_ratio = ratio
        if changed:
            self._redraw()

    def _set_hover(self, value: bool) -> None:
        if self._hovered != value:
            self._hovered = value
            self._redraw()

    def _redraw(self, _event: Any = None) -> None:
        if not self.winfo_exists():
            return
        palette = self._app._modern_palette
        width = max(2, self.winfo_width())
        height = max(2, self.winfo_height())
        self._canvas.delete("all")

        # Three-layer elevation: ambient shadow, close shadow, and hairline border.
        _rounded_polygon(
            self._canvas,
            4,
            7,
            width - 4,
            height - 1,
            self._radius,
            fill=palette["shadow_deep"],
            outline="",
        )
        _rounded_polygon(
            self._canvas,
            2,
            3,
            width - 2,
            height - 2,
            self._radius,
            fill=palette["shadow_soft"],
            outline="",
        )

        fill = palette[self._fill_key]
        border = palette["accent_border"] if self._variant == "accent" else palette["border"]
        if self._hovered:
            fill = palette["surface_hover"] if self._fill_key == "surface" else palette["surface_alt_hover"]
            border = palette["accent_border"] if self._variant == "accent" else palette["border_hover"]

        _rounded_polygon(
            self._canvas,
            1,
            1,
            width - 1,
            height - 4,
            self._radius,
            fill=fill,
            outline=border,
            width=1,
        )

        # Accent-tinted pointer spotlight along the upper edge.
        if self._hovered or self._variant == "accent":
            center = width * self._cursor_ratio
            glow_width = min(260, width * 0.62)
            for index in range(5, 0, -1):
                ratio = index / 5
                colour = _blend(fill, palette["accent"], 0.025 + (1 - ratio) * 0.06)
                self._canvas.create_line(
                    max(self._radius, center - glow_width * ratio / 2),
                    2,
                    min(width - self._radius, center + glow_width * ratio / 2),
                    2,
                    fill=colour,
                    width=max(1, round(5 - index * 0.7)),
                )

        self._canvas.create_line(
            self._radius,
            2,
            width - self._radius,
            2,
            fill=palette["inner_highlight"],
            width=1,
        )
        self._canvas.tag_lower("all")

    def apply_palette(self) -> None:
        palette = self._app._modern_palette
        self.configure(background=palette[self._outside_key])
        self._canvas.configure(background=palette[self._outside_key])
        self._inner.configure(background=palette[self._fill_key])
        self._redraw()


class _RoundedButton(tk.Canvas):
    """Canvas button with focus ring, layered depth, and precise active motion."""

    def __init__(
        self,
        parent: Any,
        app: Any,
        *,
        text: str,
        command: Callable[[], None],
        role: str = "secondary",
        state: str = "normal",
        height: int = 38,
        width: int = 120,
        radius: int = 9,
        background_key: str = "surface",
    ) -> None:
        self._app = app
        self._text = text
        self._command = command
        self._role = role
        self._state = state
        self._hovered = False
        self._pressed = False
        self._focused = False
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
        self.bind("<ButtonPress-1>", self._press, add="+")
        self.bind("<ButtonRelease-1>", self._release, add="+")
        self.bind("<FocusIn>", self._focus_in, add="+")
        self.bind("<FocusOut>", self._focus_out, add="+")
        self.bind("<Return>", self._keyboard_activate, add="+")
        self.bind("<space>", self._keyboard_activate, add="+")
        _register_visual(app, self)
        self.after_idle(self._redraw)

    def _colours(self) -> tuple[str, str, str]:
        palette = self._app._modern_palette
        if self._state == "disabled":
            return palette["disabled_fill"], palette["border"], palette["muted"]
        if self._role == "primary":
            return (
                palette["accent_pressed"] if self._pressed else palette["accent_hover"] if self._hovered else palette["accent"],
                palette["accent_border"],
                "#FFFFFF",
            )
        if self._role == "danger":
            return (
                palette["danger_pressed"] if self._pressed else palette["danger_hover"] if self._hovered else palette["danger"],
                palette["danger_border"],
                "#FFFFFF",
            )
        return (
            palette["surface_pressed"] if self._pressed else palette["surface_alt_hover"] if self._hovered else palette["surface_alt"],
            palette["border_hover"] if self._hovered else palette["border"],
            palette["foreground"],
        )

    def _redraw(self, _event: Any = None) -> None:
        if not self.winfo_exists():
            return
        palette = self._app._modern_palette
        fill, outline, text = self._colours()
        width = max(2, self.winfo_width())
        height = max(2, self.winfo_height())
        self.delete("all")
        inset = 2 if self._pressed else 1

        if self._role == "primary" and self._state != "disabled":
            glow = palette["accent_glow_hover"] if self._hovered else palette["accent_glow"]
            _rounded_polygon(self, 3, 5, width - 3, height - 1, self._radius, fill=glow, outline="")
        elif self._role == "danger" and self._state != "disabled":
            _rounded_polygon(self, 3, 5, width - 3, height - 1, self._radius, fill=palette["danger_glow"], outline="")
        else:
            _rounded_polygon(self, 3, 5, width - 3, height - 1, self._radius, fill=palette["shadow_soft"], outline="")

        if self._focused and self._state != "disabled":
            _rounded_polygon(
                self,
                0,
                0,
                width,
                height - 2,
                self._radius + 1,
                fill=palette[self._background_key],
                outline=palette["focus"],
                width=2,
            )

        _rounded_polygon(
            self,
            inset,
            inset,
            width - inset,
            height - 3 - inset,
            self._radius,
            fill=fill,
            outline=outline,
            width=1,
        )
        self.create_line(
            self._radius + 3,
            inset + 1,
            width - self._radius - 3,
            inset + 1,
            fill=palette["button_highlight"],
            width=1,
        )
        font = ("Segoe UI Semibold", 10) if self._role in {"primary", "danger"} else ("Segoe UI", 9)
        y = height / 2 + (1 if self._pressed else -1)
        self.create_text(width / 2, y, text=self._text, fill=text, font=font)

    def _enter(self, _event: Any = None) -> None:
        if self._state != "disabled":
            self._hovered = True
            self._redraw()

    def _leave(self, _event: Any = None) -> None:
        self._hovered = False
        self._pressed = False
        self._redraw()

    def _press(self, _event: Any = None) -> None:
        if self._state != "disabled":
            self.focus_set()
            self._pressed = True
            self._redraw()

    def _release(self, event: Any = None) -> None:
        if self._state == "disabled":
            return
        was_pressed = self._pressed
        self._pressed = False
        self._redraw()
        if was_pressed and event is not None and 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
            self._command()

    def _focus_in(self, _event: Any = None) -> None:
        self._focused = True
        self._redraw()

    def _focus_out(self, _event: Any = None) -> None:
        self._focused = False
        self._pressed = False
        self._redraw()

    def _keyboard_activate(self, _event: Any = None) -> str:
        if self._state != "disabled":
            self._command()
        return "break"

    def configure(self, cnf: Any = None, **kwargs: Any) -> Any:
        if cnf:
            kwargs.update(cnf)
        redraw = False
        if "state" in kwargs:
            self._state = str(kwargs.pop("state"))
            super().configure(cursor="arrow" if self._state == "disabled" else "hand2")
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
        _register_visual(app, self)

    def _redraw(self, _event: Any = None) -> None:
        width = max(2, self.winfo_width())
        height = max(2, self.winfo_height())
        palette = self._app._modern_palette
        self.delete("all")
        radius = height / 2
        _rounded_polygon(self, 0, 0, width, height, radius, fill=palette["surface_strong"], outline=palette["border"])
        ratio = 0.0 if self._maximum <= 0 else max(0.0, min(1.0, self._value / self._maximum))
        fill_width = width * ratio
        if fill_width > 1:
            _rounded_polygon(
                self,
                0,
                0,
                max(height, fill_width),
                height,
                radius,
                fill=palette["accent"],
                outline=palette["accent"],
            )
            self.create_line(height / 2, 1, max(height / 2, fill_width - height / 2), 1, fill=palette["button_highlight"])

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


def _apply_modern_styles(app: Any) -> None:
    """Apply the centralized Linear / Modern design tokens."""
    style = app._style
    dark = bool(app._dark_mode)

    if dark:
        palette = {
            "background": "#050506",
            "background_top": "#0A0A0F",
            "surface": "#0B0B0E",
            "surface_alt": "#101014",
            "surface_strong": "#15151B",
            "surface_hover": "#0F0F14",
            "surface_alt_hover": "#17171D",
            "surface_pressed": "#0D0D11",
            "disabled_fill": "#141419",
            "foreground": "#EDEDEF",
            "muted": "#8A8F98",
            "subtle": "#B0B3BA",
            "border": "#1B1B21",
            "border_hover": "#292932",
            "inner_highlight": "#25252D",
            "button_highlight": "#A4AAEF",
            "accent": "#5E6AD2",
            "accent_hover": "#6872D9",
            "accent_pressed": "#535FC4",
            "accent_border": "#373B68",
            "accent_glow": "#16182A",
            "accent_glow_hover": "#202443",
            "ambient_purple": "#7B4D9B",
            "ambient_blue": "#345CA8",
            "danger": "#C9555B",
            "danger_hover": "#D66066",
            "danger_pressed": "#B9494F",
            "danger_border": "#66373B",
            "danger_glow": "#241315",
            "focus": "#7C86E8",
            "shadow_deep": "#020203",
            "shadow_soft": "#060608",
            "grid": "#0D0D11",
            "success": "#62C79B",
            "warning": "#D7AD68",
        }
    else:
        palette = {
            "background": "#F4F4F7",
            "background_top": "#FFFFFF",
            "surface": "#FFFFFF",
            "surface_alt": "#F7F7FA",
            "surface_strong": "#ECECF2",
            "surface_hover": "#FBFBFD",
            "surface_alt_hover": "#F0F0F6",
            "surface_pressed": "#E9E9F0",
            "disabled_fill": "#E6E6EB",
            "foreground": "#17171B",
            "muted": "#6D717B",
            "subtle": "#4E525B",
            "border": "#E1E1E7",
            "border_hover": "#CBCBD5",
            "inner_highlight": "#FFFFFF",
            "button_highlight": "#D9DCF8",
            "accent": "#5E6AD2",
            "accent_hover": "#505CC7",
            "accent_pressed": "#4551BA",
            "accent_border": "#9CA3E5",
            "accent_glow": "#E5E7F8",
            "accent_glow_hover": "#D9DCF5",
            "ambient_purple": "#C9A5DA",
            "ambient_blue": "#A9C0E8",
            "danger": "#C24D55",
            "danger_hover": "#AF4048",
            "danger_pressed": "#9B353D",
            "danger_border": "#E0A7AA",
            "danger_glow": "#F6E2E3",
            "focus": "#5E6AD2",
            "shadow_deep": "#DADAE2",
            "shadow_soft": "#E8E8ED",
            "grid": "#ECECF1",
            "success": "#23845E",
            "warning": "#996A1E",
        }

    app._modern_palette = palette
    app.configure(background=palette["background"])

    # Use the same rendering path in light and dark mode so the custom tokens are consistent.
    if "clam" in set(style.theme_names()):
        style.theme_use("clam")

    style.configure(".", font=("Segoe UI", 9), background=palette["background"], foreground=palette["foreground"])
    style.configure("Modern.TFrame", background=palette["background"])
    style.configure("Surface.TFrame", background=palette["surface"])
    style.configure("SurfaceAlt.TFrame", background=palette["surface_alt"])

    style.configure("ModernTitle.TLabel", background=palette["background"], foreground=palette["foreground"], font=("Segoe UI Semibold", 24))
    style.configure("ModernSubtitle.TLabel", background=palette["background"], foreground=palette["muted"], font=("Segoe UI", 10))
    style.configure("ModernAuthor.TLabel", background=palette["background"], foreground=palette["accent"], font=("Segoe UI Semibold", 10))
    style.configure("Eyebrow.TLabel", background=palette["surface"], foreground=palette["accent"], font=("Consolas", 8, "bold"))
    style.configure("HeaderEyebrow.TLabel", background=palette["background"], foreground=palette["accent"], font=("Consolas", 8, "bold"))
    style.configure("NoticeDot.TLabel", background=palette["surface_alt"], foreground=palette["accent"], font=("Segoe UI", 8))
    style.configure("CardTitle.TLabel", background=palette["surface"], foreground=palette["foreground"], font=("Segoe UI Semibold", 12))
    style.configure("ModernVersion.TLabel", background=palette["surface_alt"], foreground=palette["muted"], font=("Consolas", 9, "bold"))
    style.configure("CardText.TLabel", background=palette["surface"], foreground=palette["foreground"], font=("Segoe UI", 10))
    style.configure("CardMuted.TLabel", background=palette["surface"], foreground=palette["muted"], font=("Segoe UI", 9))
    style.configure("InfoStrip.TLabel", background=palette["surface_alt"], foreground=palette["subtle"], font=("Segoe UI", 10))
    style.configure("Footer.TLabel", background=palette["background"], foreground=palette["muted"], font=("Segoe UI", 9))

    # Inputs retain native accessibility and keyboard behavior while matching the design tokens.
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
            padding=(9, 7),
        )
        style.map(
            widget_style,
            fieldbackground=[("focus", palette["surface_strong"]), ("readonly", palette["surface_alt"]), ("disabled", palette["disabled_fill"])],
            bordercolor=[("focus", palette["focus"]), ("active", palette["border_hover"])],
            foreground=[("disabled", palette["muted"]), ("readonly", palette["foreground"])],
        )

    style.configure("TCheckbutton", background=palette["surface"], foreground=palette["foreground"], focuscolor=palette["focus"], padding=(0, 2))
    style.map("TCheckbutton", background=[("active", palette["surface"])], foreground=[("disabled", palette["muted"])])
    style.configure("TSeparator", background=palette["border"])

    style.configure("Modern.TNotebook", background=palette["surface"], borderwidth=0, tabmargins=(0, 0, 0, 10))
    style.configure("Modern.TNotebook.Tab", background=palette["surface_alt"], foreground=palette["muted"], padding=(14, 7), borderwidth=0, font=("Segoe UI Semibold", 9))
    style.map(
        "Modern.TNotebook.Tab",
        background=[("selected", palette["accent"]), ("active", palette["surface_alt_hover"])],
        foreground=[("selected", "#FFFFFF"), ("active", palette["foreground"])],
    )

    # Re-style suitability labels created by app.py so they sit correctly inside cards.
    style.configure("Good.TLabel", background=palette["surface"], foreground=palette["success"], font=("Segoe UI Semibold", 10))
    style.configure("Warning.TLabel", background=palette["surface"], foreground=palette["warning"], font=("Segoe UI Semibold", 10))
    style.configure("Danger.TLabel", background=palette["surface"], foreground=palette["danger_hover"], font=("Segoe UI Semibold", 10))

    app.option_add("*TCombobox*Listbox.background", palette["surface_alt"])
    app.option_add("*TCombobox*Listbox.foreground", palette["foreground"])
    app.option_add("*TCombobox*Listbox.selectBackground", palette["accent"])
    app.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")

    live_visuals = []
    for widget in getattr(app, "_modern_visuals", []):
        try:
            if widget.winfo_exists():
                widget.apply_palette()
                live_visuals.append(widget)
        except tk.TclError:
            pass
    app._modern_visuals = live_visuals


def _field_label(parent: Any, text: str, row: int, column: int = 0, **grid: Any) -> None:
    ttk.Label(parent, text=text.upper(), style="CardMuted.TLabel", font=("Consolas", 8, "bold")).grid(
        row=row,
        column=column,
        sticky="w",
        pady=(0, 6),
        **grid,
    )


def _modern_build_custom_settings(self: Any, settings: Any) -> None:
    settings.columnconfigure(0, weight=1)

    ttk.Label(
        settings,
        text="Manual controls for unusual MIDI files. Fixed profiles are the safer default.",
        style="CardMuted.TLabel",
        wraplength=530,
        justify="left",
    ).grid(row=0, column=0, sticky="w", pady=(0, 12))

    tabs = ttk.Notebook(settings, style="Modern.TNotebook")
    tabs.grid(row=1, column=0, sticky="nsew")

    notes_tab = ttk.Frame(tabs, style="Surface.TFrame", padding=(2, 12, 2, 2))
    timing_tab = ttk.Frame(tabs, style="Surface.TFrame", padding=(2, 12, 2, 2))
    tabs.add(notes_tab, text="Notes")
    tabs.add(timing_tab, text="Timing")

    notes_tab.columnconfigure(0, weight=1)
    notes_tab.columnconfigure(1, weight=1)

    _field_label(notes_tab, "Playback mode", 0, 0)
    self.mode_combo = ttk.Combobox(notes_tab, textvariable=self.mode_var, values=list(self._modern_module.MODE_LABELS), state="readonly")
    self.mode_combo.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 12))

    _field_label(notes_tab, "Unlocked range", 2, 0, padx=(0, 7))
    _field_label(notes_tab, "Chord detail", 2, 1, padx=(7, 0))
    self.unlock_combo = ttk.Combobox(
        notes_tab,
        textvariable=self.unlock_var,
        values=list(self._modern_module.UNLOCK_LABELS_BY_INSTRUMENT["keyboard"]),
        state="readonly",
    )
    self.unlock_combo.grid(row=3, column=0, sticky="ew", padx=(0, 7), pady=(0, 12))
    self.chord_combo = ttk.Combobox(
        notes_tab,
        textvariable=self.chord_var,
        values=list(self._modern_module.STANDARD_CHORD_LABELS),
        state="readonly",
    )
    self.chord_combo.grid(row=3, column=1, sticky="ew", padx=(7, 0), pady=(0, 12))

    _field_label(notes_tab, "Unavailable notes", 4, 0)
    self.mapping_combo = ttk.Combobox(notes_tab, textvariable=self.mapping_var, values=list(self._modern_module.MAPPING_LABELS), state="readonly")
    self.mapping_combo.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 12))

    checks = ttk.Frame(notes_tab, style="Surface.TFrame")
    checks.grid(row=6, column=0, columnspan=2, sticky="ew")
    ttk.Checkbutton(checks, text="Ignore drums", variable=self.percussion_var).pack(side="left")
    ttk.Checkbutton(checks, text="Use sustain pedal", variable=self.pedal_var).pack(side="left", padx=(20, 0))

    timing_tab.columnconfigure(0, weight=1)
    timing_tab.columnconfigure(1, weight=1)
    _field_label(timing_tab, "Page-switch wait", 0, 0, padx=(0, 7))
    _field_label(timing_tab, "Ctrl / Shift lead", 0, 1, padx=(7, 0))

    page_wrap = ttk.Frame(timing_tab, style="Surface.TFrame")
    page_wrap.grid(row=1, column=0, sticky="w", padx=(0, 7), pady=(0, 14))
    self.page_delay_spin = ttk.Spinbox(page_wrap, from_=40, to=1000, increment=10, textvariable=self.page_delay_var, width=8)
    self.page_delay_spin.pack(side="left")
    ttk.Label(page_wrap, text="ms", style="CardMuted.TLabel").pack(side="left", padx=(7, 0))

    modifier_wrap = ttk.Frame(timing_tab, style="Surface.TFrame")
    modifier_wrap.grid(row=1, column=1, sticky="w", padx=(7, 0), pady=(0, 14))
    ttk.Spinbox(modifier_wrap, from_=10, to=500, increment=5, textvariable=self.modifier_lead_var, width=8).pack(side="left")
    ttk.Label(modifier_wrap, text="ms", style="CardMuted.TLabel").pack(side="left", padx=(7, 0))

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
        ttk.Label(box, text=label.upper(), style="CardMuted.TLabel", font=("Consolas", 8, "bold")).pack(anchor="w", pady=(0, 6))
        value_row = ttk.Frame(box, style="Surface.TFrame")
        value_row.pack(anchor="w")
        ttk.Spinbox(value_row, from_=from_value, to=to_value, textvariable=variable, width=7).pack(side="left")
        ttk.Label(value_row, text=suffix, style="CardMuted.TLabel").pack(side="left", padx=(6, 0))


def _modern_build_ui(self: Any) -> None:
    self._apply_system_theme(force=True)
    self.geometry("1080x880")
    self.minsize(940, 720)

    _AmbientBackdrop(self, self)

    outer = tk.Frame(self, background=self._modern_palette["background"], borderwidth=0, highlightthickness=0)
    outer.place(x=22, y=18, relwidth=1, relheight=1, width=-44, height=-36)

    header = ttk.Frame(outer, style="Modern.TFrame")
    header.pack(fill="x", pady=(0, 16))
    title_group = ttk.Frame(header, style="Modern.TFrame")
    title_group.pack(side="left", fill="x", expand=True)

    ttk.Label(title_group, text="MIDI PLAYER", style="HeaderEyebrow.TLabel").pack(anchor="w", pady=(0, 4))
    title_line = ttk.Frame(title_group, style="Modern.TFrame")
    title_line.pack(anchor="w")
    ttk.Label(title_line, text=self._modern_module.APP_NAME, style="ModernTitle.TLabel").pack(side="left")
    ttk.Label(title_line, text="by MrEz", style="ModernAuthor.TLabel").pack(side="left", padx=(12, 0), pady=(10, 0))
    ttk.Label(
        title_group,
        text="Precise MIDI playback for Keyboard, Guitar, and Bass in BPSR",
        style="ModernSubtitle.TLabel",
    ).pack(anchor="w", pady=(4, 0))

    version_panel = _RoundedPanel(
        header,
        self,
        fill_key="surface_alt",
        radius=999,
        padding=(11, 6),
        variant="accent",
    )
    version_panel.pack(side="right", anchor="n", pady=(6, 0))
    ttk.Label(version_panel.content, text=f"v{self._modern_module.APP_VERSION}", style="ModernVersion.TLabel").pack()

    notice_panel = _RoundedPanel(
        outer,
        self,
        fill_key="surface_alt",
        radius=14,
        padding=(16, 11),
        variant="accent",
    )
    notice_panel.pack(fill="x", pady=(0, 16))
    notice_row = ttk.Frame(notice_panel.content, style="SurfaceAlt.TFrame")
    notice_row.pack(fill="x")
    ttk.Label(notice_row, text="●", style="NoticeDot.TLabel").pack(side="left", padx=(0, 9))
    ttk.Label(
        notice_row,
        textvariable=self.notice_var,
        style="InfoStrip.TLabel",
        wraplength=930,
        justify="left",
    ).pack(side="left", fill="x", expand=True)

    content = ttk.Frame(outer, style="Modern.TFrame")
    content.pack(fill="both", expand=True)
    content.columnconfigure(0, weight=3, uniform="columns")
    content.columnconfigure(1, weight=2, uniform="columns")
    content.rowconfigure(0, weight=1)

    left = ttk.Frame(content, style="Modern.TFrame")
    left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
    right = ttk.Frame(content, style="Modern.TFrame")
    right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

    setup_card = _RoundedPanel(left, self, eyebrow="01  SETUP", title="Choose your instrument")
    setup_card.pack(fill="x", pady=(0, 12))
    setup = setup_card.content
    setup.columnconfigure(0, weight=1)
    setup.columnconfigure(1, weight=1)

    _field_label(setup, "Instrument", 0, 0, padx=(0, 8))
    _field_label(setup, "Profile", 0, 1, padx=(8, 0))
    self.instrument_combo = ttk.Combobox(setup, textvariable=self.instrument_var, values=list(self._modern_module.INSTRUMENT_LABELS), state="readonly")
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
    ttk.Label(setup, textvariable=self.profile_summary_var, style="CardMuted.TLabel", wraplength=560, justify="left").grid(
        row=2, column=0, columnspan=2, sticky="w", pady=(11, 0)
    )

    library_card = _RoundedPanel(left, self, eyebrow="02  SONG", title="Select a MIDI file")
    library_card.pack(fill="x", pady=(0, 12))
    library = library_card.content
    library.columnconfigure(0, weight=1)
    _field_label(library, "MIDI library", 0, 0)
    self.midi_combo = ttk.Combobox(library, textvariable=self.midi_display_var, state="readonly", values=())
    self.midi_combo.grid(row=1, column=0, columnspan=3, sticky="ew")
    self.midi_combo.bind("<<ComboboxSelected>>", lambda _event: self._midi_selected())

    tools = ttk.Frame(library, style="Surface.TFrame")
    tools.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(11, 0))
    _RoundedButton(tools, self, text="Open folder", command=self._open_midi_folder, width=104, height=35).pack(side="left")
    _RoundedButton(tools, self, text="Refresh", command=self._reload_midi_library, width=82, height=35).pack(side="left", padx=(8, 0))
    _RoundedButton(tools, self, text="Find MIDI online", command=self._open_online_sequencer, width=126, height=35).pack(side="right")
    ttk.Label(
        library,
        text="Simple piano, melody, and solo arrangements usually translate best.",
        style="CardMuted.TLabel",
        wraplength=560,
        justify="left",
    ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(11, 0))

    self.custom_settings_frame = _RoundedPanel(left, self, eyebrow="CUSTOM", title="Fine-tune playback")
    self._build_custom_settings(self.custom_settings_frame.content)

    playback_card = _RoundedPanel(right, self, eyebrow="03  PLAY", title="Ready when you are", variant="accent")
    playback_card.pack(fill="x", pady=(0, 12))
    playback = playback_card.content
    playback.columnconfigure(0, weight=1)
    playback.columnconfigure(1, weight=1)

    _field_label(playback, "Countdown", 0, 0, padx=(0, 8))
    _field_label(playback, "Input method", 0, 1, padx=(8, 0))
    delay_row = ttk.Frame(playback, style="Surface.TFrame")
    delay_row.grid(row=1, column=0, sticky="w", padx=(0, 8))
    ttk.Spinbox(delay_row, from_=0, to=30, increment=0.5, textvariable=self.start_delay_var, width=7).pack(side="left")
    ttk.Label(delay_row, text="sec", style="CardMuted.TLabel").pack(side="left", padx=(7, 0))
    self.input_backend_combo = ttk.Combobox(
        playback,
        textvariable=self.input_backend_var,
        values=list(self._modern_module.INPUT_BACKEND_LABELS),
        state="readonly",
    )
    self.input_backend_combo.grid(row=1, column=1, sticky="ew", padx=(8, 0))
    self.input_backend_combo.bind("<<ComboboxSelected>>", lambda _event: self._save_config())

    ttk.Checkbutton(playback, text="Minimize after Play", variable=self.minimize_var, command=self._save_config).grid(
        row=2, column=0, columnspan=2, sticky="w", pady=(14, 0)
    )

    action_row = ttk.Frame(playback, style="Surface.TFrame")
    action_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(18, 0))
    action_row.columnconfigure(0, weight=1)
    action_row.columnconfigure(1, weight=1)
    self.start_button = _RoundedButton(action_row, self, text="Play", role="primary", command=self._start, height=44)
    self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
    self.stop_button = _RoundedButton(
        action_row,
        self,
        text="Stop  ·  F10",
        role="danger",
        command=self._stop,
        state="disabled",
        height=44,
    )
    self.stop_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))

    self.progress = _RoundedProgress(playback, self, maximum=1.0, height=8)
    self.progress.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(20, 9))
    ttk.Label(playback, textvariable=self.status_var, style="CardText.TLabel", wraplength=360, justify="left").grid(
        row=5, column=0, columnspan=2, sticky="w"
    )

    ttk.Separator(playback).grid(row=6, column=0, columnspan=2, sticky="ew", pady=17)
    footer_row = ttk.Frame(playback, style="Surface.TFrame")
    footer_row.grid(row=7, column=0, columnspan=2, sticky="ew")
    ttk.Label(footer_row, text="Keep BPSR focused while playing.", style="CardMuted.TLabel").pack(side="left")
    _RoundedButton(footer_row, self, text="Reset", command=self._reset_defaults, width=72, height=32).pack(side="right")

    self.analysis_frame = _RoundedPanel(right, self, eyebrow="SONG FIT", title="Automatic check")
    self.analysis_frame.pack(fill="x")
    analysis = self.analysis_frame.content
    self.suitability_label = ttk.Label(analysis, textvariable=self.suitability_var, style="Good.TLabel")
    self.suitability_label.pack(anchor="w", pady=(0, 7))
    ttk.Label(analysis, textvariable=self.analysis_var, style="CardText.TLabel", wraplength=360, justify="left").pack(anchor="w")

    footer = ttk.Frame(outer, style="Modern.TFrame")
    footer.pack(fill="x", pady=(14, 0))
    ttk.Label(footer, text="Administrator access required", style="Footer.TLabel").pack(side="left")
    ttk.Label(footer, text="F10 emergency stop  ·  Settings save automatically", style="Footer.TLabel").pack(side="right")

    # Internal compatibility only. app.py still toggles this object during playback,
    # but the removed input-test feature is not exposed in the interface.
    self.test_button = ttk.Button(self)


def install_modern_ui(app_module: Any) -> None:
    """Install the visual layer without changing MIDI or input behavior."""
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
                summary = "Manual Bass controls for Default and High Octave ranges."
            else:
                summary = "Manual controls. Full-range modes may use the < and > page keys."
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
                notice = f"Open Bass in Default mode. {unlock_profile.label} enables High Octave automatically."
            else:
                notice = f"Open Bass in Default mode before Play. Profile: {unlock_profile.label}."
        elif mode == "full" and tier == "tier4":
            notice = f"Open {instrument.title()} on the middle page with Default octave. This full-range profile may use < and >."
        else:
            notice = f"Open {instrument.title()} on the middle page with Default octave, press Play, then focus BPSR during the countdown."
        self.notice_var.set(notice)

        if schedule:
            self._schedule_analysis()

    app_class._modern_module = app_module
    app_class._apply_system_theme = apply_system_theme
    app_class._build_ui = _modern_build_ui
    app_class._build_custom_settings = _modern_build_custom_settings
    app_class._apply_profile_ui = apply_profile_ui
