from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import ttk
from typing import Any

import online_ui
import studio_youtube as youtube


def attach(app: Any) -> None:
    """Add Studio-only YouTube search to the already-built Lite/Online UI."""
    app.youtube_query_var = tk.StringVar(master=app)
    app.youtube_status_var = tk.StringVar(
        master=app,
        value="Search YouTube. The top 3 results appear here; click one to convert it automatically.",
    )
    app._youtube_results: dict[str, youtube.YouTubeResult] = {}
    app._youtube_cached_midi: dict[str, Path] = {}
    app._youtube_selected_id: str | None = None
    app._youtube_converting = False

    _rename_studio_shell(app)
    _build_youtube_tab(app)
    app.song_source_notebook.bind(
        "<<NotebookTabChanged>>",
        lambda _event: _source_tab_changed(app),
    )
    youtube.cleanup_cache()


def _rename_studio_shell(app: Any) -> None:
    try:
        app.title("BPSR MIDI Studio")
    except tk.TclError:
        pass
    pending = list(app.winfo_children())
    while pending:
        widget = pending.pop(0)
        try:
            pending.extend(widget.winfo_children())
            if widget.winfo_class() == "TLabel":
                text = str(widget.cget("text"))
                if text == "BPSR MIDI Lite":
                    widget.configure(text="BPSR MIDI Studio")
                elif text.startswith("Local keeps permanent MIDI files."):
                    widget.configure(
                        text=(
                            "Local keeps permanent MIDI files. Online Sequencer uses temporary cache. "
                            "YouTube searches the top 3 results and converts the one you click into temporary MIDI. "
                            "Save MIDI to Local keeps a permanent offline copy."
                        )
                    )
        except tk.TclError:
            continue


def _build_youtube_tab(app: Any) -> None:
    tab = ttk.Frame(app.song_source_notebook, padding=(8, 10, 8, 8))
    tab.columnconfigure(0, weight=1)
    tab.rowconfigure(3, weight=1)
    app.song_source_notebook.add(tab, text="YouTube")
    app.youtube_tab = tab

    search_row = ttk.Frame(tab)
    search_row.grid(row=0, column=0, sticky="ew")
    search_row.columnconfigure(0, weight=1)

    app.youtube_search_entry = ttk.Entry(
        search_row,
        textvariable=app.youtube_query_var,
    )
    app.youtube_search_entry.grid(row=0, column=0, sticky="ew")
    app.youtube_search_entry.bind("<Return>", lambda _event: search(app))
    app.youtube_search_button = ttk.Button(
        search_row,
        text="Search",
        command=lambda: search(app),
    )
    app.youtube_search_button.grid(row=0, column=1, padx=(8, 0))

    ttk.Label(
        tab,
        textvariable=app.youtube_status_var,
        style="Hint.TLabel",
        wraplength=610,
        justify="left",
    ).grid(row=1, column=0, sticky="w", pady=(6, 5))

    app.youtube_progress = ttk.Progressbar(
        tab,
        mode="determinate",
        maximum=100,
        value=0,
    )
    app.youtube_progress.grid(row=2, column=0, sticky="ew", pady=(0, 7))

    tree = ttk.Treeview(
        tab,
        columns=("channel", "duration"),
        show="tree headings",
        height=3,
        selectmode="browse",
    )
    tree.heading("#0", text="Song")
    tree.heading("channel", text="Channel")
    tree.heading("duration", text="Length")
    tree.column("#0", width=345, minwidth=180, stretch=True)
    tree.column("channel", width=150, minwidth=90, stretch=False)
    tree.column("duration", width=62, minwidth=55, stretch=False, anchor="center")
    tree.grid(row=3, column=0, sticky="nsew")
    tree.bind("<<TreeviewSelect>>", lambda _event: _result_selected(app))
    app.youtube_tree = tree

    actions = ttk.Frame(tab)
    actions.grid(row=4, column=0, sticky="ew", pady=(8, 0))
    app.youtube_save_button = ttk.Button(
        actions,
        text="Save MIDI to Local",
        command=lambda: save_selected_midi(app),
    )
    app.youtube_save_button.pack(side="left")
    ttk.Button(
        actions,
        text="Open on YouTube",
        command=lambda: open_selected(app),
    ).pack(side="left", padx=(8, 0))
    ttk.Label(
        actions,
        text="No sign-in. Restricted videos are simply skipped.",
        style="Hint.TLabel",
    ).pack(side="left", padx=(12, 0))

    app.youtube_instrumental_tip = ttk.Label(
        tab,
        text=(
            "Tip: choose instrumental, piano, guitar, bass, karaoke, or melody-cover uploads when possible. "
            "They usually produce much cleaner MIDI than a full vocal/full-band mix."
        ),
        style="Hint.TLabel",
        wraplength=610,
        justify="left",
    )
    app.youtube_instrumental_tip.grid(row=5, column=0, sticky="w", pady=(8, 0))


def _dispatch(app: Any, callback: Any) -> None:
    online_ui._dispatch(app, callback)


def _worker(app: Any, action: Any) -> None:
    threading.Thread(
        target=action,
        daemon=True,
        name="bpsr-midi-studio-youtube",
    ).start()


def _set_youtube_status(app: Any, message: str) -> None:
    try:
        app.youtube_status_var.set(message)
    except tk.TclError:
        pass


def _progress_start(app: Any) -> None:
    try:
        app.youtube_progress.stop()
        app.youtube_progress.configure(mode="indeterminate", maximum=100, value=0)
        app.youtube_progress.start(12)
    except tk.TclError:
        pass


def _progress_done(app: Any) -> None:
    try:
        app.youtube_progress.stop()
        app.youtube_progress.configure(mode="determinate", maximum=100, value=100)
    except tk.TclError:
        pass


def _progress_reset(app: Any) -> None:
    try:
        app.youtube_progress.stop()
        app.youtube_progress.configure(mode="determinate", maximum=100, value=0)
    except tk.TclError:
        pass


def _progress_callback(app: Any) -> Any:
    def report(message: str) -> None:
        _dispatch(app, lambda message=message: _set_youtube_status(app, message))
    return report


def _clear_current_song(app: Any) -> None:
    online_ui._clear_current_song(app)


def search(app: Any) -> None:
    query = app.youtube_query_var.get().strip()
    if not query:
        app.youtube_status_var.set("Type a song, artist, or video title first.")
        return
    if app._youtube_converting:
        app.youtube_status_var.set("Finish the current conversion before starting another search.")
        return

    for item in app.youtube_tree.get_children():
        app.youtube_tree.delete(item)
    app._youtube_results.clear()
    app._youtube_selected_id = None
    _clear_current_song(app)
    app.youtube_search_button.configure(state="disabled")
    app.youtube_status_var.set("Preparing YouTube search…")
    _progress_start(app)

    def work() -> None:
        try:
            results = youtube.search_youtube(
                query,
                limit=youtube.TOP_RESULTS,
                progress=_progress_callback(app),
            )
        except youtube.StudioError as exc:
            _dispatch(app, lambda exc=exc: _search_failed(app, exc))
            return
        _dispatch(app, lambda results=results: _search_finished(app, results))

    _worker(app, work)


def _search_failed(app: Any, error: Exception) -> None:
    app.youtube_search_button.configure(state="normal")
    _progress_reset(app)
    app.youtube_status_var.set(str(error))
    app.status_var.set("YouTube search unavailable. Local MIDI still works normally.")


def _search_finished(app: Any, results: list[youtube.YouTubeResult]) -> None:
    app.youtube_search_button.configure(state="normal")
    _progress_reset(app)
    app._youtube_results = {result.video_id: result for result in results}
    for result in results:
        app.youtube_tree.insert(
            "",
            "end",
            iid=f"yt:{result.video_id}",
            text=result.title,
            values=(result.channel or "—", youtube.duration_label(result.duration_seconds)),
        )
    app.youtube_status_var.set(
        f"Found {len(results)} result(s). Click a song to automatically get audio, build a cleaner core MIDI, and run BPSR Song Check."
    )
    app.status_var.set("Choose one of the YouTube results to convert.")


def _selected_video_id(app: Any) -> str | None:
    selection = app.youtube_tree.selection()
    if not selection:
        return None
    iid = str(selection[0])
    if not iid.startswith("yt:"):
        return None
    return iid[3:]


def _result_selected(app: Any) -> None:
    if app.song_source_var.get() != "youtube":
        return
    video_id = _selected_video_id(app)
    if not video_id:
        return
    result = app._youtube_results.get(video_id)
    if result is None:
        return
    app._youtube_selected_id = video_id

    cached = app._youtube_cached_midi.get(video_id)
    if cached is not None and cached.exists():
        _progress_done(app)
        _activate_midi(app, result, cached)
        return
    if app._youtube_converting:
        app.youtube_status_var.set("A song is already converting. The moving bar means Studio is still working.")
        return
    _start_conversion(app, result)


def _start_conversion(app: Any, result: youtube.YouTubeResult) -> None:
    app._youtube_converting = True
    app.youtube_search_button.configure(state="disabled")
    _clear_current_song(app)
    app.youtube_status_var.set(f"Preparing “{result.title}”…")
    app.status_var.set("Converting YouTube audio to a cleaner core MIDI. The progress bar moves while Studio is working.")
    _progress_start(app)

    def work() -> None:
        try:
            midi_path = youtube.convert_result_to_midi(
                result,
                progress=_progress_callback(app),
            )
        except youtube.StudioError as exc:
            _dispatch(app, lambda exc=exc, result=result: _conversion_failed(app, result, exc))
            return
        _dispatch(app, lambda: _conversion_finished(app, result, midi_path))

    _worker(app, work)


def _conversion_failed(app: Any, result: youtube.YouTubeResult, error: Exception) -> None:
    app._youtube_converting = False
    app.youtube_search_button.configure(state="normal")
    _progress_reset(app)
    app.youtube_status_var.set(str(error))
    app.status_var.set(f"Could not convert {result.title}. Choose another YouTube result.")


def _conversion_finished(app: Any, result: youtube.YouTubeResult, midi_path: Path) -> None:
    app._youtube_converting = False
    app.youtube_search_button.configure(state="normal")
    app._youtube_cached_midi[result.video_id] = midi_path
    _progress_done(app)
    if (
        app.song_source_var.get() == "youtube"
        and app._youtube_selected_id == result.video_id
        and _selected_video_id(app) == result.video_id
    ):
        _activate_midi(app, result, midi_path)
    else:
        app.youtube_status_var.set(f"{result.title} is converted and cached. Click it again when ready.")


def _activate_midi(app: Any, result: youtube.YouTubeResult, midi_path: Path) -> None:
    if not midi_path.exists():
        return
    app.file_var.set(str(midi_path))
    app.youtube_status_var.set(
        f"MIDI ready: {result.title}. BPSR Song Check is running; then use Play in BPSR."
    )
    app.status_var.set("YouTube conversion is ready. Checking how it fits your BPSR instrument/category…")
    app._schedule_analysis(20)


def _source_tab_changed(app: Any) -> None:
    try:
        selected = app.song_source_notebook.select()
        tab_text = str(app.song_source_notebook.tab(selected, "text"))
    except tk.TclError:
        return

    if tab_text != "YouTube":
        online_ui._source_tab_changed(app)
        return

    app.song_source_var.set("youtube")
    video_id = _selected_video_id(app)
    app._youtube_selected_id = video_id
    if video_id is None:
        _clear_current_song(app)
        app.status_var.set("Search YouTube, then click one of the top results.")
        return
    result = app._youtube_results.get(video_id)
    cached = app._youtube_cached_midi.get(video_id)
    if result is not None and cached is not None and cached.exists():
        _progress_done(app)
        _activate_midi(app, result, cached)
    else:
        _clear_current_song(app)


def save_selected_midi(app: Any) -> None:
    video_id = _selected_video_id(app)
    if not video_id:
        app.status_var.set("Choose and convert a YouTube result first.")
        return
    result = app._youtube_results.get(video_id)
    midi_path = app._youtube_cached_midi.get(video_id)
    if result is None or midi_path is None or not midi_path.exists():
        app.status_var.set("Wait for this YouTube song to finish converting first.")
        return
    try:
        target = youtube.save_midi_to_local(
            midi_path,
            result.title,
            result.video_id,
            Path(app.midi_folder_var.get()),
        )
    except OSError as exc:
        app.status_var.set(f"Could not save the MIDI: {exc}")
        return
    app.status_var.set(f"Saved to Local: {target.name}")


def open_selected(app: Any) -> None:
    video_id = _selected_video_id(app)
    if video_id and video_id in app._youtube_results:
        url = app._youtube_results[video_id].url
    else:
        query = app.youtube_query_var.get().strip()
        if query:
            from urllib.parse import quote_plus
            url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        else:
            url = "https://www.youtube.com/"
    try:
        opened = bool(webbrowser.open(url, new=2, autoraise=True))
    except webbrowser.Error:
        opened = False
    app.status_var.set(
        "Opened YouTube in your browser." if opened else "Could not open your web browser."
    )


def empty_selection_message() -> tuple[str, str]:
    return (
        "Choose a YouTube song",
        "Search YouTube and click one of the top 3 results. Studio converts it to temporary MIDI automatically.",
    )


def analysis_suffix() -> str:
    return (
        "\nTemporary YouTube core transcription — use Save MIDI to Local if you want to keep this conversion."
    )
