from __future__ import annotations

import queue
import threading
import tkinter as tk
import urllib.parse
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from online_sequencer import (
    SEARCH_URL,
    SITE_ROOT,
    OnlineSequencerError,
    SearchResult,
    extract_sequence_id,
    import_sequence,
    search_sequences,
)


class OnlineSequencerDialog(tk.Toplevel):
    """Small, rate-limited search/import window for Online Sequencer."""

    def __init__(
        self,
        parent: tk.Misc,
        midi_folder: str | Path,
        on_imported: Callable[[Path], None],
    ) -> None:
        super().__init__(parent)
        self.title("Find songs — Online Sequencer")
        self.geometry("760x560")
        self.minsize(650, 480)
        self.transient(parent)
        self._midi_folder = Path(midi_folder)
        self._on_imported = on_imported
        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._results_by_item: dict[str, SearchResult] = {}
        self._busy = False

        self.query_var = tk.StringVar()
        self.direct_var = tk.StringVar()
        self.status_var = tk.StringVar(
            value="Search by song name, or paste a sequence URL/ID below."
        )

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(80, self._drain_queue)
        self.query_entry.focus_set()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="Find songs on Online Sequencer",
            style="Title.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                "Search public sequences, preview them in your browser, then import one "
                "as a MIDI into this app's MIDI folder."
            ),
            wraplength=700,
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(2, 12))

        search_row = ttk.Frame(outer)
        search_row.pack(fill="x")
        search_row.columnconfigure(0, weight=1)
        self.query_entry = ttk.Entry(search_row, textvariable=self.query_var)
        self.query_entry.grid(row=0, column=0, sticky="ew")
        self.query_entry.bind("<Return>", lambda _event: self._search())
        self.search_button = ttk.Button(search_row, text="Search", command=self._search)
        self.search_button.grid(row=0, column=1, padx=(8, 0))
        self.browser_search_button = ttk.Button(
            search_row,
            text="Open search in browser",
            command=self._open_search_in_browser,
        )
        self.browser_search_button.grid(row=0, column=2, padx=(8, 0))

        result_frame = ttk.Frame(outer)
        result_frame.pack(fill="both", expand=True, pady=(10, 8))
        result_frame.rowconfigure(0, weight=1)
        result_frame.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            result_frame,
            columns=("title", "id"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("title", text="Sequence title")
        self.tree.heading("id", text="ID")
        self.tree.column("title", width=560, anchor="w")
        self.tree.column("id", width=90, anchor="center", stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<Double-1>", lambda _event: self._open_selected())
        scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        result_buttons = ttk.Frame(outer)
        result_buttons.pack(fill="x")
        self.open_button = ttk.Button(
            result_buttons,
            text="Preview selected",
            command=self._open_selected,
        )
        self.open_button.pack(side="left")
        self.import_button = ttk.Button(
            result_buttons,
            text="Download selected MIDI",
            command=self._import_selected,
        )
        self.import_button.pack(side="left", padx=(8, 0))

        ttk.Separator(outer).pack(fill="x", pady=12)

        direct = ttk.LabelFrame(outer, text="Already have a sequence link?", padding=10)
        direct.pack(fill="x")
        direct.columnconfigure(0, weight=1)
        direct_entry = ttk.Entry(direct, textvariable=self.direct_var)
        direct_entry.grid(row=0, column=0, sticky="ew")
        direct_entry.bind("<Return>", lambda _event: self._import_direct())
        self.direct_button = ttk.Button(
            direct,
            text="Download URL / ID",
            command=self._import_direct,
        )
        self.direct_button.grid(row=0, column=1, padx=(8, 0))
        ttk.Label(
            direct,
            text="Example: https://onlinesequencer.net/1234567 or 1234567",
            style="Hint.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        ttk.Label(
            outer,
            textvariable=self.status_var,
            wraplength=710,
        ).pack(anchor="w", pady=(10, 0))
        ttk.Label(
            outer,
            text=(
                "Online Sequencer is a third-party service. Import one public sequence at a time, "
                "and respect its creator's rights and the site's rules. Search/import availability "
                "depends on the website."
            ),
            wraplength=710,
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(6, 0))

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for widget in (
            self.search_button,
            self.import_button,
            self.direct_button,
        ):
            widget.configure(state=state)

    def _search(self) -> None:
        if self._busy:
            return
        query = self.query_var.get().strip()
        if not query:
            self.status_var.set("Type a song name first.")
            return
        self._set_busy(True)
        self.status_var.set(f"Searching Online Sequencer for “{query}”…")

        def worker() -> None:
            try:
                results = search_sequences(query)
                self._queue.put(("search_ok", results))
            except Exception as exc:  # noqa: BLE001
                self._queue.put(("search_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _open_search_in_browser(self) -> None:
        query = self.query_var.get().strip()
        if query:
            webbrowser.open(SEARCH_URL.format(query=urllib.parse.quote_plus(query)))
        else:
            webbrowser.open(SITE_ROOT + "/sequences")

    def _selected_result(self) -> SearchResult | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._results_by_item.get(selection[0])

    def _open_selected(self) -> None:
        result = self._selected_result()
        if result is None:
            self.status_var.set("Select a search result first.")
            return
        webbrowser.open(result.url)

    def _import_selected(self) -> None:
        result = self._selected_result()
        if result is None:
            self.status_var.set("Select a search result first.")
            return
        self._start_import(result.sequence_id, result.title)

    def _import_direct(self) -> None:
        value = self.direct_var.get().strip()
        try:
            sequence_id = extract_sequence_id(value)
        except OnlineSequencerError as exc:
            self.status_var.set(str(exc))
            return
        self._start_import(sequence_id, None)

    def _start_import(self, sequence_id: int, title: str | None) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self.status_var.set(
            f"Downloading sequence #{sequence_id} and converting it to MIDI…"
        )

        def worker() -> None:
            try:
                path = import_sequence(
                    sequence_id,
                    self._midi_folder,
                    title=title,
                )
                self._queue.put(("import_ok", path))
            except Exception as exc:  # noqa: BLE001
                self._queue.put(("import_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _fill_results(self, results: list[SearchResult]) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._results_by_item.clear()
        for result in results:
            item = self.tree.insert(
                "",
                "end",
                values=(result.title, result.sequence_id),
            )
            self._results_by_item[item] = result
        if results:
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
            self.status_var.set(
                f"Found {len(results)} result(s). Double-click to preview, or download the selected MIDI."
            )
        else:
            self.status_var.set(
                "No results were found in the page returned by Online Sequencer. "
                "Try fewer words, use Open search in browser, or paste a sequence URL/ID."
            )

    def _drain_queue(self) -> None:
        if not self.winfo_exists():
            return
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                self._set_busy(False)
                if kind == "search_ok":
                    self._fill_results(payload)  # type: ignore[arg-type]
                elif kind == "search_error":
                    self.status_var.set(f"Search failed: {payload}")
                elif kind == "import_ok":
                    path = Path(payload)  # type: ignore[arg-type]
                    self.status_var.set(f"Saved: {path.name}")
                    self._on_imported(path)
                    messagebox.showinfo(
                        "BPSR MIDI Lite",
                        f"Downloaded into the MIDI library:\n\n{path.name}",
                        parent=self,
                    )
                elif kind == "import_error":
                    self.status_var.set(f"Download failed: {payload}")
        except queue.Empty:
            pass
        self.after(80, self._drain_queue)

    def _close(self) -> None:
        if self._busy and not messagebox.askyesno(
            "BPSR MIDI Lite",
            "A request is still running. Close this window anyway?",
            parent=self,
        ):
            return
        self.destroy()
