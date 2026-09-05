from __future__ import annotations

import tkinter as tk
from typing import Any

import ui_overlay_coordinator_2026 as coordinator


def _extension_widgets(panel: Any) -> list[Any]:
    """Return Calibration add-ons in their original desktop row/column order."""
    widgets: list[tuple[int, int, Any]] = []
    try:
        children = tuple(panel.winfo_children())
    except (tk.TclError, AttributeError):
        return []

    for widget in children:
        info = getattr(widget, "_ux_calibration_grid", None)
        if not isinstance(info, dict):
            continue
        try:
            row = int(info.get("row", -1))
            column = int(info.get("column", -1))
        except (TypeError, ValueError):
            continue
        # Rows 0-3 belong to the base Calibration Lab. Studio latency,
        # guided-search copy and reset/provenance controls are appended from
        # row 4 onward by separate feature modules.
        if row >= 4:
            widgets.append((row, column, widget))

    widgets.sort(key=lambda item: (item[0], item[1]))
    return [widget for _row, _column, widget in widgets]


def _reflow_extensions(app: Any) -> None:
    panel = getattr(app, "_calibration_panel", None)
    if panel is None:
        return
    try:
        width = max(1, int(panel.winfo_width()))
    except (tk.TclError, TypeError, ValueError):
        return

    # The coordinator restores every child's remembered desktop grid before it
    # returns to wide mode, so this layer only needs to intervene in compact mode.
    if width >= 700:
        return

    for index, widget in enumerate(_extension_widgets(panel)):
        row = 8 + index
        try:
            class_name = str(widget.winfo_class())
            sticky = "ew" if class_name in {"TLabel", "TSeparator"} else "w"
            widget.grid_configure(
                row=row,
                column=0,
                columnspan=4,
                sticky=sticky,
                padx=0,
                pady=(7, 0),
            )
            if class_name == "TLabel":
                widget.configure(wraplength=max(220, width - 30), justify="left")
        except (tk.TclError, TypeError):
            pass


def install_calibration_extension_reflow() -> None:
    """Stack Studio-only Calibration add-ons below the compact base form."""
    if getattr(coordinator, "_calibration_extension_reflow_installed", False):
        return

    original = coordinator._reflow_calibration_panel

    def reflow(app: Any) -> None:
        original(app)
        _reflow_extensions(app)

    coordinator._reflow_calibration_panel = reflow
    coordinator._calibration_extension_reflow_installed = True
