from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from tkinter import ttk
from typing import Any


@dataclass(frozen=True, slots=True)
class ThemeColors:
    background: str
    surface: str
    field: str
    foreground: str
    muted: str
    border: str
    accent: str
    active: str
    disabled: str
    selection: str


def theme_colors(dark: bool) -> ThemeColors:
    if dark:
        return ThemeColors(
            background="#202020",
            surface="#292929",
            field="#333333",
            foreground="#f3f3f3",
            muted="#b8b8b8",
            border="#505050",
            accent="#60cdff",
            active="#3a3a3a",
            disabled="#777777",
            selection="#0f6cbd",
        )
    return ThemeColors(
        background="#f5f5f5",
        surface="#ffffff",
        field="#ffffff",
        foreground="#111111",
        muted="#5d6470",
        border="#c7c7c7",
        accent="#0067c0",
        active="#e8e8e8",
        disabled="#8a8a8a",
        selection="#0078d4",
    )


def system_prefers_dark_mode() -> bool:
    """Read the current Windows app-theme preference.

    On non-Windows systems or inaccessible registry settings, use light mode.
    """
    if os.name != "nt":
        return False
    try:
        import winreg

        path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return int(value) == 0
    except (ImportError, OSError, ValueError, TypeError):
        return False


def _set_titlebar_mode(root: Any, dark: bool) -> None:
    if os.name != "nt":
        return
    try:
        root.update_idletasks()
        user32 = ctypes.windll.user32
        dwmapi = ctypes.windll.dwmapi
        widget_hwnd = int(root.winfo_id())
        hwnd = int(user32.GetParent(widget_hwnd)) or widget_hwnd
        enabled = ctypes.c_int(1 if dark else 0)
        # Attribute 20 is current; 19 supports some older Windows 10 builds.
        for attribute in (20, 19):
            result = dwmapi.DwmSetWindowAttribute(
                hwnd,
                attribute,
                ctypes.byref(enabled),
                ctypes.sizeof(enabled),
            )
            if result == 0:
                break
    except (AttributeError, OSError, TypeError, ValueError):
        pass


def apply_theme(root: Any, style: ttk.Style, dark: bool) -> None:
    """Apply a Windows-like light or dark palette to Tk/ttk widgets."""
    colors = theme_colors(dark)
    available = set(style.theme_names())

    if dark and "clam" in available:
        style.theme_use("clam")
    elif not dark and "vista" in available:
        style.theme_use("vista")
    elif "clam" in available:
        style.theme_use("clam")

    root.configure(background=colors.background)
    root.tk_setPalette(
        background=colors.background,
        foreground=colors.foreground,
        activeBackground=colors.active,
        activeForeground=colors.foreground,
        selectBackground=colors.selection,
        selectForeground="#ffffff",
        highlightColor=colors.accent,
    )

    base = {
        "background": colors.background,
        "foreground": colors.foreground,
        "bordercolor": colors.border,
        "lightcolor": colors.border,
        "darkcolor": colors.border,
        "troughcolor": colors.surface,
        "focuscolor": colors.accent,
    }
    style.configure(".", font=("Segoe UI", 9), **base)
    style.configure("TFrame", background=colors.background)
    style.configure("TLabel", background=colors.background, foreground=colors.foreground)
    style.configure(
        "TLabelframe",
        background=colors.background,
        foreground=colors.foreground,
        bordercolor=colors.border,
    )
    style.configure(
        "TLabelframe.Label",
        background=colors.background,
        foreground=colors.foreground,
    )
    style.configure(
        "TButton",
        background=colors.surface,
        foreground=colors.foreground,
        bordercolor=colors.border,
        padding=(9, 4),
    )
    style.map(
        "TButton",
        background=[("active", colors.active), ("pressed", colors.selection)],
        foreground=[("disabled", colors.disabled), ("pressed", "#ffffff")],
    )
    style.configure(
        "TCheckbutton",
        background=colors.background,
        foreground=colors.foreground,
    )
    style.map(
        "TCheckbutton",
        background=[("active", colors.background)],
        foreground=[("disabled", colors.disabled)],
    )
    style.configure(
        "TCombobox",
        fieldbackground=colors.field,
        background=colors.surface,
        foreground=colors.foreground,
        arrowcolor=colors.foreground,
        bordercolor=colors.border,
        selectbackground=colors.selection,
        selectforeground="#ffffff",
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", colors.field), ("disabled", colors.surface)],
        foreground=[("readonly", colors.foreground), ("disabled", colors.disabled)],
        selectbackground=[("readonly", colors.selection)],
        selectforeground=[("readonly", "#ffffff")],
    )
    for widget_style in ("TEntry", "TSpinbox"):
        style.configure(
            widget_style,
            fieldbackground=colors.field,
            background=colors.field,
            foreground=colors.foreground,
            bordercolor=colors.border,
            insertcolor=colors.foreground,
            arrowcolor=colors.foreground,
        )
        style.map(
            widget_style,
            fieldbackground=[("disabled", colors.surface), ("readonly", colors.field)],
            foreground=[("disabled", colors.disabled)],
        )
    style.configure(
        "Horizontal.TProgressbar",
        background=colors.accent,
        troughcolor=colors.surface,
        bordercolor=colors.border,
    )
    style.configure("TSeparator", background=colors.border)

    style.configure(
        "TNotebook",
        background=colors.background,
        bordercolor=colors.border,
        lightcolor=colors.border,
        darkcolor=colors.border,
    )
    style.configure(
        "TNotebook.Tab",
        background=colors.surface,
        foreground=colors.muted,
        bordercolor=colors.border,
        padding=(10, 5),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", colors.field), ("active", colors.active)],
        foreground=[("selected", colors.foreground), ("active", colors.foreground), ("disabled", colors.disabled)],
    )
    style.configure(
        "Treeview",
        background=colors.field,
        fieldbackground=colors.field,
        foreground=colors.foreground,
        bordercolor=colors.border,
        lightcolor=colors.border,
        darkcolor=colors.border,
        rowheight=24,
    )
    style.map(
        "Treeview",
        background=[("selected", colors.selection)],
        foreground=[("selected", "#ffffff")],
    )
    style.configure(
        "Treeview.Heading",
        background=colors.surface,
        foreground=colors.foreground,
        bordercolor=colors.border,
        lightcolor=colors.border,
        darkcolor=colors.border,
        relief="flat",
    )
    style.map(
        "Treeview.Heading",
        background=[("active", colors.active), ("pressed", colors.selection)],
        foreground=[("pressed", "#ffffff")],
    )

    style.configure(
        "Title.TLabel",
        font=("Segoe UI", 19, "bold"),
        background=colors.background,
        foreground=colors.foreground,
    )
    style.configure(
        "Author.TLabel",
        font=("Segoe UI", 10, "bold"),
        background=colors.background,
        foreground=colors.accent,
    )
    style.configure(
        "Hint.TLabel",
        background=colors.background,
        foreground=colors.muted,
    )
    style.configure(
        "Warning.TLabel",
        background=colors.background,
        foreground="#ffcc66" if dark else "#8a4b00",
        font=("Segoe UI", 9, "bold"),
    )
    style.configure(
        "Good.TLabel",
        background=colors.background,
        foreground="#6ccb5f" if dark else "#187a2f",
        font=("Segoe UI", 9, "bold"),
    )
    style.configure(
        "Danger.TLabel",
        background=colors.background,
        foreground="#ff7b72" if dark else "#b42318",
        font=("Segoe UI", 9, "bold"),
    )

    # The dropdown of a ttk Combobox is a classic Tk listbox.
    root.option_add("*TCombobox*Listbox.background", colors.field)
    root.option_add("*TCombobox*Listbox.foreground", colors.foreground)
    root.option_add("*TCombobox*Listbox.selectBackground", colors.selection)
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    _set_titlebar_mode(root, dark)
