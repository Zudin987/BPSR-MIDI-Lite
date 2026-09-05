from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

import ui_full_overhaul_2026 as full_ui
import ui_video_audit_2026 as audit


def _focus_widgets(app: Any, key: str) -> tuple[Any | None, Any | None]:
    """Keep final overlay chrome in the canonical state keys.

    Older responsive checks and feature modules legitimately inspect
    state['scrollbar'] / state['close_button']. The video-audit layer needs
    those widgets to live in the feature panel's coordinate system, but it does
    not need separate state names. Recreate them under the correct master and
    retain the public overlay-state contract.
    """
    state = full_ui._overlay_state(app, key)
    panel = state.get("panel")
    master = getattr(panel, "master", None) if panel is not None else None
    if master is None:
        return None, None

    scrollbar = state.get("scrollbar")
    close_button = state.get("close_button")
    try:
        if scrollbar is None or scrollbar.master is not master:
            if scrollbar is not None:
                audit._hide_widget(scrollbar)
            scrollbar = ttk.Scrollbar(
                master,
                orient="vertical",
                command=lambda *args: audit._focus_scroll(app, key, *args),
            )
            state["scrollbar"] = scrollbar
        if close_button is None or close_button.master is not master:
            if close_button is not None:
                audit._hide_widget(close_button)
            close_button = ttk.Button(master, text="Close", command=state.get("close"))
            state["close_button"] = close_button
    except tk.TclError:
        return None, None

    for alias in ("video_scrollbar", "video_close_button"):
        stale = state.pop(alias, None)
        if stale is not None and stale not in {scrollbar, close_button}:
            audit._hide_widget(stale)
    return scrollbar, close_button


def _library_width_for(window_width: int) -> int:
    """Use roomy desktops instead of keeping the Library artificially tiny."""
    if window_width >= 1800:
        return 430
    if window_width >= 1440:
        return 400
    if window_width >= 1180:
        return 360
    if window_width >= 960:
        return 320
    return 280


def _fit_roomy_desktop(app: Any) -> None:
    """Start larger on large monitors while retaining the 720p compact contract."""
    try:
        sw = max(640, int(app.winfo_screenwidth()))
        sh = max(480, int(app.winfo_screenheight()))
        if sw >= 1600 and sh >= 900:
            width = min(1440, max(1180, sw - 160))
            height = min(860, max(700, sh - 180))
        else:
            width = min(1240, max(560, sw - 80))
            height = min(760, max(380, sh - 100))
        x = max(0, (sw - width) // 2)
        y = max(0, (sh - height) // 3)
        app.geometry(f"{width}x{height}+{x}+{y}")
        app.minsize(
            min(720, max(560, sw - 120)),
            min(500, max(380, sh - 130)),
        )
    except (tk.TclError, TypeError, ValueError):
        pass


def _patch_audio_source_status() -> None:
    """Do not leave the YouTube instruction in the footer on Audio -> Band."""
    try:
        import studio_ui
    except Exception:
        return
    original = studio_ui._source_tab_changed
    if getattr(original, "_video_audit_status_patch", False):
        return

    def source_changed(app: Any) -> None:
        original(app)
        audio = getattr(app, "_studio_band_audio", None)
        if audio is None:
            return
        try:
            if app.song_source_notebook.select() != str(audio.tab):
                return
            app.status_var.set("Choose local audio or search for a song, then open the Audio → Band workspace.")
        except (AttributeError, tk.TclError):
            pass

    source_changed._video_audit_status_patch = True
    studio_ui._source_tab_changed = source_changed


def _patch_finalize() -> None:
    original = full_ui._finalize_app_ui
    if getattr(original, "_video_audit_roomy_patch", False):
        return

    def finalize(app: Any) -> None:
        original(app)
        _fit_roomy_desktop(app)
        try:
            app.after_idle(lambda: full_ui._responsive_root(app))
        except tk.TclError:
            pass

    finalize._video_audit_roomy_patch = True
    full_ui._finalize_app_ui = finalize


def install_video_audit_compat() -> None:
    if getattr(audit, "_video_audit_compat_installed", False):
        return
    audit._focus_widgets = _focus_widgets
    full_ui._library_width_for = _library_width_for
    _patch_audio_source_status()
    _patch_finalize()
    audit._video_audit_compat_installed = True
