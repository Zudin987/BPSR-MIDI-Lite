from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

import ui_full_overhaul_2026 as full_ui
import ui_video_audit_2026 as audit


# Second recording-driven pass.  The first beta.8 pass fixed the large structural
# leaks; this layer removes redundant legacy surfaces and cleans the remaining
# normal-user copy/hierarchy visible throughout the supplied 77.8 s recording.
_FOCUS_MARGIN = 32


def _widget_text(widget: Any) -> str:
    try:
        return str(widget.cget("text"))
    except (AttributeError, TypeError, tk.TclError):
        return ""


def _hide(widget: Any) -> None:
    try:
        manager = str(widget.winfo_manager())
        if manager == "grid":
            widget.grid_remove()
        elif manager == "pack":
            widget.pack_forget()
        elif manager == "place":
            widget.place_forget()
    except (AttributeError, tk.TclError):
        pass


def _focus_geometry(app: Any, key: str) -> tuple[int, int, int, int]:
    """Give focused secondary pages breathing room even at 720 logical px."""
    state = full_ui._overlay_state(app, key)
    panel = state.get("panel")
    master = getattr(panel, "master", None) if panel is not None else None
    if panel is None or master is None:
        return 0, 0, 0, 0
    master_width, master_height = full_ui._safe_dimensions(master)
    max_width = int(state.get("max_width", 820))
    available_width = max(280, master_width - _FOCUS_MARGIN)
    width = min(max_width, available_width)
    try:
        panel.update_idletasks()
        requested = max(1, int(panel.winfo_reqheight()) + 16)
    except (tk.TclError, TypeError, ValueError):
        requested = master_height
    viewport = max(180, master_height - 24)
    maximum = max(0, requested - viewport)
    offset = max(0, min(int(state.get("offset", 0)), maximum))
    state["offset"] = offset
    return width, requested, viewport, maximum


def _retire_legacy_youtube_tab(app: Any) -> None:
    """Keep yt-dlp internally, but remove the obsolete standalone YouTube UI.

    Audio -> Band now owns normal song acquisition and already uses yt-dlp as an
    automatic fallback.  Leaving the old YouTube -> single core MIDI tab visible
    duplicated the same user decision and was a recurring source of stale status
    copy in the recording.
    """
    if bool(getattr(app, "_ux_legacy_youtube_retired", False)):
        return
    notebook = getattr(app, "song_source_notebook", None)
    tab = getattr(app, "youtube_tab", None)
    if notebook is None or tab is None:
        return
    try:
        tabs = tuple(str(value) for value in notebook.tabs())
        tab_id = str(tab)
        if tab_id not in tabs:
            app._ux_legacy_youtube_retired = True
            return
        if str(notebook.select()) == tab_id:
            notebook.select(0)
        notebook.forget(tab)
        app._ux_legacy_youtube_retired = True
    except (tk.TclError, TypeError):
        return


def _polish_shell(app: Any) -> None:
    """Remove duplicated labels and shorten desktop-facing product copy."""
    panel = getattr(app, "_gaming_library_panel", None)
    if panel is not None:
        hidden_songs_caption = False
        for widget in full_ui._walk(panel):
            text = _widget_text(widget)
            try:
                if text == "Songs" and not hidden_songs_caption and widget.winfo_class() == "TLabel":
                    _hide(widget)
                    hidden_songs_caption = True
                elif text.startswith("Local stays on this PC."):
                    widget.configure(
                        text="Local files stay on this PC. Online uses cache; Save to Local keeps a permanent MIDI.",
                        justify="left",
                    )
            except tk.TclError:
                pass

    version = str(getattr(getattr(app, "_modern_module", None), "APP_VERSION", ""))
    for widget in full_ui._walk(app):
        text = _widget_text(widget)
        try:
            if text == "BPSR MIDI" and version.startswith("Studio "):
                widget.configure(text="BPSR MIDI Studio")
            elif text == version and "band-accurate-beta." in version:
                short = version.removeprefix("Studio ").replace("-band-accurate-", " · ")
                widget.configure(text=short)
            elif text.startswith("Still uses C2–B6 during playback"):
                widget.configure(text="Page-safe playback: extra notes are remapped into C2–B6.")
        except tk.TclError:
            pass


def _find_arrangement_title(app: Any) -> Any | None:
    frame = getattr(app, "analysis_frame", None)
    if frame is None:
        return None
    for widget in full_ui._children(frame):
        if widget.winfo_class() == "TLabel" and _widget_text(widget) == "Arrangement impact":
            return widget
    return None


def _sync_details_chrome(app: Any) -> None:
    """Do not show an empty 'Arrangement impact' section while Details is closed."""
    title = getattr(app, "_ux_arrangement_impact_title", None)
    if title is None:
        title = _find_arrangement_title(app)
        app._ux_arrangement_impact_title = title
    anchor = getattr(app, "_product_impact_anchor", None)
    impact = getattr(app, "_product_impact_label", None)
    visible = bool(getattr(app, "_product_details_visible", False))
    if not visible:
        for widget in (anchor, title):
            if widget is not None:
                _hide(widget)
        return
    if impact is None:
        return
    try:
        if anchor is not None and not anchor.winfo_ismapped():
            anchor.pack(fill="x", pady=(8, 5), before=impact)
        if title is not None and not title.winfo_ismapped():
            title.pack(anchor="w", before=impact)
    except tk.TclError:
        pass


def _patch_details_toggle() -> None:
    original = full_ui._toggle_song_details
    if getattr(original, "_video_round2_details", False):
        return

    def toggle(app: Any) -> None:
        original(app)
        _sync_details_chrome(app)

    toggle._video_round2_details = True
    full_ui._toggle_song_details = toggle
    try:
        import ui_product_overhaul_v34 as product

        product._toggle_technical_details = toggle
    except Exception:
        pass


def _polish_band_room(app: Any) -> None:
    frame = getattr(app, "_band_frame", None)
    if frame is None:
        return
    replacements = {
        "Create": "Create room",
        "Join": "Join room",
        "Leave": "Leave room",
        "Start Band": "Start band",
        "Players / instruments present": "Players & instruments",
    }
    for widget in (frame, *full_ui._walk(frame)):
        text = _widget_text(widget)
        if text not in replacements:
            continue
        try:
            widget.configure(text=replacements[text])
        except tk.TclError:
            pass


def _polish_audio(owner: Any) -> None:
    """Keep the acquisition implementation out of the normal workflow copy."""
    try:
        current = str(owner.resolver_status.get())
        if (
            "spotDL" in current
            or "direct yt-dlp" in current
            or "Local audio" in current
            or "Search Apple catalogue" in current
        ):
            owner.resolver_status.set(
                "Automatic download is enabled. Studio tries the best match first and falls back automatically. "
                "Local audio always remains available."
            )
        if str(owner.status.get()).startswith("Choose or drop a song"):
            owner.status.set("Choose local audio or search for a song to begin.")
    except tk.TclError:
        pass

    root = getattr(owner, "workspace", None)
    if root is None:
        return
    replacements = {
        "Download & Analyze": "Download & Convert",
        "Analyze & Convert": "Convert audio",
        "First use downloads several GB of models.": "First conversion may download several GB of model files.",
    }
    for widget in full_ui._walk(root):
        text = _widget_text(widget)
        if text not in replacements:
            continue
        try:
            widget.configure(text=replacements[text])
        except tk.TclError:
            pass


def _patch_audio_copy() -> None:
    try:
        import studio_band_ui
    except Exception:
        return
    cls = studio_band_ui.BandAudioTab
    if getattr(cls, "_video_round2_copy_installed", False):
        return
    original_init = cls.__init__
    original_poll = cls.poll

    def init(self, app):
        original_init(self, app)
        _polish_audio(self)

    def poll(self):
        result = original_poll(self)
        try:
            hardware = str(self.hardware.get())
            if hardware.startswith("GPU detected"):
                self.hardware.set("GPU available · acceleration is used when supported.")
        except tk.TclError:
            pass
        return result

    cls.__init__ = init
    cls.poll = poll
    cls._video_round2_copy_installed = True


def _patch_finalize() -> None:
    original = full_ui._finalize_app_ui
    if getattr(original, "_video_round2_finalize", False):
        return

    def finalize(app: Any) -> None:
        original(app)
        _retire_legacy_youtube_tab(app)
        _polish_shell(app)
        _polish_band_room(app)
        _sync_details_chrome(app)
        try:
            app.after_idle(lambda: (
                _retire_legacy_youtube_tab(app),
                _polish_shell(app),
                _polish_band_room(app),
                _sync_details_chrome(app),
                full_ui._responsive_root(app),
            ))
        except tk.TclError:
            pass

    finalize._video_round2_finalize = True
    full_ui._finalize_app_ui = finalize


def install_video_audit_round2() -> None:
    if getattr(full_ui, "_video_audit_round2_installed", False):
        return

    # Both the original audit module and the public full-ui compatibility entry
    # point at the same geometry contract after this final layer is installed.
    audit._focus_geometry = _focus_geometry
    full_ui._overlay_geometry = _focus_geometry

    _patch_details_toggle()
    _patch_audio_copy()
    _patch_finalize()
    full_ui._video_audit_round2_installed = True
