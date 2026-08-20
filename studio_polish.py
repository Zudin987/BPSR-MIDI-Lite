from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

import online_ui
import studio_ui


def _schedule_resize(app: Any) -> None:
    try:
        app.after_idle(lambda: online_ui._resize_source_notebook(app))
    except (tk.TclError, AttributeError):
        pass


def _decorate_studio_ui(app: Any) -> None:
    save_button = getattr(app, "youtube_save_button", None)
    if save_button is not None:
        try:
            save_button.configure(text="Save MIDI to Local")
        except tk.TclError:
            pass

    tab = getattr(app, "youtube_tab", None)
    if tab is not None and not hasattr(app, "youtube_instrumental_tip"):
        app.youtube_instrumental_tip = ttk.Label(
            tab,
            text=(
                "Tip: instrumental, piano, guitar, or bass versions usually convert much cleaner "
                "than full vocal/full-band mixes."
            ),
            style="Hint.TLabel",
            wraplength=610,
            justify="left",
        )
        app.youtube_instrumental_tip.grid(
            row=4,
            column=0,
            sticky="w",
            pady=(8, 0),
        )

    notebook = getattr(app, "song_source_notebook", None)
    if notebook is not None:
        try:
            notebook.bind(
                "<<NotebookTabChanged>>",
                lambda _event: _schedule_resize(app),
                add="+",
            )
        except tk.TclError:
            pass
    _schedule_resize(app)


def _build_ui(self: Any) -> None:
    self._studio_polish_original_build_ui()
    _decorate_studio_ui(self)


def install_studio_polish(app_module: Any) -> None:
    """Studio-only UI fixes layered after the Studio integration is installed."""
    app_class = app_module.App
    if getattr(app_class, "_studio_polish_installed", False):
        return

    original_search_finished = studio_ui._search_finished
    original_source_tab_changed = studio_ui._source_tab_changed

    def search_finished(app: Any, results: Any) -> None:
        original_search_finished(app, results)
        _schedule_resize(app)

    def source_tab_changed(app: Any) -> None:
        original_source_tab_changed(app)
        _schedule_resize(app)

    studio_ui._search_finished = search_finished
    studio_ui._source_tab_changed = source_tab_changed

    app_class._studio_polish_original_build_ui = app_class._build_ui
    app_class._build_ui = _build_ui
    app_class._studio_polish_installed = True
