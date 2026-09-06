from __future__ import annotations

import tkinter as tk
from typing import Any

import ui_full_overhaul_2026 as full_ui
import ui_video_audit_2026 as audit


# Third recording-driven polish pass. This stays Studio-only and deliberately
# changes composition/copy only; playback, calibration math, Band networking and
# Audio -> Band inference/download behavior remain owned by their feature layers.
_CUSTOM_NARROW_AT = 620


def _text(widget: Any) -> str:
    try:
        return str(widget.cget("text"))
    except (AttributeError, TypeError, tk.TclError):
        return ""


def _prepare_custom_grid(app: Any) -> None:
    panel = getattr(app, "custom_settings_frame", None)
    if panel is None or getattr(panel, "_ux_round3_prepared", False):
        return
    panel._ux_round3_prepared = True
    panel._ux_round3_narrow = None
    panel._ux_round3_refresh_job = None

    # Save only widgets that are genuinely part of the visible Custom form.
    # Earlier feature layers intentionally grid_remove legacy page/speed rows;
    # an empty grid_info therefore means "keep retired" and is not resurrected.
    for child in tuple(panel.winfo_children()):
        try:
            info = dict(child.grid_info())
        except tk.TclError:
            continue
        if not info:
            continue
        info.pop("in", None)
        child._ux_round3_grid = info

    def configured(event: Any = None) -> None:
        width = int(getattr(event, "width", 0) or panel.winfo_width() or 780)
        _reflow_custom_panel(app, width)

    panel.bind("<Configure>", configured, add="+")
    try:
        panel.after_idle(configured)
    except tk.TclError:
        pass


def _schedule_custom_overlay_refresh(app: Any) -> None:
    panel = getattr(app, "custom_settings_frame", None)
    if panel is None:
        return
    old = getattr(panel, "_ux_round3_refresh_job", None)
    try:
        if old is not None:
            panel.after_cancel(old)
    except tk.TclError:
        pass

    def refresh() -> None:
        panel._ux_round3_refresh_job = None
        try:
            if full_ui._overlay_state(app, "custom").get("visible"):
                audit._refresh_focus(app, "custom")
        except (AttributeError, tk.TclError):
            pass

    try:
        panel._ux_round3_refresh_job = panel.after_idle(refresh)
    except tk.TclError:
        panel._ux_round3_refresh_job = None


def _reflow_custom_panel(app: Any, width: int | None = None) -> None:
    """Split the legacy 4-column Custom form into one field per row when narrow.

    The recording showed the right-hand Retrigger gap and the long help sentence
    being clipped. The old form has two logical fields per row: columns 0/1 and
    2/3. At compact width we keep each pair intact but move the right-hand pair
    to the next row. Unit labels sharing the control cell keep their padding, so
    e.g. "ms (0 = Auto)" remains attached to its spinbox rather than becoming a
    separate floating label.
    """
    panel = getattr(app, "custom_settings_frame", None)
    if panel is None:
        return
    _prepare_custom_grid(app)
    try:
        actual = max(1, int(width or panel.winfo_width()))
    except (tk.TclError, TypeError, ValueError):
        actual = 780
    narrow = actual < _CUSTOM_NARROW_AT
    if getattr(panel, "_ux_round3_narrow", None) == narrow:
        # Width can still change while remaining in the same mode; keep wrapping
        # text tied to the actual viewport.
        _wrap_custom_copy(app, actual)
        return
    panel._ux_round3_narrow = narrow

    try:
        for column in range(4):
            panel.columnconfigure(column, weight=0, uniform="")
        panel.columnconfigure(1, weight=1)
        if not narrow:
            # Restore the original two flexible value columns on a roomy panel.
            panel.columnconfigure(3, weight=1)
    except tk.TclError:
        pass

    for child in tuple(panel.winfo_children()):
        info = getattr(child, "_ux_round3_grid", None)
        if not info:
            continue
        if not narrow:
            try:
                child.grid_configure(**info)
            except tk.TclError:
                pass
            continue

        try:
            row = int(info.get("row", 0))
            column = int(info.get("column", 0))
            span = max(1, int(info.get("columnspan", 1)))
            new = dict(info)
            if column >= 2:
                new["row"] = row * 2 + 1
                new["column"] = column - 2
                new["columnspan"] = min(2, span)
            else:
                new["row"] = row * 2
                new["column"] = column
                # A wide combo may have spanned columns 1-3 in the desktop form.
                # In the compact 2-column form it simply owns the value column.
                new["columnspan"] = 1 if column == 1 else min(2, span)

            # Full-width checkboxes/help rows stay full width. The advanced hint
            # is the only normal visible four-column item after feature cleanup.
            if span >= 4 or child.winfo_class() == "TCheckbutton" and span >= 2:
                new["column"] = 0
                new["columnspan"] = 2
            if child.winfo_class() == "TCombobox":
                new["sticky"] = "ew"
            child.grid_configure(**new)
        except (tk.TclError, TypeError, ValueError):
            pass

    _wrap_custom_copy(app, actual)
    _schedule_custom_overlay_refresh(app)


def _wrap_custom_copy(app: Any, width: int) -> None:
    panel = getattr(app, "custom_settings_frame", None)
    if panel is None:
        return
    wrap = max(230, width - 30)
    hint_var = getattr(app, "_advanced_hint_var", None)
    target = str(hint_var) if hint_var is not None else ""
    for child in tuple(panel.winfo_children()):
        try:
            if target and child.winfo_class() == "TLabel" and str(child.cget("textvariable")) == target:
                child.configure(wraplength=wrap, justify="left")
            elif _text(child) == "ms (0 = Auto)":
                child.configure(text="ms · 0 = Auto")
        except (tk.TclError, TypeError):
            pass


def _remove_duplicate_library_caption(app: Any) -> None:
    """The outer 'MIDI Library' heading already names this surface."""
    panel = getattr(app, "_gaming_library_panel", None)
    if panel is None:
        return
    for widget in (panel, *full_ui._walk(panel)):
        try:
            if widget.winfo_class() in {"TLabelframe", "Labelframe"} and _text(widget) == "Songs":
                widget.configure(text="")
        except tk.TclError:
            pass


def _polish_primary_setup(app: Any) -> None:
    """Use labels that describe what the primary controls actually select."""
    frame = getattr(app, "_product_setup_frame", None)
    if frame is None:
        return
    for widget in (frame, *full_ui._walk(frame)):
        try:
            if widget.winfo_class() == "TLabel" and _text(widget) == "Unlocked category":
                widget.configure(text="Playback profile")
        except tk.TclError:
            pass


def _patch_custom_profile_summary() -> None:
    """Remove the stale 'panel below' direction after Custom became an overlay."""
    try:
        import playback_advanced_ui as advanced
    except Exception:
        return
    original = advanced._custom_profile_summary
    if getattr(original, "_video_round3_copy", False):
        return

    def summary(app: Any) -> tuple[str, str]:
        text, notice = original(app)
        text = text.replace(
            "Use the advanced panel below to tune mapping, chord detail, note timing and sustain.",
            "Open Custom tuning to adjust mapping, chord detail, note timing and sustain.",
        )
        return text, notice

    summary._video_round3_copy = True
    advanced._custom_profile_summary = summary


def _polish_audio_nested_copy(owner: Any) -> None:
    root = getattr(owner, "workspace", None)
    if root is None:
        return
    replacements = {
        "Main Melody": "Melody",
        "Stem Quality": "Separation",
    }
    for widget in full_ui._walk(root):
        text = _text(widget)
        if text not in replacements:
            continue
        try:
            widget.configure(text=replacements[text])
        except tk.TclError:
            pass
    try:
        current = str(owner.resolver_status.get())
        if current.startswith("Automatic download is enabled."):
            owner.resolver_status.set("Automatic download with fallback. Local audio always remains available.")
    except tk.TclError:
        pass


def _patch_audio_init() -> None:
    try:
        import studio_band_ui
    except Exception:
        return
    cls = studio_band_ui.BandAudioTab
    if getattr(cls, "_video_round3_copy_installed", False):
        return
    original_init = cls.__init__

    def init(self, app):
        original_init(self, app)
        _polish_audio_nested_copy(self)

    cls.__init__ = init
    cls._video_round3_copy_installed = True


def _patch_finalize() -> None:
    original = full_ui._finalize_app_ui
    if getattr(original, "_video_round3_finalize", False):
        return

    def finalize(app: Any) -> None:
        original(app)
        _remove_duplicate_library_caption(app)
        _polish_primary_setup(app)
        _prepare_custom_grid(app)
        try:
            app.after_idle(lambda: (
                _remove_duplicate_library_caption(app),
                _polish_primary_setup(app),
                _prepare_custom_grid(app),
                _reflow_custom_panel(app),
            ))
        except tk.TclError:
            pass

    finalize._video_round3_finalize = True
    full_ui._finalize_app_ui = finalize


def install_video_audit_round3() -> None:
    if getattr(full_ui, "_video_audit_round3_installed", False):
        return
    _patch_custom_profile_summary()
    _patch_audio_init()
    _patch_finalize()
    full_ui._video_audit_round3_installed = True
