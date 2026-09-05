"""Small-screen resilience for the Studio Audio -> Band workspace.

Kept separate from the feature module so the beta UI can be tuned without
changing the conversion pipeline or the Lite application.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import studio_band_ui


def _forget(widget) -> None:
    manager = widget.winfo_manager()
    if manager == "pack":
        widget.pack_forget()
    elif manager == "grid":
        widget.grid_forget()


def _label_text(widget) -> str:
    try:
        return str(widget.cget("text"))
    except tk.TclError:
        return ""


def _refresh_scroll_region(canvas) -> None:
    """Synchronize a canvas scrollregion after responsive children reflow."""
    try:
        canvas.update_idletasks()
        bounds = canvas.bbox("all")
        if bounds:
            canvas.configure(scrollregion=bounds)
    except tk.TclError:
        pass


def _responsive_flow(frame, *, narrow_at: int, narrow_columns: int = 2) -> None:
    """Reflow a compact toolbar instead of letting its right side clip."""
    children = tuple(frame.winfo_children())
    if not children:
        return
    try:
        frame.grid_configure(sticky="ew")
    except tk.TclError:
        pass

    state = {"columns": None}

    def render(event=None):
        width = int(getattr(event, "width", 0) or frame.winfo_width() or narrow_at)
        columns = len(children) if width >= narrow_at else min(narrow_columns, len(children))
        if state["columns"] == columns:
            return
        state["columns"] = columns
        for child in children:
            _forget(child)
        for column in range(len(children)):
            frame.columnconfigure(column, weight=0)
        for index, child in enumerate(children):
            row, column = divmod(index, columns)
            child.grid(row=row, column=column, sticky="w", padx=(0, 7), pady=2)

    frame.bind("<Configure>", render, add="+")
    frame.after_idle(render)


def _responsive_manual_row(owner) -> None:
    frame = owner.manual_button.master
    entry = next((child for child in frame.winfo_children() if child is not owner.manual_button), None)
    if entry is None:
        return
    state = {"narrow": None}

    def render(event=None):
        width = int(getattr(event, "width", 0) or frame.winfo_width() or 480)
        narrow = width < 480
        if state["narrow"] == narrow:
            return
        state["narrow"] = narrow
        _forget(entry)
        _forget(owner.manual_button)
        frame.columnconfigure(0, weight=1)
        if narrow:
            entry.grid(row=0, column=0, sticky="ew")
            owner.manual_button.grid(row=1, column=0, sticky="w", pady=(6, 0))
        else:
            entry.grid(row=0, column=0, sticky="ew")
            owner.manual_button.grid(row=0, column=1, padx=(6, 0))

    frame.bind("<Configure>", render, add="+")
    frame.after_idle(render)


def _responsive_search_row(owner) -> None:
    frame = owner.music_search_entry.master
    combo = next((child for child in frame.winfo_children() if child.winfo_class() == "TCombobox"), None)
    setup = next((child for child in frame.winfo_children()
                  if child.winfo_class() == "TButton" and child is not owner.search_button), None)
    if combo is None or setup is None:
        return
    widgets = (owner.music_search_entry, combo, owner.search_button, setup)
    state = {"mode": None}

    def render(event=None):
        width = int(getattr(event, "width", 0) or frame.winfo_width() or 720)
        mode = "wide" if width >= 720 else "medium" if width >= 480 else "tiny"
        if state["mode"] == mode:
            return
        state["mode"] = mode
        for widget in widgets:
            _forget(widget)
        for column in range(4):
            frame.columnconfigure(column, weight=0)
        frame.columnconfigure(0, weight=1)
        if mode == "wide":
            owner.music_search_entry.grid(row=0, column=0, sticky="ew")
            combo.grid(row=0, column=1, padx=(6, 0))
            owner.search_button.grid(row=0, column=2, padx=(6, 0))
            setup.grid(row=0, column=3, padx=(6, 0))
        elif mode == "medium":
            owner.music_search_entry.grid(row=0, column=0, columnspan=3, sticky="ew")
            combo.grid(row=1, column=0, sticky="w", pady=(6, 0))
            owner.search_button.grid(row=1, column=1, padx=(6, 0), pady=(6, 0))
            setup.grid(row=1, column=2, padx=(6, 0), pady=(6, 0))
        else:
            owner.music_search_entry.grid(row=0, column=0, columnspan=2, sticky="ew")
            combo.grid(row=1, column=0, sticky="w", pady=(6, 0))
            owner.search_button.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(6, 0))
            setup.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

    frame.bind("<Configure>", render, add="+")
    frame.after_idle(render)


def _add_tree_horizontal_scroll(owner, tree, attribute: str) -> None:
    if hasattr(owner, attribute):
        return
    parent = tree.master
    scrollbar = ttk.Scrollbar(parent, orient="horizontal", command=tree.xview)
    tree.configure(xscrollcommand=scrollbar.set)
    scrollbar.grid(row=1, column=0, sticky="ew")
    setattr(owner, attribute, scrollbar)


def _split_workspace_notes(owner) -> None:
    """Prevent the two status labels from painting over each other."""
    body = owner.summary.master
    hardware = None
    model_note = None
    for child in body.winfo_children():
        if child.winfo_class() != "TLabel":
            continue
        try:
            if str(child.cget("textvariable")) == str(owner.hardware):
                hardware = child
        except tk.TclError:
            pass
        if _label_text(child) == "First use downloads several GB of models.":
            model_note = child
    if hardware is None or model_note is None:
        return

    for child in tuple(body.winfo_children()):
        if child is model_note:
            continue
        info = child.grid_info()
        if info and int(info.get("row", 0)) >= 3:
            child.grid_configure(row=int(info["row"]) + 1)
    hardware.grid_configure(row=2, column=0, sticky="w")
    model_note.grid_configure(row=3, column=0, sticky="w", pady=(0, 2))

    def wrap(event=None):
        width = max(240, int(getattr(event, "width", 0) or body.winfo_width()) - 10)
        hardware.configure(wraplength=width, justify="left")
        model_note.configure(wraplength=width, justify="left")

    body.bind("<Configure>", wrap, add="+")
    body.after_idle(wrap)


def _add_summary_horizontal_scroll(owner) -> None:
    tree = owner.summary
    body = tree.master
    info = tree.grid_info()
    if not info or hasattr(owner, "summary_hscrollbar"):
        return
    row = int(info["row"])
    for child in tuple(body.winfo_children()):
        if child is tree:
            continue
        child_info = child.grid_info()
        if child_info and int(child_info.get("row", 0)) > row:
            child.grid_configure(row=int(child_info["row"]) + 1)
    scrollbar = ttk.Scrollbar(body, orient="horizontal", command=tree.xview)
    tree.configure(xscrollcommand=scrollbar.set)
    scrollbar.grid(row=row + 1, column=0, sticky="ew", pady=(0, 4))
    owner.summary_hscrollbar = scrollbar
    tree.column("#0", width=90, minwidth=70, stretch=True)
    for name in ("notes", "melody", "rejected", "simplified", "shifted"):
        tree.column(name, width=90, minwidth=55, stretch=True)


def _find_direct_frame(body, predicate):
    for child in body.winfo_children():
        if child.winfo_class() != "TFrame":
            continue
        if any(predicate(grandchild) for grandchild in child.winfo_children()):
            return child
    return None


def _install_workspace_scroll_refresh(owner) -> None:
    """Keep scrolling accurate after toolbars gain/lose rows at runtime."""
    canvas = owner.workspace_canvas
    body = owner.summary.master
    pending = {"job": None}

    def schedule(_event=None):
        try:
            if pending["job"] is not None:
                canvas.after_cancel(pending["job"])
            pending["job"] = canvas.after_idle(lambda: (
                pending.__setitem__("job", None), _refresh_scroll_region(canvas)))
        except tk.TclError:
            pending["job"] = None

    # A descendant toolbar can change requested height without producing a
    # reliable body Configure event on every Windows/Tk scaling combination.
    # Listen at both levels and refresh after geometry settles.
    body.bind("<Configure>", schedule, add="+")
    owner.workspace.bind("<Configure>", schedule, add="+")
    for child in body.winfo_children():
        child.bind("<Configure>", schedule, add="+")
    schedule()


def _apply_workspace_responsiveness(owner) -> None:
    _responsive_manual_row(owner)
    _responsive_search_row(owner)
    _add_tree_horizontal_scroll(owner, owner.source_tree, "source_hscrollbar")
    _split_workspace_notes(owner)
    _add_summary_horizontal_scroll(owner)

    body = owner.summary.master
    controls = _find_direct_frame(body, lambda widget: _label_text(widget) == "Main Melody")
    listen = _find_direct_frame(body, lambda widget: _label_text(widget) == "▶ Full Band")
    muted = _find_direct_frame(body, lambda widget: widget.winfo_class() == "TCheckbutton")

    if controls is not None:
        _responsive_flow(controls, narrow_at=620, narrow_columns=2)
    _responsive_flow(owner.acquire_button.master, narrow_at=380, narrow_columns=1)
    _responsive_flow(owner.convert_button.master, narrow_at=650, narrow_columns=2)
    if listen is not None:
        _responsive_flow(listen, narrow_at=690, narrow_columns=3)
    if muted is not None:
        _responsive_flow(muted, narrow_at=650, narrow_columns=3)
    _responsive_flow(owner.save_button.master, narrow_at=560, narrow_columns=2)
    _install_workspace_scroll_refresh(owner)


def _responsive_source_setup(window) -> None:
    """Stack credential labels above fields on very narrow desktops."""
    canvas = getattr(window, "_scroll_canvas", None)
    if canvas is None:
        return
    content = next((child for child in canvas.winfo_children() if child.winfo_class() == "TFrame"), None)
    if content is None or getattr(content, "_responsive_form_installed", False):
        return
    entries = sorted((child for child in content.winfo_children() if child.winfo_class() == "TEntry"),
                     key=lambda widget: int(widget.grid_info().get("row", 0)))
    if not entries:
        return
    pairs = []
    for entry in entries:
        row = int(entry.grid_info().get("row", 0))
        label = next((child for child in content.winfo_children()
                      if child.winfo_class() == "TLabel"
                      and int(child.grid_info().get("row", -1)) == row
                      and int(child.grid_info().get("column", -1)) == 0), None)
        if label is not None:
            pairs.append((label, entry, row))
    if not pairs:
        return
    max_field_row = max(row for _, _, row in pairs)
    intro = next((child for child in content.winfo_children()
                  if int(child.grid_info().get("row", -1)) == 0), None)
    env_note = next((child for child in content.winfo_children()
                     if child.winfo_class() == "TLabel"
                     and int(child.grid_info().get("row", -1)) == max_field_row + 1), None)
    actions = next((child for child in content.winfo_children()
                    if child.winfo_class() == "TFrame"
                    and int(child.grid_info().get("row", -1)) == max_field_row + 2), None)
    state = {"narrow": None}
    content._responsive_form_installed = True

    def refresh():
        _refresh_scroll_region(canvas)

    def render(event=None):
        width = int(getattr(event, "width", 0) or content.winfo_width() or 600)
        narrow = width < 560
        if state["narrow"] == narrow:
            return
        state["narrow"] = narrow
        if narrow:
            for label, entry, _ in pairs:
                _forget(label)
                _forget(entry)
            content.columnconfigure(0, weight=1)
            content.columnconfigure(1, weight=0)
            for index, (label, entry, _) in enumerate(pairs):
                label.grid(row=1 + index * 2, column=0, sticky="w", pady=(4, 1))
                entry.grid(row=2 + index * 2, column=0, sticky="ew", padx=0, pady=(0, 2))
            tail_row = 1 + len(pairs) * 2
            if env_note is not None:
                env_note.grid_configure(row=tail_row, column=0, columnspan=1, sticky="ew")
            if actions is not None:
                actions.grid_configure(row=tail_row + 1, column=0, columnspan=1, sticky="w")
            if intro is not None:
                intro.grid_configure(row=0, column=0, columnspan=1, sticky="ew")
        else:
            content.columnconfigure(0, weight=0)
            content.columnconfigure(1, weight=1)
            for label, entry, row in pairs:
                label.grid(row=row, column=0, sticky="w", pady=3)
                entry.grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=3)
            if env_note is not None:
                env_note.grid_configure(row=max_field_row + 1, column=0, columnspan=2, sticky="ew")
            if actions is not None:
                actions.grid_configure(row=max_field_row + 2, column=0, columnspan=2, sticky="w")
            if intro is not None:
                intro.grid_configure(row=0, column=0, columnspan=2, sticky="ew")
        canvas.after_idle(refresh)

    content.bind("<Configure>", render, add="+")
    content.after_idle(render)


def install_responsive_band_audio() -> None:
    cls = studio_band_ui.BandAudioTab
    if getattr(cls, "_small_screen_responsive_installed", False):
        return

    original_init = cls.__init__
    original_source_setup = cls.source_setup

    def init(self, app):
        original_init(self, app)
        _apply_workspace_responsiveness(self)

    def source_setup(self):
        window = original_source_setup(self)
        if window is not None:
            window.after_idle(lambda: _responsive_source_setup(window) if window.winfo_exists() else None)
        return window

    cls.__init__ = init
    cls.source_setup = source_setup
    cls._small_screen_responsive_installed = True
