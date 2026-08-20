from __future__ import annotations

import tkinter as tk
from typing import Any

import online_search_bridge
import online_ui


def _walk(widget: Any):
    yield widget
    try:
        for child in widget.winfo_children():
            yield from _walk(child)
    except tk.TclError:
        return


def _initialize(app: Any) -> None:
    _ORIGINAL_INITIALIZE(app)
    app.online_status_var.set(
        "Search Online Sequencer by song title, or paste a sequence link / numeric ID."
    )


def _build_song_source_ui(app: Any, songs: Any) -> None:
    _ORIGINAL_BUILD(app, songs)
    try:
        for widget in _walk(app.song_source_notebook):
            if widget.winfo_class() != "TButton":
                continue
            text = str(widget.cget("text"))
            if text == "Load link / ID":
                widget.configure(text="Search")
                app.online_search_button = widget
            elif text == "Find online MIDI ID":
                widget.configure(text="Verify once")
                app.online_verify_button = widget
    except tk.TclError:
        pass


def _search(app: Any) -> None:
    query = app.online_query_var.get().strip()
    if not query:
        app.online_status_var.set("Enter a song title, sequence link, or numeric ID first.")
        return
    _ORIGINAL_SEARCH(app)
    app.online_status_var.set("Searching Online Sequencer…")
    app.status_var.set("Searching Online Sequencer in the background…")


def _find_online_midi_id(app: Any) -> None:
    """One-time browser verification fallback; never asks users to copy anything."""
    query = app.online_query_var.get().strip()
    opened = online_search_bridge.open_verification(query)
    if opened:
        app.online_status_var.set(
            "Complete the Online Sequencer browser check once, then return here and press Search again. "
            "No link, ID, or cookie copying is needed."
        )
        app.status_var.set("Waiting for one-time Online Sequencer browser verification.")
    else:
        app.online_status_var.set("Could not open the browser verification page.")


def _source_tab_changed(app: Any) -> None:
    _ORIGINAL_SOURCE_CHANGED(app)
    try:
        if app.song_source_var.get() == "online" and not app.online_tree.selection():
            app.status_var.set("Search Online Sequencer by title or paste a link / ID.")
    except (tk.TclError, AttributeError):
        pass


def install_online_search_ui_2026() -> None:
    if getattr(online_ui, "_search_ui_2026_installed", False):
        return
    online_ui.initialize = _initialize
    online_ui.build_song_source_ui = _build_song_source_ui
    online_ui.search = _search
    online_ui.find_online_midi_id = _find_online_midi_id
    online_ui._source_tab_changed = _source_tab_changed
    online_ui._search_ui_2026_installed = True


_ORIGINAL_INITIALIZE = online_ui.initialize
_ORIGINAL_BUILD = online_ui.build_song_source_ui
_ORIGINAL_SEARCH = online_ui.search
_ORIGINAL_SOURCE_CHANGED = online_ui._source_tab_changed
