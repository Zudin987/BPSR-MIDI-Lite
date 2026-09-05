from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

import ui_full_overhaul_2026 as full_ui
import ui_video_audit_2026 as audit


def _focus_widgets(app: Any, key: str) -> tuple[Any | None, Any | None]:
    """Keep final overlay chrome in the canonical state keys.

    Older responsive checks and feature modules legitimately inspect
    state['scrollbar'] / state['close_button'].  The video-audit layer needs
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

    # Remove stale aliases left by a previous open in the same process. The
    # canonical keys above are now the only overlay chrome references.
    for alias in ("video_scrollbar", "video_close_button"):
        stale = state.pop(alias, None)
        if stale is not None and stale not in {scrollbar, close_button}:
            audit._hide_widget(stale)
    return scrollbar, close_button


def install_video_audit_compat() -> None:
    if getattr(audit, "_video_audit_compat_installed", False):
        return
    audit._focus_widgets = _focus_widgets
    audit._video_audit_compat_installed = True
