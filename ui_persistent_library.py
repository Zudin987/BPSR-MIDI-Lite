from __future__ import annotations

import tkinter as tk
from typing import Any

import gaming_runtime_2026 as gaming_runtime
import gaming_ui_2026 as gaming_ui


# Baseline v3.4 Library contract. The final 2026 responsive layer replaces these
# fixed values at install time, while keeping this module compatible on its own.
_LIBRARY_WIDTH = 400
_CENTER_MIN_WIDTH = 520
_MIN_WINDOW_WIDTH = 990


def _force_library_open(app: Any) -> None:
    panel = getattr(app, "_gaming_library_panel", None)
    body = getattr(app, "_gaming_body", None)
    if panel is None or body is None:
        return
    try:
        body.columnconfigure(0, minsize=_LIBRARY_WIDTH, weight=0)
        body.columnconfigure(1, minsize=_CENTER_MIN_WIDTH, weight=1)
        panel.configure(width=_LIBRARY_WIDTH)
        # The Local/Online/Bookmarks children can have a very large requested
        # width. Do not let that request resize the whole Library column.
        panel.grid_propagate(False)
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
    """Compatibility hook for callers that expect the Library to be available."""
    _force_library_open(app)


def _toggle_library_persistent(app: Any) -> None:
    _force_library_open(app)


def _persistent_responsive_layout(app: Any, width: int) -> None:
    """Baseline layout hook; final product layers may replace this at runtime."""
    _force_library_open(app)

    if width < _MIN_WINDOW_WIDTH and bool(getattr(app, "_gaming_settings_visible", False)):
        try:
            import ui_product_overhaul_v34 as product_ui

            product_ui._set_settings_drawer_visible(app, False)
        except Exception:
            pass

    if bool(getattr(app, "_gaming_settings_visible", False)):
        panel = getattr(app, "_gaming_settings_panel", None)
        if panel is not None:
            try:
                import ui_product_overhaul_v34 as product_ui

                panel.place_configure(width=product_ui._drawer_width(app))
            except (tk.TclError, Exception):
                pass


def _remove_library_toggle(root: Any) -> None:
    """Remove the old button; the final responsive layer may add a Songs toggle."""
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


def _polish_library_copy(root: Any) -> None:
    """Remove old numbered-flow copy and keep sidebar guidance compact."""
    try:
        children = tuple(root.winfo_children())
    except (AttributeError, tk.TclError):
        return
    for child in children:
        try:
            text = str(child.cget("text"))
            normalized = " ".join(text.split())
            if normalized == "2 Song":
                child.configure(text="Songs")
            elif text.startswith("Local keeps permanent MIDI files."):
                child.configure(
                    text=(
                        "Local files stay on disk. Online loads temporarily. "
                        "Bookmarks save links; Save to Local keeps a MIDI copy."
                    ),
                    wraplength=_LIBRARY_WIDTH - 36,
                )
        except (tk.TclError, TypeError):
            pass
        _polish_library_copy(child)


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
        # winfo_width() can still be 1 during nested build wrappers. Re-run the
        # final Library policy after the requested window geometry is realized.
        try:
            self.after_idle(lambda: _force_library_open(self))
        except tk.TclError:
            pass
        _remove_library_toggle(self)
        _polish_library_copy(self)

    app_class._build_ui = build_ui

    # Configure callbacks in gaming_ui resolve these module globals at runtime.
    gaming_ui._toggle_library = _toggle_library_persistent
    gaming_ui._responsive_layout = _persistent_responsive_layout

    # Older integrations may still call the runtime helper directly.
    gaming_runtime._set_library_visible = _set_library_visible_persistent
    gaming_runtime._toggle_library = _toggle_library_persistent

    app_module._persistent_library_installed = True
