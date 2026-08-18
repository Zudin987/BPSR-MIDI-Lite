from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from typing import Any

import online_ui


"""Optional Online Sequencer integration layered on top of modern_ui.

This module deliberately does not replace the proven v2.5 single-page UI or
MIDI planner. It swaps only the Song picker area and wraps a few lifecycle
methods for bookmarks, online cache selection, and re-analysis.
"""


def _find_song_frame(root: Any) -> Any | None:
    """Find the existing '2  Song' LabelFrame without coupling to widget paths."""
    pending = list(root.winfo_children())
    while pending:
        widget = pending.pop(0)
        try:
            if widget.winfo_class() == "TLabelframe" and str(widget.cget("text")).strip() in {
                "2 Song",
                "2  Song",
            }:
                return widget
            pending.extend(widget.winfo_children())
        except tk.TclError:
            continue
    return None


def _replace_song_picker(self: Any) -> None:
    songs = _find_song_frame(self)
    if songs is None:
        raise RuntimeError("Could not locate the Song section for Online Sequencer integration.")

    # Remove only the old row-0 local picker. Speed controls on row 1 are kept.
    old_combo = getattr(self, "midi_combo", None)
    if old_combo is not None:
        try:
            old_combo.destroy()
        except tk.TclError:
            pass

    for child in list(songs.winfo_children()):
        try:
            info = child.grid_info()
            row = int(info.get("row", -1))
            if row == 0:
                child.destroy()
                continue
            # Replace the old Local-only explanatory paragraph on row 2.
            if row == 2 and child.winfo_class() == "TLabel":
                child.destroy()
        except (tk.TclError, TypeError, ValueError):
            continue

    online_ui.build_song_source_ui(self, songs)
    ttk.Label(
        songs,
        text=(
            "Local keeps permanent MIDI files. Online Sequencer can search/check/play from temporary cache. "
            "Bookmarks remember online songs; Save to Local keeps an offline MIDI copy."
        ),
        style="Hint.TLabel",
        wraplength=620,
        justify="left",
    ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))


def _build_ui(self: Any) -> None:
    online_ui.initialize(self)
    self._online_original_build_ui()
    _replace_song_picker(self)


def _profile_changed(self: Any) -> None:
    self._online_original_profile_changed()
    online_ui.schedule_reanalysis(self)


def _instrument_changed(self: Any) -> None:
    self._online_original_instrument_changed()
    online_ui.schedule_reanalysis(self)


def _save_config(self: Any) -> None:
    self._online_original_save_config()
    if getattr(self, "_suspend_auto_analysis", False):
        return
    try:
        path = self._config_path()
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(data, dict):
            data = {}
        online_ui.save_bookmarks_to_config(self, data)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except (OSError, ValueError, TypeError, json.JSONDecodeError, tk.TclError):
        pass


def _load_config(self: Any) -> None:
    self._online_original_load_config()
    try:
        path = self._config_path()
        if not path.exists() and self._legacy_config_path().exists():
            path = self._legacy_config_path()
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if isinstance(data, dict):
            online_ui.load_bookmarks_from_config(self, data)
    except (OSError, ValueError, TypeError, json.JSONDecodeError, tk.TclError):
        pass


def _analyze(self: Any) -> None:
    self._online_original_analyze()

    if self.current_plan is None and not self.file_var.get():
        title, message = online_ui.empty_selection_message(self)
        self.suitability_var.set(title)
        self.analysis_var.set(message)
        return

    if self.current_plan is not None and self.song_source_var.get() in {"online", "bookmarks"}:
        suffix = online_ui.analysis_suffix(self)
        current = self.analysis_var.get()
        if suffix.strip() and suffix.strip() not in current:
            self.analysis_var.set(current + suffix)


def _reload_midi_library(
    self: Any,
    analyze: bool = True,
    preferred_display: str | None = None,
) -> None:
    # The modern UI's background folder poll calls this method. While an online
    # source is active, ignore that local refresh so it cannot overwrite the
    # temporary online song path. Switching back to Local explicitly reloads.
    if hasattr(self, "song_source_var") and not online_ui.is_local_source(self):
        return
    self._online_original_reload_midi_library(
        analyze=analyze,
        preferred_display=preferred_display,
    )


def install_online_integration(app_module: Any) -> None:
    """Layer the Online Sequencer library onto an already-installed modern_ui."""
    app_class = app_module.App

    app_class._online_original_build_ui = app_class._build_ui
    app_class._online_original_profile_changed = app_class._profile_changed
    app_class._online_original_instrument_changed = app_class._instrument_changed
    app_class._online_original_save_config = app_class._save_config
    app_class._online_original_load_config = app_class._load_config
    app_class._online_original_analyze = app_class._analyze
    app_class._online_original_reload_midi_library = app_class._reload_midi_library

    app_class._build_ui = _build_ui
    app_class._profile_changed = _profile_changed
    app_class._instrument_changed = _instrument_changed
    app_class._save_config = _save_config
    app_class._load_config = _load_config
    app_class._analyze = _analyze
    app_class._reload_midi_library = _reload_midi_library
