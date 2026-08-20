from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Iterable


def filter_midi_names(names: Iterable[str], query: str) -> list[str]:
    """Return local MIDI display names matching every search word."""
    items = list(names)
    tokens = [token for token in query.casefold().split() if token]
    if not tokens:
        return items
    return [
        name
        for name in items
        if all(token in name.casefold() for token in tokens)
    ]


def _find_local_tab(app: Any) -> Any | None:
    notebook = getattr(app, "song_source_notebook", None)
    if notebook is None:
        return None
    try:
        for tab_id in notebook.tabs():
            if str(notebook.tab(tab_id, "text")) == "Local":
                return app.nametowidget(tab_id)
    except tk.TclError:
        return None
    return None


def _apply_local_filter(app: Any) -> None:
    combo = getattr(app, "midi_combo", None)
    query_var = getattr(app, "local_search_var", None)
    if combo is None or query_var is None:
        return

    try:
        names = list(getattr(app, "_midi_lookup", {}).keys())
        query = query_var.get()
        filtered = filter_midi_names(names, query)
        combo.configure(values=filtered)
        if hasattr(app, "local_search_count_var"):
            if query.strip():
                app.local_search_count_var.set(f"{len(filtered)} / {len(names)}")
            else:
                app.local_search_count_var.set(f"{len(names)} songs")
    except tk.TclError:
        pass


def _attach_local_search(app: Any) -> None:
    local_tab = _find_local_tab(app)
    if local_tab is None or hasattr(app, "local_search_var"):
        return

    # The existing Local tab is intentionally left intact; move its rows down
    # by one and insert only a compact filename filter above the song picker.
    for child in list(local_tab.winfo_children()):
        try:
            info = child.grid_info()
            if info and "row" in info:
                child.grid_configure(row=int(info["row"]) + 1)
        except (tk.TclError, TypeError, ValueError):
            continue

    app.local_search_var = tk.StringVar(master=app)
    app.local_search_count_var = tk.StringVar(master=app, value="0 songs")

    search_row = ttk.Frame(local_tab)
    search_row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 7))
    search_row.columnconfigure(1, weight=1)
    ttk.Label(search_row, text="Search").grid(row=0, column=0, sticky="w", padx=(0, 8))
    app.local_search_entry = ttk.Entry(search_row, textvariable=app.local_search_var)
    app.local_search_entry.grid(row=0, column=1, sticky="ew")
    ttk.Label(
        search_row,
        textvariable=app.local_search_count_var,
        style="Hint.TLabel",
        width=10,
        anchor="e",
    ).grid(row=0, column=2, sticky="e", padx=(8, 0))

    app.local_search_var.trace_add("write", lambda *_args: _apply_local_filter(app))
    _apply_local_filter(app)


def _build_ui(self: Any) -> None:
    self._local_search_original_build_ui()
    _attach_local_search(self)


def _reload_midi_library(
    self: Any,
    analyze: bool = True,
    preferred_display: str | None = None,
) -> None:
    self._local_search_original_reload_midi_library(
        analyze=analyze,
        preferred_display=preferred_display,
    )
    _apply_local_filter(self)


def install_local_search_integration(app_module: Any) -> None:
    """Add local filename search without changing MIDI loading/playback logic."""
    app_class = app_module.App
    if getattr(app_class, "_local_search_integration_installed", False):
        return

    app_class._local_search_original_build_ui = app_class._build_ui
    app_class._local_search_original_reload_midi_library = app_class._reload_midi_library
    app_class._build_ui = _build_ui
    app_class._reload_midi_library = _reload_midi_library
    app_class._local_search_integration_installed = True
