from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Iterable

import online_ui


VISIBLE_LOCAL_ROWS = 5


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


def _schedule_resize(app: Any) -> None:
    """Resize after the Local browser exists, including on the first app view."""
    try:
        app.after_idle(lambda: online_ui._resize_source_notebook(app))
        app.after(40, lambda: online_ui._resize_source_notebook(app))
    except (tk.TclError, AttributeError):
        pass


def _selected_result_name(app: Any) -> str | None:
    tree = getattr(app, "local_song_tree", None)
    if tree is None:
        return None
    try:
        selected = tree.selection()
        if not selected:
            return None
        iid = str(selected[0])
        if not iid.startswith("local:"):
            return None
        index = int(iid.split(":", 1)[1])
        names = getattr(app, "_local_result_names", [])
        if 0 <= index < len(names):
            return str(names[index])
    except (tk.TclError, TypeError, ValueError, IndexError):
        return None
    return None


def _local_song_selected(app: Any) -> None:
    name = _selected_result_name(app)
    if not name or name not in getattr(app, "_midi_lookup", {}):
        return
    try:
        app.midi_display_var.set(name)
        app._midi_selected()
    except tk.TclError:
        pass


def _render_results(app: Any, query: str | None = None) -> None:
    tree = getattr(app, "local_song_tree", None)
    if tree is None:
        return

    if query is None:
        query = str(getattr(app, "_local_applied_query", ""))
    app._local_applied_query = query
    names = list(getattr(app, "_midi_lookup", {}).keys())
    filtered = filter_midi_names(names, query)
    app._local_result_names = filtered

    try:
        for iid in tree.get_children():
            tree.delete(iid)
        for index, name in enumerate(filtered):
            tree.insert("", "end", iid=f"local:{index}", text=name)

        selected_name = app.midi_display_var.get()
        if selected_name in filtered:
            index = filtered.index(selected_name)
            iid = f"local:{index}"
            tree.selection_set(iid)
            tree.focus(iid)
            tree.see(iid)

        if hasattr(app, "local_search_count_var"):
            if query.strip():
                app.local_search_count_var.set(
                    f"{len(filtered)} match(es) • {len(names)} total • scroll for more"
                )
            else:
                app.local_search_count_var.set(
                    f"{len(names)} song(s) • showing {VISIBLE_LOCAL_ROWS} rows at a time"
                    if names
                    else "No MIDI files yet"
                )
    except tk.TclError:
        return

    _schedule_resize(app)


def _run_search(app: Any) -> None:
    try:
        query = app.local_search_var.get()
    except tk.TclError:
        query = ""
    _render_results(app, query)


def _attach_local_browser(app: Any) -> None:
    local_tab = _find_local_tab(app)
    if local_tab is None or hasattr(app, "local_search_var"):
        return

    # Keep the original Combobox object alive but hidden because the established
    # library loader still updates it internally. Everything the user sees in
    # Local is rebuilt as the simpler folder + search + five-row browser.
    original_combo = getattr(app, "midi_combo", None)
    for child in list(local_tab.winfo_children()):
        try:
            if child is original_combo:
                child.grid_remove()
            else:
                child.destroy()
        except tk.TclError:
            continue

    local_tab.columnconfigure(0, weight=1)
    local_tab.rowconfigure(2, weight=1)

    app.local_search_var = tk.StringVar(master=app)
    app.local_search_count_var = tk.StringVar(master=app, value="No MIDI files yet")
    app._local_applied_query = ""
    app._local_result_names: list[str] = []

    ttk.Button(
        local_tab,
        text="Open folder",
        command=app._open_midi_folder,
    ).grid(row=0, column=0, sticky="w")

    search_row = ttk.Frame(local_tab)
    search_row.grid(row=1, column=0, sticky="ew", pady=(8, 7))
    search_row.columnconfigure(0, weight=1)
    app.local_search_entry = ttk.Entry(
        search_row,
        textvariable=app.local_search_var,
    )
    app.local_search_entry.grid(row=0, column=0, sticky="ew")
    app.local_search_entry.bind("<Return>", lambda _event: _run_search(app))
    ttk.Button(
        search_row,
        text="Search",
        command=lambda: _run_search(app),
    ).grid(row=0, column=1, padx=(8, 0))

    results = ttk.Frame(local_tab)
    results.grid(row=2, column=0, sticky="nsew")
    results.columnconfigure(0, weight=1)
    results.rowconfigure(0, weight=1)

    app.local_song_tree = ttk.Treeview(
        results,
        show="tree",
        height=VISIBLE_LOCAL_ROWS,
        selectmode="browse",
    )
    app.local_song_tree.column("#0", width=560, minwidth=220, stretch=True)
    app.local_song_tree.grid(row=0, column=0, sticky="nsew")
    app.local_song_tree.bind(
        "<<TreeviewSelect>>",
        lambda _event: _local_song_selected(app),
    )
    scrollbar = ttk.Scrollbar(
        results,
        orient="vertical",
        command=app.local_song_tree.yview,
    )
    scrollbar.grid(row=0, column=1, sticky="ns")
    app.local_song_tree.configure(yscrollcommand=scrollbar.set)

    ttk.Label(
        local_tab,
        textvariable=app.local_search_count_var,
        style="Hint.TLabel",
    ).grid(row=3, column=0, sticky="w", pady=(6, 0))

    _render_results(app, "")
    _schedule_resize(app)


def _build_ui(self: Any) -> None:
    self._local_search_original_build_ui()
    _attach_local_browser(self)


def _reload_midi_library(
    self: Any,
    analyze: bool = True,
    preferred_display: str | None = None,
) -> None:
    self._local_search_original_reload_midi_library(
        analyze=analyze,
        preferred_display=preferred_display,
    )
    _render_results(self)


def install_local_search_integration(app_module: Any) -> None:
    """Replace the Local picker with a small searchable MIDI library browser."""
    app_class = app_module.App
    if getattr(app_class, "_local_search_integration_installed", False):
        return

    app_class._local_search_original_build_ui = app_class._build_ui
    app_class._local_search_original_reload_midi_library = app_class._reload_midi_library
    app_class._build_ui = _build_ui
    app_class._reload_midi_library = _reload_midi_library
    app_class._local_search_integration_installed = True
