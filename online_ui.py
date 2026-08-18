from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable

import online_sequencer as osq


AUTO_ANALYZE_RESULTS = 8


def initialize(app: Any) -> None:
    """Create Online Sequencer state before the Song UI is built."""
    # All Tk variables are created on the UI thread. Background workers receive
    # plain Python values only and return UI work through _online_ui_queue.
    app.song_source_var = tk.StringVar(master=app, value="local")
    app.online_query_var = tk.StringVar(master=app)
    app.online_status_var = tk.StringVar(
        master=app,
        value=(
            "Paste an Online Sequencer song link or numeric sequence ID here. "
            "It loads into temporary cache for BPSR analysis."
        ),
    )
    app._online_results: dict[int, osq.SearchResult] = {}
    app._online_bookmarks: dict[int, osq.SearchResult] = {}
    app._online_cached: dict[int, osq.CachedSequence] = {}
    app._online_fit: dict[int, tuple[str, str, str]] = {}
    app._online_fetching: set[int] = set()
    app._online_pending_saves: set[int] = set()
    app._online_selected_id: int | None = None
    app._bookmark_selected_id: int | None = None
    app._online_search_generation = 0
    app._online_reanalysis_job: str | None = None
    app._online_context_generation = 0
    app._online_worker_gate = threading.BoundedSemaphore(2)
    app._online_ui_queue: queue.Queue[Callable[[], None]] = queue.Queue()
    app.after(80, lambda: _drain_ui_queue(app))
    app.speed_var.trace_add("write", lambda *_args: schedule_reanalysis(app))
    osq.cleanup_cache()


def _drain_ui_queue(app: Any) -> None:
    try:
        while True:
            callback = app._online_ui_queue.get_nowait()
            try:
                callback()
            except Exception:  # noqa: BLE001 - never let an optional online callback break the app loop
                pass
    except queue.Empty:
        pass
    try:
        app.after(80, lambda: _drain_ui_queue(app))
    except Exception:  # root is closing
        pass


def _dispatch(app: Any, callback: Callable[[], None]) -> None:
    try:
        app._online_ui_queue.put(callback)
    except Exception:
        pass


def _worker(app: Any, action: Callable[[], None]) -> None:
    def run() -> None:
        with app._online_worker_gate:
            action()

    threading.Thread(target=run, daemon=True, name="bpsr-online-sequencer").start()


def is_local_source(app: Any) -> bool:
    try:
        return app.song_source_var.get() == "local"
    except Exception:
        return True


def build_song_source_ui(app: Any, songs: Any) -> None:
    """Build Local / Online Sequencer / Bookmarks as one simple Song chooser."""
    app.song_source_notebook = ttk.Notebook(songs)
    app.song_source_notebook.grid(row=0, column=0, columnspan=2, sticky="nsew")

    local_tab = ttk.Frame(app.song_source_notebook, padding=(8, 10, 8, 8))
    local_tab.columnconfigure(0, weight=1)
    app.song_source_notebook.add(local_tab, text="Local")

    app.midi_combo = ttk.Combobox(
        local_tab,
        textvariable=app.midi_display_var,
        state="readonly",
        values=(),
    )
    app.midi_combo.grid(row=0, column=0, sticky="ew")
    app.midi_combo.bind("<<ComboboxSelected>>", lambda _event: app._midi_selected())
    ttk.Button(local_tab, text="Open folder", command=app._open_midi_folder).grid(
        row=0, column=1, padx=(8, 0)
    )
    ttk.Label(
        local_tab,
        text="Permanent .mid/.midi files stored on this PC.",
        style="Hint.TLabel",
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(7, 0))

    online_tab = ttk.Frame(app.song_source_notebook, padding=(8, 10, 8, 8))
    online_tab.columnconfigure(0, weight=1)
    online_tab.rowconfigure(3, weight=1)
    app.song_source_notebook.add(online_tab, text="Online Sequencer")

    search_row = ttk.Frame(online_tab)
    search_row.grid(row=0, column=0, sticky="ew")
    search_row.columnconfigure(0, weight=1)
    app.online_search_entry = ttk.Entry(search_row, textvariable=app.online_query_var)
    app.online_search_entry.grid(row=0, column=0, sticky="ew")
    app.online_search_entry.bind("<Return>", lambda _event: search(app))
    ttk.Button(search_row, text="Load link / ID", command=lambda: search(app)).grid(
        row=0, column=1, padx=(8, 0)
    )
    ttk.Button(
        online_tab,
        text="Find online MIDI ID",
        command=lambda: find_online_midi_id(app),
    ).grid(row=1, column=0, sticky="w", pady=(7, 0))

    ttk.Label(
        online_tab,
        textvariable=app.online_status_var,
        style="Hint.TLabel",
        wraplength=610,
        justify="left",
    ).grid(row=2, column=0, sticky="w", pady=(6, 7))

    app.online_tree = _build_result_tree(online_tab)
    app.online_tree.grid(row=3, column=0, sticky="nsew")
    app.online_tree.bind("<<TreeviewSelect>>", lambda _event: _online_selected(app))

    online_actions = ttk.Frame(online_tab)
    online_actions.grid(row=4, column=0, sticky="ew", pady=(8, 0))
    ttk.Button(online_actions, text="Bookmark", command=lambda: bookmark_selected(app)).pack(side="left")
    ttk.Button(online_actions, text="Save to Local", command=lambda: save_selected_local(app)).pack(
        side="left", padx=(8, 0)
    )

    bookmarks_tab = ttk.Frame(app.song_source_notebook, padding=(8, 10, 8, 8))
    bookmarks_tab.columnconfigure(0, weight=1)
    bookmarks_tab.rowconfigure(1, weight=1)
    app.song_source_notebook.add(bookmarks_tab, text="Bookmarks")
    ttk.Label(
        bookmarks_tab,
        text="Bookmarks save only the Online Sequencer link. Use Save to Local for offline playback.",
        style="Hint.TLabel",
        wraplength=610,
        justify="left",
    ).grid(row=0, column=0, sticky="w", pady=(0, 7))

    app.bookmark_tree = _build_result_tree(bookmarks_tab)
    app.bookmark_tree.grid(row=1, column=0, sticky="nsew")
    app.bookmark_tree.bind("<<TreeviewSelect>>", lambda _event: _bookmark_selected(app))

    bookmark_actions = ttk.Frame(bookmarks_tab)
    bookmark_actions.grid(row=2, column=0, sticky="ew", pady=(8, 0))
    ttk.Button(bookmark_actions, text="Remove bookmark", command=lambda: remove_bookmark(app)).pack(side="left")
    ttk.Button(bookmark_actions, text="Save to Local", command=lambda: save_selected_local(app)).pack(
        side="left", padx=(8, 0)
    )

    app.song_source_notebook.bind("<<NotebookTabChanged>>", lambda _event: _source_tab_changed(app))
    _schedule_source_notebook_resize(app)


def _build_result_tree(parent: Any) -> Any:
    tree = ttk.Treeview(
        parent,
        columns=("fit", "changes", "notes"),
        show="tree headings",
        height=6,
        selectmode="browse",
    )
    tree.heading("#0", text="Song")
    tree.heading("fit", text="BPSR fit")
    tree.heading("changes", text="Changes")
    tree.heading("notes", text="Playable")
    tree.column("#0", width=285, minwidth=160, stretch=True)
    tree.column("fit", width=82, minwidth=70, stretch=False, anchor="center")
    tree.column("changes", width=145, minwidth=120, stretch=False, anchor="center")
    tree.column("notes", width=72, minwidth=60, stretch=False, anchor="e")
    return tree


def _schedule_source_notebook_resize(app: Any) -> None:
    try:
        app.after_idle(lambda: _resize_source_notebook(app))
    except Exception:
        pass


def _resize_source_notebook(app: Any) -> None:
    """Fit the notebook to the selected tab instead of its largest tab."""
    try:
        selected = app.song_source_notebook.select()
        tab = app.nametowidget(selected)
        height = max(1, int(tab.winfo_reqheight()))
        app.song_source_notebook.configure(height=height)
    except Exception:
        pass


def _source_tab_changed(app: Any) -> None:
    try:
        index = app.song_source_notebook.index(app.song_source_notebook.select())
    except Exception:
        return
    source = ("local", "online", "bookmarks")[index]
    app.song_source_var.set(source)
    _schedule_source_notebook_resize(app)

    if source == "local":
        # Refresh now because the folder watcher intentionally sleeps while an
        # online source is active.
        app._reload_midi_library(analyze=False, preferred_display=app.midi_display_var.get())
        selected = app.midi_display_var.get()
        path = app._midi_lookup.get(selected)
        app.file_var.set(str(path) if path is not None else "")
        if path is not None:
            app._schedule_analysis(20)
        else:
            _clear_current_song(app)
        return

    if source == "online":
        selected = _tree_selected_id(app.online_tree, "os:")
        app._online_selected_id = selected
        if selected is not None:
            _ensure_result_ready(app, selected)
        else:
            _clear_current_song(app)
            app.status_var.set("Paste an Online Sequencer link or numeric ID, then load the song.")
        return

    refresh_bookmarks(app)
    selected = _tree_selected_id(app.bookmark_tree, "bm:")
    if selected is None and app.bookmark_tree.get_children():
        first = app.bookmark_tree.get_children()[0]
        app.bookmark_tree.selection_set(first)
        app.bookmark_tree.focus(first)
        selected = _tree_selected_id(app.bookmark_tree, "bm:")
    app._bookmark_selected_id = selected
    if selected is not None:
        _ensure_result_ready(app, selected)
    else:
        _clear_current_song(app)
        app.status_var.set("No bookmarks yet. Bookmark a song from Online Sequencer first.")


def _clear_current_song(app: Any) -> None:
    app.file_var.set("")
    app.current_plan = None
    app.current_suitability = None
    try:
        app.start_button.configure(state="disabled")
    except Exception:
        pass


def search(app: Any) -> None:
    query = app.online_query_var.get().strip()
    if not query:
        app.online_status_var.set("Paste an Online Sequencer song link or numeric sequence ID first.")
        return

    app._online_search_generation += 1
    generation = app._online_search_generation
    app._online_results.clear()
    for item in app.online_tree.get_children():
        app.online_tree.delete(item)
    app.online_status_var.set("Loading Online Sequencer song…")
    _clear_current_song(app)

    def work() -> None:
        try:
            results = osq.search_sequences(query)
        except Exception as exc:  # noqa: BLE001
            _dispatch(app, lambda exc=exc: _search_failed(app, generation, exc))
            return
        _dispatch(app, lambda results=results: _populate_search(app, generation, results))

    _worker(app, work)


def find_online_midi_id(app: Any) -> None:
    """Open the public sequence list only after the user explicitly asks."""
    try:
        opened = bool(webbrowser.open(osq.BROWSE_URL, new=2, autoraise=True))
        if not opened and os.name == "nt":
            os.startfile(osq.BROWSE_URL)  # type: ignore[attr-defined]
            opened = True
    except (OSError, webbrowser.Error):
        opened = False

    if opened:
        app.online_status_var.set(
            "Online Sequencer opened. Choose a song, copy its link or numeric ID, then return here."
        )
        app.status_var.set("Find the song ID online, then use Load link / ID in BPSR MIDI Lite.")
    else:
        app.online_status_var.set("Could not open Online Sequencer in your web browser.")


def _search_failed(app: Any, generation: int, error: Exception) -> None:
    if generation != app._online_search_generation:
        return
    app.online_status_var.set(str(error))
    app.status_var.set("Online song was not loaded. Local songs still work normally.")


def _result_title(result: osq.SearchResult) -> str:
    if result.author:
        return f"{result.title} — {result.author}"
    return result.title


def _populate_search(app: Any, generation: int, results: list[osq.SearchResult]) -> None:
    if generation != app._online_search_generation:
        return
    app._online_results = {result.sequence_id: result for result in results}
    app.online_status_var.set(
        f"Loaded {len(results)} song(s). BPSR fit is checked automatically."
    )

    for index, result in enumerate(results):
        known_too_large = result.note_count is not None and result.note_count > osq.MAX_SEQUENCE_NOTES
        fit = "Too large" if known_too_large else ("Checking…" if index < AUTO_ANALYZE_RESULTS else "Select to check")
        changes = "—"
        notes = f"{result.note_count:,}" if result.note_count is not None else "—"
        app.online_tree.insert("", "end", iid=f"os:{result.sequence_id}", text=_result_title(result), values=(fit, changes, notes))
        if index < AUTO_ANALYZE_RESULTS and not known_too_large:
            _fetch_result(app, result)

    children = app.online_tree.get_children()
    if children:
        first = children[0]
        app.online_tree.selection_set(first)
        app.online_tree.focus(first)
        app._online_selected_id = _tree_selected_id(app.online_tree, "os:")
        if app.song_source_var.get() == "online" and app._online_selected_id is not None:
            _ensure_result_ready(app, app._online_selected_id)


def _tree_selected_id(tree: Any, prefix: str) -> int | None:
    selection = tree.selection()
    if not selection:
        return None
    iid = str(selection[0])
    if not iid.startswith(prefix):
        return None
    try:
        return int(iid[len(prefix) :])
    except ValueError:
        return None


def _online_selected(app: Any) -> None:
    sequence_id = _tree_selected_id(app.online_tree, "os:")
    app._online_selected_id = sequence_id
    if sequence_id is not None and app.song_source_var.get() == "online":
        _ensure_result_ready(app, sequence_id)


def _bookmark_selected(app: Any) -> None:
    sequence_id = _tree_selected_id(app.bookmark_tree, "bm:")
    app._bookmark_selected_id = sequence_id
    if sequence_id is not None and app.song_source_var.get() == "bookmarks":
        _ensure_result_ready(app, sequence_id)


def _result_for(app: Any, sequence_id: int) -> osq.SearchResult:
    result = app._online_results.get(sequence_id) or app._online_bookmarks.get(sequence_id)
    if result is not None:
        return result
    cached = app._online_cached.get(sequence_id)
    if cached is not None:
        return osq.SearchResult(cached.sequence_id, cached.title, cached.author, cached.note_count)
    return osq.SearchResult(sequence_id, f"Sequence #{sequence_id}")


def _ensure_result_ready(app: Any, sequence_id: int) -> None:
    cached = app._online_cached.get(sequence_id)
    if cached is not None and cached.path.exists():
        _activate_cached_if_selected(app, cached)
        if sequence_id not in app._online_fit:
            _analyze_cached(app, cached)
        return

    result = _result_for(app, sequence_id)
    if result.note_count is not None and result.note_count > osq.MAX_SEQUENCE_NOTES:
        _set_row_status(app, sequence_id, "Too large", "Not suitable", f"{result.note_count:,}")
        _clear_current_song(app)
        return
    _fetch_result(app, result)
    app.status_var.set("Loading the selected Online Sequencer song into temporary cache…")


def _fetch_result(app: Any, result: osq.SearchResult) -> None:
    sequence_id = result.sequence_id
    if sequence_id in app._online_cached:
        _analyze_cached(app, app._online_cached[sequence_id])
        return
    if sequence_id in app._online_fetching:
        return
    app._online_fetching.add(sequence_id)

    def work() -> None:
        try:
            cached = osq.fetch_sequence_to_cache(
                sequence_id,
                title=result.title,
                author=result.author,
            )
        except osq.SequenceTooLargeError as exc:
            _dispatch(app, lambda exc=exc: _fetch_too_large(app, sequence_id, exc.note_count))
            return
        except Exception as exc:  # noqa: BLE001
            _dispatch(app, lambda exc=exc: _fetch_failed(app, sequence_id, exc))
            return
        _dispatch(app, lambda cached=cached: _fetch_finished(app, cached))

    _worker(app, work)


def _fetch_too_large(app: Any, sequence_id: int, note_count: int) -> None:
    app._online_fetching.discard(sequence_id)
    _set_row_status(app, sequence_id, "Too large", "Not suitable", f"{note_count:,}")
    if _selected_sequence_id(app) == sequence_id:
        _clear_current_song(app)
        app.status_var.set(f"Sequence #{sequence_id} has {note_count:,} notes and is too large for safe BPSR analysis.")


def _fetch_failed(app: Any, sequence_id: int, error: Exception) -> None:
    app._online_fetching.discard(sequence_id)
    _set_row_status(app, sequence_id, "Unavailable", "—", "—")
    if _selected_sequence_id(app) == sequence_id:
        _clear_current_song(app)
        app.status_var.set(str(error))


def _fetch_finished(app: Any, cached: osq.CachedSequence) -> None:
    sequence_id = cached.sequence_id
    app._online_fetching.discard(sequence_id)
    app._online_cached[sequence_id] = cached
    result = _result_for(app, sequence_id)
    bookmark_was_renamed = False
    if result.title.startswith("Sequence #") and cached.title != result.title:
        replacement = osq.SearchResult(sequence_id, cached.title, cached.author, cached.note_count)
        if sequence_id in app._online_results:
            app._online_results[sequence_id] = replacement
        if sequence_id in app._online_bookmarks:
            app._online_bookmarks[sequence_id] = replacement
            bookmark_was_renamed = True
        _update_row_title(app, sequence_id, replacement)
    if bookmark_was_renamed:
        app._save_config()
    _analyze_cached(app, cached)
    _activate_cached_if_selected(app, cached)

    if sequence_id in app._online_pending_saves:
        app._online_pending_saves.discard(sequence_id)
        _save_cached_now(app, cached)


def _analyze_cached(app: Any, cached: osq.CachedSequence) -> None:
    # Read Tk-backed options on the UI thread before starting the worker.
    context_generation = app._online_context_generation
    options = app._plan_options()

    def work() -> None:
        try:
            plan = app._modern_module.build_plan(cached.path, options)
            suitability = app._modern_module.evaluate_song_suitability(plan)
            if plan.page_switches:
                fit = "Blocked"
            else:
                fit = {"good": "Ready", "busy": "Busy", "complex": "Crowded"}.get(
                    getattr(suitability, "code", "good"), "Ready"
                )
            changes = f"R {plan.remapped_notes:,} · S {plan.skipped_notes:,} · F {plan.filtered_notes:,}"
            notes = f"{plan.note_count:,}"
        except Exception as exc:  # noqa: BLE001
            _dispatch(app, lambda exc=exc: _analysis_failed(app, cached.sequence_id, context_generation, exc))
            return
        _dispatch(
            app,
            lambda: _analysis_finished(app, cached.sequence_id, context_generation, fit, changes, notes),
        )

    _worker(app, work)


def _analysis_finished(
    app: Any,
    sequence_id: int,
    context_generation: int,
    fit: str,
    changes: str,
    notes: str,
) -> None:
    if context_generation != app._online_context_generation:
        return
    app._online_fit[sequence_id] = (fit, changes, notes)
    _set_row_status(app, sequence_id, fit, changes, notes)


def _analysis_failed(app: Any, sequence_id: int, context_generation: int, error: Exception) -> None:
    if context_generation != app._online_context_generation:
        return
    app._online_fit[sequence_id] = ("Unavailable", "—", "—")
    _set_row_status(app, sequence_id, "Unavailable", "—", "—")
    if _selected_sequence_id(app) == sequence_id:
        app.status_var.set(f"Could not analyze this online song: {error}")


def _set_row_status(app: Any, sequence_id: int, fit: str, changes: str, notes: str) -> None:
    for tree, prefix in ((getattr(app, "online_tree", None), "os:"), (getattr(app, "bookmark_tree", None), "bm:")):
        if tree is None:
            continue
        iid = f"{prefix}{sequence_id}"
        if tree.exists(iid):
            tree.item(iid, values=(fit, changes, notes))


def _update_row_title(app: Any, sequence_id: int, result: osq.SearchResult) -> None:
    for tree, prefix in ((getattr(app, "online_tree", None), "os:"), (getattr(app, "bookmark_tree", None), "bm:")):
        if tree is None:
            continue
        iid = f"{prefix}{sequence_id}"
        if tree.exists(iid):
            tree.item(iid, text=_result_title(result))


def _selected_sequence_id(app: Any) -> int | None:
    source = app.song_source_var.get()
    if source == "online":
        return app._online_selected_id
    if source == "bookmarks":
        return app._bookmark_selected_id
    return None


def _activate_cached_if_selected(app: Any, cached: osq.CachedSequence) -> None:
    if _selected_sequence_id(app) != cached.sequence_id:
        return
    if app.song_source_var.get() not in {"online", "bookmarks"}:
        return
    app.file_var.set(str(cached.path))
    app.status_var.set("Online song is ready from temporary cache. Press Play in BPSR, or Save to Local for offline use.")
    app._schedule_analysis(20)


def schedule_reanalysis(app: Any, delay_ms: int = 350) -> None:
    if not hasattr(app, "_online_cached"):
        return
    if app._online_reanalysis_job is not None:
        try:
            app.after_cancel(app._online_reanalysis_job)
        except Exception:
            pass
    try:
        app._online_reanalysis_job = app.after(delay_ms, lambda: _reanalyze_cached(app))
    except Exception:
        app._online_reanalysis_job = None


def _reanalyze_cached(app: Any) -> None:
    app._online_reanalysis_job = None
    app._online_context_generation += 1
    app._online_fit.clear()
    for cached in list(app._online_cached.values())[:24]:
        _set_row_status(app, cached.sequence_id, "Checking…", "—", f"{cached.note_count:,}")
        _analyze_cached(app, cached)
    selected_id = _selected_sequence_id(app)
    if selected_id is not None and selected_id in app._online_cached:
        _activate_cached_if_selected(app, app._online_cached[selected_id])


def bookmark_selected(app: Any) -> None:
    sequence_id = _tree_selected_id(app.online_tree, "os:")
    if sequence_id is None:
        app.status_var.set("Choose an Online Sequencer result first.")
        return
    result = _result_for(app, sequence_id)
    app._online_bookmarks[sequence_id] = result
    refresh_bookmarks(app)
    app._save_config()
    app.status_var.set(f"Bookmarked {result.title}. Bookmarking stores the link, not a permanent MIDI file.")


def remove_bookmark(app: Any) -> None:
    sequence_id = _tree_selected_id(app.bookmark_tree, "bm:")
    if sequence_id is None:
        return
    result = app._online_bookmarks.pop(sequence_id, None)
    refresh_bookmarks(app)
    app._save_config()
    if result is not None:
        app.status_var.set(f"Removed bookmark: {result.title}")
    if app.song_source_var.get() == "bookmarks":
        _source_tab_changed(app)


def refresh_bookmarks(app: Any) -> None:
    if not hasattr(app, "bookmark_tree"):
        return
    selected = app._bookmark_selected_id
    for item in app.bookmark_tree.get_children():
        app.bookmark_tree.delete(item)
    for result in app._online_bookmarks.values():
        fit, changes, notes = app._online_fit.get(
            result.sequence_id,
            ("Not checked", "—", f"{result.note_count:,}" if result.note_count is not None else "—"),
        )
        app.bookmark_tree.insert(
            "",
            "end",
            iid=f"bm:{result.sequence_id}",
            text=_result_title(result),
            values=(fit, changes, notes),
        )
    if selected is not None and app.bookmark_tree.exists(f"bm:{selected}"):
        app.bookmark_tree.selection_set(f"bm:{selected}")
        app.bookmark_tree.focus(f"bm:{selected}")

    if app.song_source_var.get() == "bookmarks":
        for result in list(app._online_bookmarks.values())[:AUTO_ANALYZE_RESULTS]:
            if result.sequence_id not in app._online_cached:
                _fetch_result(app, result)


def _current_action_sequence_id(app: Any) -> int | None:
    source = app.song_source_var.get()
    if source == "bookmarks":
        return _tree_selected_id(app.bookmark_tree, "bm:")
    return _tree_selected_id(app.online_tree, "os:")


def save_selected_local(app: Any) -> None:
    sequence_id = _current_action_sequence_id(app)
    if sequence_id is None:
        app.status_var.set("Choose an Online Sequencer song first.")
        return
    cached = app._online_cached.get(sequence_id)
    if cached is not None and cached.path.exists():
        _save_cached_now(app, cached)
        return
    app._online_pending_saves.add(sequence_id)
    _fetch_result(app, _result_for(app, sequence_id))
    app.status_var.set("Preparing the song, then it will be saved to your Local MIDI folder…")


def _save_cached_now(app: Any, cached: osq.CachedSequence) -> None:
    try:
        target = osq.save_cached_sequence(cached, Path(app.midi_folder_var.get()))
    except OSError as exc:
        app.status_var.set(f"Could not save the local MIDI: {exc}")
        return
    app.status_var.set(f"Saved to Local: {target.name}")


def load_bookmarks_from_config(app: Any, data: dict[str, Any]) -> None:
    app._online_bookmarks.clear()
    raw = data.get("online_bookmarks", [])
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                sequence_id = int(item.get("id", 0))
            except (TypeError, ValueError):
                continue
            if sequence_id <= 0:
                continue
            title = str(item.get("title") or f"Sequence #{sequence_id}")[:160]
            author = str(item.get("author") or "")[:80]
            note_count_raw = item.get("note_count")
            try:
                note_count = int(note_count_raw) if note_count_raw is not None else None
            except (TypeError, ValueError):
                note_count = None
            app._online_bookmarks[sequence_id] = osq.SearchResult(sequence_id, title, author, note_count)
    refresh_bookmarks(app)


def save_bookmarks_to_config(app: Any, data: dict[str, Any]) -> None:
    data["online_bookmarks"] = [
        {
            "id": result.sequence_id,
            "title": result.title,
            "author": result.author,
            "note_count": result.note_count,
        }
        for result in app._online_bookmarks.values()
    ]


def empty_selection_message(app: Any) -> tuple[str, str]:
    source = app.song_source_var.get()
    if source == "online":
        return "Choose an online song", "Paste an Online Sequencer link or numeric ID. It is cached temporarily, not saved permanently."
    if source == "bookmarks":
        return "Choose a bookmark", "Select a bookmarked Online Sequencer song, or bookmark one from the Online Sequencer tab first."
    return "Add a MIDI song to begin", "Open the song folder and copy in a .mid or .midi file."


def analysis_suffix(app: Any) -> str:
    if app.song_source_var.get() in {"online", "bookmarks"}:
        return "\nTemporary online cache — use Save to Local if you want to keep this MIDI for offline use."
    return ""
