from __future__ import annotations

import tkinter as tk
from typing import Any


def _force_unmap_band_frame(app: Any) -> None:
    """Hide the real Band Room widget even before an overlay entry exists."""
    frame = getattr(app, "_band_frame", None)
    if frame is None:
        return
    for method_name in ("grid_remove", "pack_forget", "place_forget"):
        try:
            getattr(frame, method_name)()
        except (tk.TclError, AttributeError):
            pass


def install_band_visibility_guard() -> None:
    """Preserve Band Mode's disabled-by-default contract after overlay patching."""
    import band_ui

    if getattr(band_ui, "_band_visibility_guard_2026_installed", False):
        return

    original = band_ui._set_band_frame_visible

    def set_band_frame_visible(app: Any, visible: bool) -> None:
        # ui_band_responsive_2026 replaces the original grid hide with a generic
        # feature-overlay hide. During App construction the Band Room has not yet
        # been registered as an overlay, so that generic hide cannot find it and
        # the freshly-gridded frame leaks into the main player even though Band
        # Mode is false. Physically unmap first; registered overlays still go
        # through the normal hide path immediately afterward.
        if not visible:
            _force_unmap_band_frame(app)
        original(app, visible)

    band_ui._set_band_frame_visible = set_band_frame_visible
    band_ui._band_visibility_guard_2026_installed = True
