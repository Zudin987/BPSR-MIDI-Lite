from __future__ import annotations

import tkinter as tk
from typing import Any

import ui_full_overhaul_2026 as full_ui


_WIDE_AT = 920
_STACK_AT = 650


def _children(widget: Any) -> tuple[Any, ...]:
    try:
        return tuple(widget.winfo_children())
    except (AttributeError, tk.TclError):
        return ()


def _walk(root: Any):
    for child in _children(root):
        yield child
        yield from _walk(child)


def _contains_class(root: Any, name: str) -> bool:
    return any(
        getattr(widget, "winfo_class", lambda: "")() == name
        for widget in _walk(root)
    )


def _save_grid(widget: Any) -> None:
    if widget is None or getattr(widget, "_ux_toolbar_grid", None) is not None:
        return
    try:
        info = dict(widget.grid_info())
        if info:
            info.pop("in", None)
            widget._ux_toolbar_grid = info
    except (AttributeError, tk.TclError):
        pass


def _restore_grid(widget: Any) -> None:
    info = getattr(widget, "_ux_toolbar_grid", None)
    if not isinstance(info, dict) or not info:
        return
    try:
        widget.grid_configure(**info)
    except tk.TclError:
        pass


def _toolbar_parts(app: Any) -> tuple[Any | None, Any | None, Any | None, Any | None]:
    stop = getattr(app, "stop_button", None)
    progress = getattr(app, "progress", None)
    if stop is None or progress is None:
        return None, None, None, None
    try:
        actions = stop.master
        controls = actions.master
        progress_frame = progress.master
    except (AttributeError, tk.TclError):
        return None, None, None, None

    tempo = next(
        (
            child
            for child in _children(controls)
            if child is not actions
            and child is not progress_frame
            and _contains_class(child, "TScale")
        ),
        None,
    )
    return controls, tempo, progress_frame, actions


def _wrap_progress_copy(progress_frame: Any, width: int) -> None:
    if progress_frame is None:
        return
    for widget in _children(progress_frame):
        if widget.winfo_class() != "TLabel":
            continue
        try:
            widget.configure(wraplength=max(220, width - 24), justify="left")
        except tk.TclError:
            pass


def _reflow_bottom_toolbar(app: Any) -> None:
    controls, tempo, progress_frame, actions = _toolbar_parts(app)
    if controls is None or progress_frame is None or actions is None:
        return
    try:
        width = max(1, int(controls.winfo_width()))
    except (tk.TclError, TypeError, ValueError):
        return

    for widget in (tempo, progress_frame, actions):
        _save_grid(widget)

    mode = "wide" if width >= _WIDE_AT else "medium" if width >= _STACK_AT else "stacked"
    if getattr(controls, "_ux_toolbar_mode", None) == mode:
        _wrap_progress_copy(progress_frame, width)
        return
    controls._ux_toolbar_mode = mode

    try:
        # The old Preset group is intentionally hidden by the product UI, so
        # only move the three still-visible quick-control groups.
        for column in range(5):
            controls.columnconfigure(column, weight=0)
        for row in range(3):
            controls.rowconfigure(row, weight=0)

        if mode == "wide":
            if tempo is not None:
                _restore_grid(tempo)
            _restore_grid(progress_frame)
            _restore_grid(actions)
            controls.columnconfigure(3, weight=1)
        elif mode == "medium":
            controls.columnconfigure(0, weight=1)
            controls.columnconfigure(1, weight=0)
            if tempo is not None:
                tempo.grid_configure(row=0, column=0, columnspan=1, sticky="ew", padx=(0, 10), pady=0)
            actions.grid_configure(row=0, column=1, columnspan=1, sticky="e", padx=0, pady=0)
            progress_frame.grid_configure(
                row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=(8, 0)
            )
        else:
            controls.columnconfigure(0, weight=1)
            actions.grid_configure(row=0, column=0, columnspan=1, sticky="w", padx=0, pady=0)
            if tempo is not None:
                tempo.grid_configure(row=1, column=0, columnspan=1, sticky="ew", padx=0, pady=(7, 0))
            progress_frame.grid_configure(
                row=2, column=0, columnspan=1, sticky="ew", padx=0, pady=(7, 0)
            )
    except tk.TclError:
        return
    _wrap_progress_copy(progress_frame, width)


def install_compact_toolbar_patch() -> None:
    """Reflow Studio's permanent playback toolbar instead of clipping it."""
    if getattr(full_ui, "_compact_toolbar_patch_installed", False):
        return

    original_root = full_ui._responsive_root
    original_finalize = full_ui._finalize_app_ui

    def responsive_root(app: Any, width: int | None = None) -> None:
        original_root(app, width)
        _reflow_bottom_toolbar(app)

    def finalize(app: Any) -> None:
        original_finalize(app)
        controls, _tempo, _progress, _actions = _toolbar_parts(app)
        if controls is not None:
            try:
                controls.bind("<Configure>", lambda _event: _reflow_bottom_toolbar(app), add="+")
                app.after_idle(lambda: _reflow_bottom_toolbar(app))
            except tk.TclError:
                pass

    full_ui._responsive_root = responsive_root
    full_ui._finalize_app_ui = finalize
    full_ui._compact_toolbar_patch_installed = True
