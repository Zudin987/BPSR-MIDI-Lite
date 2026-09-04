from __future__ import annotations

import tkinter as tk
from typing import Any

import gaming_runtime_2026 as gaming_runtime
import gaming_ui_2026 as gaming_ui


_LIBRARY_WIDTH = 260
_MIN_WINDOW_WIDTH = 820


def _force_library_open(app: Any) -> None:
    panel = getattr(app, "_gaming_library_panel", None)
    body = getattr(app, "_gaming_body", None)
    if panel is None or body is None:
        return
    try:
        body.columnconfigure(0, minsize=_LIBRARY_WIDTH, weight=0)
        panel.grid()
        app._gaming_library_visible = True
    except tk.TclError:
        return
    try:
        import online_ui

        online_ui._schedule_source_notebook_resize(app)
    except Exception:
        pass


def _set_library_visible_persistent(app: Any, _visible: bool = True) -> None:
    """Compatibility hook: Library is intentionally permanent in the v3.4 UI."""
    _force_library_open(app)


def _toggle_library_persistent(app: Any) -> None:
    _force_library_open(app)


def _persistent_responsive_layout(app: Any, width: int) -> None:
    """Keep Library visible at every supported size; only manage Settings."""
    _force_library_open(app)

    # Product UI owns the Settings drawer. On a very narrow window, close the
    # drawer rather than sacrificing the permanent Library or main player.
    if width < 760 and bool(getattr(app, "_gaming_settings_visible", False)):
        try:
            import ui_product_overhaul_v34 as product_ui

            product_ui._set_settings_drawer_visible(app, False)
        except Exception:
            pass

    # If Settings remains open, keep its overlay width responsive.
    if bool(getattr(app, "_gaming_settings_visible", False)):
        panel = getattr(app, "_gaming_settings_panel", None)
        if panel is not None:
            try:
                import ui_product_overhaul_v34 as product_ui

                panel.place_configure(width=product_ui._drawer_width(app))
            except (tk.TclError, Exception):
                pass


def _remove_library_toggle(root: Any) -> None:
    """Remove the obsolete top-bar Library button now that the panel is fixed."""
    try:
        children = tuple(root.winfo_children())
    except (AttributeError, tk.TclError):
        return
    for child in children:
        try:
            if child.winfo_class() == "TButton" and str(child.cget("text")) == "Library":
                manager = str(child.winfo_manager())
                if manager == "grid":
                    child.grid_remove()
                elif manager == "pack":
                    child.pack_forget()
                elif manager == "place":
                    child.place_forget()
                continue
        except (tk.TclError, TypeError):
            pass
        _remove_library_toggle(child)


def install_persistent_library(app_module: Any) -> None:
    if getattr(app_module, "_persistent_library_installed", False):
        return

    app_class = app_module.App
    original_build = app_class._build_ui

    def build_ui(self: Any) -> None:
        original_build(self)
        try:
            self.minsize(_MIN_WINDOW_WIDTH, 540)
        except tk.TclError:
            pass
        _force_library_open(self)
        _remove_library_toggle(self)

    app_class._build_ui = build_ui

    # Configure callbacks in gaming_ui resolve these module globals at runtime.
    gaming_ui._toggle_library = _toggle_library_persistent
    gaming_ui._responsive_layout = _persistent_responsive_layout

    # Older integrations may still call the runtime helper directly.
    gaming_runtime._set_library_visible = _set_library_visible_persistent
    gaming_runtime._toggle_library = _toggle_library_persistent

    app_module._persistent_library_installed = True
