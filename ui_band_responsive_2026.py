from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

import ui_full_overhaul_2026 as full_ui


_BASE_EXTENSION_ROW = 8


def _children(widget: Any) -> tuple[Any, ...]:
    try:
        return tuple(widget.winfo_children())
    except (AttributeError, tk.TclError):
        return ()


def _saved_grid_row(widget: Any, key: str) -> int | None:
    info = getattr(widget, key, None)
    if not isinstance(info, dict):
        return None
    try:
        return int(info.get("row", -1))
    except (TypeError, ValueError):
        return None


def _restore_saved_grid(widget: Any, key: str) -> None:
    info = getattr(widget, key, None)
    if not isinstance(info, dict) or not info:
        return
    try:
        widget.grid_configure(**info)
    except tk.TclError:
        pass


def _label_for_variable(frame: Any, variable: Any) -> Any | None:
    if variable is None:
        return None
    target = str(variable)
    for widget in _children(frame):
        try:
            if str(widget.cget("textvariable")) == target:
                return widget
        except (tk.TclError, TypeError):
            pass
    return None


def _reflow_lineup(app: Any, outer_width: int, narrow: bool) -> None:
    frame = getattr(app, "_band_lineup_frame", None)
    checks = getattr(app, "_band_lineup_checks", None)
    if frame is None or not isinstance(checks, dict):
        return

    full_ui._remember_grid_children(frame, "_ux_lineup_grid")
    compact = narrow and outer_width < 470
    if not compact:
        for child in _children(frame):
            _restore_saved_grid(child, "_ux_lineup_grid")
        try:
            for column in range(4):
                frame.columnconfigure(column, weight=0)
        except tk.TclError:
            pass
    else:
        ordered = [
            checks[part]
            for part in ("keyboard", "guitar", "bass", "drums")
            if part in checks
        ]
        try:
            for column in range(4):
                frame.columnconfigure(column, weight=0)
            frame.columnconfigure(0, weight=1)
            frame.columnconfigure(1, weight=1)
            for index, check in enumerate(ordered):
                row, column = divmod(index, 2)
                check.grid_configure(
                    row=row,
                    column=column,
                    sticky="w",
                    padx=(0 if column == 0 else 10, 0),
                    pady=(0, 3),
                )
            hint = next(
                (child for child in _children(frame) if child.winfo_class() == "TLabel"),
                None,
            )
            if hint is not None:
                hint.grid_configure(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
                hint.configure(wraplength=max(210, outer_width - 44), justify="left")
        except tk.TclError:
            pass

    for child in _children(frame):
        if child.winfo_class() != "TLabel":
            continue
        try:
            child.configure(wraplength=max(210, outer_width - 44), justify="left")
        except tk.TclError:
            pass


def _reflow_room_midi(app: Any, outer_width: int, narrow: bool) -> None:
    frame = getattr(app, "_band_share_frame", None)
    if frame is None:
        return

    full_ui._remember_grid_children(frame, "_ux_room_midi_grid")
    if not narrow:
        for child in _children(frame):
            _restore_saved_grid(child, "_ux_room_midi_grid")
        try:
            frame.columnconfigure(0, weight=1)
            frame.columnconfigure(1, weight=0)
            frame.columnconfigure(2, weight=0)
        except tk.TclError:
            pass
        return

    song = _label_for_variable(frame, getattr(app, "_band_room_song_var", None))
    status = _label_for_variable(frame, getattr(app, "_band_share_status_var", None))
    checkbox = getattr(app, "_band_share_checkbox", None)
    download = getattr(app, "_band_download_button", None)
    try:
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=0)
        frame.columnconfigure(2, weight=0)
        if song is not None:
            song.grid_configure(row=0, column=0, columnspan=3, sticky="ew")
            song.configure(wraplength=max(210, outer_width - 44), justify="left")
        if checkbox is not None:
            checkbox.grid_configure(row=1, column=0, columnspan=3, sticky="w", padx=0, pady=(5, 0))
        if download is not None:
            download.grid_configure(row=2, column=0, columnspan=3, sticky="w", padx=0, pady=(5, 0))
        if status is not None:
            status.grid_configure(row=3, column=0, columnspan=3, sticky="ew", pady=(5, 0))
            status.configure(wraplength=max(210, outer_width - 44), justify="left")
    except tk.TclError:
        pass


def _extension_children(frame: Any) -> list[tuple[int, Any]]:
    result: list[tuple[int, Any]] = []
    for child in _children(frame):
        row = _saved_grid_row(child, "_ux_band_grid")
        if row is not None and row >= 6:
            result.append((row, child))
    result.sort(key=lambda item: item[0])
    return result


def _finish_band_reflow(app: Any) -> None:
    frame = getattr(app, "_band_frame", None)
    if frame is None:
        return
    try:
        width = max(1, int(frame.winfo_width()))
    except (tk.TclError, TypeError, ValueError):
        return

    # ui_full_overhaul_2026 stores the original extension rows before it moves
    # the base Band Room controls. Preserve those rows as the canonical wide
    # layout, then reserve rows 8+ for every extension on narrow layouts.
    full_ui._remember_grid_children(frame, "_ux_band_grid")
    narrow = width < 560
    extensions = _extension_children(frame)

    if narrow:
        for index, (_original_row, child) in enumerate(extensions):
            try:
                child.grid_configure(
                    row=_BASE_EXTENSION_ROW + index,
                    column=0,
                    columnspan=4,
                    sticky="ew",
                    pady=(7, 0),
                )
            except tk.TclError:
                pass
    else:
        for _original_row, child in extensions:
            _restore_saved_grid(child, "_ux_band_grid")

    _reflow_lineup(app, width, narrow)
    _reflow_room_midi(app, width, narrow)


def _band_overlay_visible(app: Any) -> bool:
    return bool(full_ui._overlay_state(app, "band").get("visible"))


def _hide_band_room(app: Any) -> None:
    full_ui._hide_feature_overlay(app, "band")


def _show_band_room(app: Any) -> None:
    frame = getattr(app, "_band_frame", None)
    if frame is None:
        return
    enabled = getattr(app, "_band_enabled_var", None)
    try:
        if enabled is not None and not bool(enabled.get()):
            return
    except tk.TclError:
        return

    # Band Mode is a secondary workflow. It should not permanently consume the
    # center player's vertical space, especially at 1280x720/high-DPI sizes.
    full_ui._hide_feature_overlay(app, "custom")
    full_ui._hide_feature_overlay(app, "calibration")
    full_ui._show_feature_overlay(
        app,
        "band",
        frame,
        860,
        lambda: _hide_band_room(app),
    )
    try:
        frame.update_idletasks()
    except tk.TclError:
        pass
    full_ui._reflow_band_panel(app)
    full_ui._refresh_feature_overlay(app, "band")


def _set_band_frame_visible(app: Any, visible: bool) -> None:
    if visible:
        _show_band_room(app)
    else:
        _hide_band_room(app)


def _sync_band_room_button(app: Any) -> None:
    button = getattr(app, "_ux_band_room_button", None)
    if button is None:
        return
    enabled = getattr(app, "_band_enabled_var", None)
    try:
        active = bool(enabled is not None and enabled.get())
        button.configure(state="normal" if active else "disabled")
    except tk.TclError:
        pass


def _position_band_room_button(app: Any) -> None:
    button = getattr(app, "_ux_band_room_button", None)
    setup = getattr(app, "_product_setup_frame", None)
    if button is None or setup is None:
        return
    try:
        width = max(1, int(setup.winfo_width()))
        narrow = width < 500
        button.grid_configure(
            row=7 if narrow else 4,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(6, 0),
        )
    except (tk.TclError, TypeError, ValueError):
        pass


def _add_band_room_button(app: Any) -> None:
    setup = getattr(app, "_product_setup_frame", None)
    variable = getattr(app, "_band_enabled_var", None)
    if setup is None or variable is None or getattr(app, "_ux_band_room_button", None) is not None:
        return
    try:
        button = ttk.Button(setup, text="Band room…", command=lambda: _show_band_room(app))
        app._ux_band_room_button = button
        _position_band_room_button(app)
        _sync_band_room_button(app)
        variable.trace_add("write", lambda *_args: app.after_idle(lambda: _sync_band_room_button(app)))
    except tk.TclError:
        pass


def install_band_responsive_patch() -> None:
    """Keep the full Band Mode workflow responsive without crowding the player."""
    if getattr(full_ui, "_band_extension_responsive_patch_installed", False):
        return

    import band_ui

    original_reflow = full_ui._reflow_band_panel
    original_root = full_ui._responsive_root
    original_setup = full_ui._reflow_primary_setup
    original_escape = full_ui._escape
    original_finalize = full_ui._finalize_app_ui

    def reflow_band_panel(app: Any) -> None:
        original_reflow(app)
        _finish_band_reflow(app)

    def responsive_root(app: Any, width: int | None = None) -> None:
        original_root(app, width)
        _position_band_room_button(app)
        if _band_overlay_visible(app):
            full_ui._refresh_feature_overlay(app, "band")

    def reflow_primary_setup(app: Any) -> None:
        original_setup(app)
        _position_band_room_button(app)

    def escape(app: Any):
        if _band_overlay_visible(app):
            _hide_band_room(app)
            return "break"
        return original_escape(app)

    def finalize(app: Any) -> None:
        original_finalize(app)
        _add_band_room_button(app)
        _position_band_room_button(app)

    full_ui._reflow_band_panel = reflow_band_panel
    full_ui._responsive_root = responsive_root
    full_ui._reflow_primary_setup = reflow_primary_setup
    full_ui._escape = escape
    full_ui._finalize_app_ui = finalize
    band_ui._set_band_frame_visible = _set_band_frame_visible
    full_ui._band_extension_responsive_patch_installed = True
