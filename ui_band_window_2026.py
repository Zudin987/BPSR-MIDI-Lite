from __future__ import annotations

import queue
import time
import tkinter as tk
from tkinter import ttk
from typing import Any

import band_arranger
import band_sync
import band_ui
import ui_full_overhaul_2026 as full_ui


# Studio beta.8 follow-up: Band Mode is a persistent playback mode, while the
# room controls are a secondary workspace. Keep those concepts separate: the
# checkbox enables Band behavior and automatically opens a dedicated Band Room
# window, exactly like Audio -> Band opens its own workspace window.


def _fit_window(app: Any, window: Any) -> None:
    try:
        sw = max(640, int(window.winfo_screenwidth()))
        sh = max(480, int(window.winfo_screenheight()))
        width = min(900, max(560, sw - 140))
        height = min(680, max(440, sh - 120))
        try:
            app.update_idletasks()
            x = int(app.winfo_rootx()) + max(24, (int(app.winfo_width()) - width) // 2)
            y = int(app.winfo_rooty()) + max(24, (int(app.winfo_height()) - height) // 2)
        except (tk.TclError, TypeError, ValueError):
            x = max(0, (sw - width) // 2)
            y = max(0, (sh - height) // 2)
        x = max(0, min(x, sw - width))
        y = max(0, min(y, sh - height))
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.minsize(min(560, width), min(420, height))
    except (tk.TclError, TypeError, ValueError):
        pass


def _window_visible(app: Any) -> bool:
    window = getattr(app, "_band_window", None)
    if window is None:
        return False
    try:
        return bool(window.winfo_viewable())
    except tk.TclError:
        return False


def _sync_scroll_region(app: Any) -> None:
    canvas = getattr(app, "_band_window_canvas", None)
    body = getattr(app, "_band_window_body", None)
    if canvas is None or body is None:
        return
    try:
        body.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))
    except tk.TclError:
        pass


def _reflow_window(app: Any) -> None:
    if not _window_visible(app):
        return
    try:
        full_ui._reflow_band_panel(app)
    except (AttributeError, tk.TclError):
        pass
    _sync_scroll_region(app)


def _schedule_reflow(app: Any) -> None:
    window = getattr(app, "_band_window", None)
    if window is None:
        return
    old = getattr(app, "_band_window_reflow_job", None)
    try:
        if old is not None:
            window.after_cancel(old)
    except tk.TclError:
        pass

    def run() -> None:
        app._band_window_reflow_job = None
        _reflow_window(app)

    try:
        app._band_window_reflow_job = window.after_idle(run)
    except tk.TclError:
        app._band_window_reflow_job = None


def _hide_band_window(app: Any) -> None:
    window = getattr(app, "_band_window", None)
    if window is None:
        return
    try:
        window.withdraw()
    except tk.TclError:
        pass


def _show_band_window(app: Any) -> None:
    enabled = getattr(app, "_band_enabled_var", None)
    try:
        if enabled is not None and not bool(enabled.get()):
            return
    except tk.TclError:
        return
    window = getattr(app, "_band_window", None)
    if window is None:
        return
    try:
        window.deiconify()
        window.lift()
    except tk.TclError:
        return
    _schedule_reflow(app)


def _set_band_frame_visible(app: Any, visible: bool) -> None:
    if visible:
        _show_band_window(app)
    else:
        _hide_band_window(app)


def _wheel_band_window(app: Any, event: Any):
    canvas = getattr(app, "_band_window_canvas", None)
    if canvas is None or not _window_visible(app):
        return None
    delta = int(getattr(event, "delta", 0) or 0)
    if delta:
        steps = -int(delta / 120) or (-1 if delta > 0 else 1)
    elif getattr(event, "num", None) == 4:
        steps = -1
    elif getattr(event, "num", None) == 5:
        steps = 1
    else:
        return None
    try:
        canvas.yview_scroll(steps, "units")
    except tk.TclError:
        return None
    return "break"


def _build_detached_band_panel(app: Any) -> None:
    setup = getattr(app, "_product_setup_frame", None)
    if setup is None:
        return

    app._band_enabled_var = tk.BooleanVar(master=app, value=False)
    current_part = str(app._instrument_code())
    app._band_role_var = tk.StringVar(
        master=app,
        value=band_arranger.part_label(
            current_part if current_part in {"keyboard", "guitar", "bass"} else "keyboard"
        ),
    )
    app._band_room_code_var = tk.StringVar(master=app, value="")
    app._band_name_var = tk.StringVar(master=app, value=band_ui._safe_username())
    app._band_room_status_var = tk.StringVar(master=app, value="Not connected")
    app._band_players_var = tk.StringVar(master=app, value="No players connected")
    app._band_sync_var = tk.StringVar(master=app, value="Clock: not synchronized")
    app._band_part_summary_var = tk.StringVar(master=app, value="Band part: off")
    app._band_player_id = band_sync.new_player_id()
    app._band_transport = None
    app._band_connected = False
    app._band_is_host = False
    app._band_ready = False
    app._band_clock_sample = None
    app._band_clock_synced_at = 0.0
    app._band_clock_sync_running = False
    app._band_roster = band_sync.BandRoster()
    app._band_event_queue = queue.Queue()
    app._band_hash_cache_key = None
    app._band_hash_cache_value = ""

    app._band_mode_check = ttk.Checkbutton(
        setup,
        text="Band Mode (Beta)",
        variable=app._band_enabled_var,
        command=lambda: band_ui._toggle_band_mode(app),
    )
    app._band_mode_check.grid(row=3, column=0, sticky="w", pady=(7, 0))
    ttk.Label(
        setup,
        text="Same MIDI → separate parts → synchronized room start",
        style="Hint.TLabel",
    ).grid(row=3, column=1, sticky="w", pady=(7, 0))

    window = tk.Toplevel(app)
    window.withdraw()
    window.title("Band Room")
    window.protocol("WM_DELETE_WINDOW", lambda: _hide_band_window(app))
    window.bind("<Escape>", lambda _event: (_hide_band_window(app), "break")[1])
    _fit_window(app, window)
    app._band_window = window
    app._band_window_reflow_job = None

    shell = ttk.Frame(window, padding=(10, 10, 4, 10))
    shell.grid(row=0, column=0, sticky="nsew")
    window.rowconfigure(0, weight=1)
    window.columnconfigure(0, weight=1)
    shell.rowconfigure(0, weight=1)
    shell.columnconfigure(0, weight=1)

    try:
        background = str(app._style.lookup("TFrame", "background") or "#202020")
    except (AttributeError, tk.TclError):
        background = "#202020"
    canvas = tk.Canvas(shell, highlightthickness=0, borderwidth=0, background=background)
    scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")

    body = ttk.Frame(canvas)
    body.columnconfigure(0, weight=1)
    body_id = canvas.create_window((0, 0), window=body, anchor="nw")
    app._band_window_canvas = canvas
    app._band_window_scrollbar = scrollbar
    app._band_window_body = body
    app._band_window_body_id = body_id

    def canvas_configured(event: Any) -> None:
        try:
            canvas.itemconfigure(body_id, width=max(1, int(event.width)))
        except (tk.TclError, TypeError, ValueError):
            pass
        _schedule_reflow(app)

    canvas.bind("<Configure>", canvas_configured, add="+")
    body.bind("<Configure>", lambda _event: _sync_scroll_region(app), add="+")
    window.bind("<Configure>", lambda _event: _schedule_reflow(app), add="+")
    window.bind("<MouseWheel>", lambda event: _wheel_band_window(app, event), add="+")
    window.bind("<Button-4>", lambda event: _wheel_band_window(app, event), add="+")
    window.bind("<Button-5>", lambda event: _wheel_band_window(app, event), add="+")

    frame = ttk.LabelFrame(body, text="Band room", padding=10)
    frame.grid(row=0, column=0, sticky="ew")
    frame.columnconfigure(1, weight=1)
    frame.columnconfigure(3, weight=1)
    app._band_frame = frame

    ttk.Label(frame, text="Name", style="Gaming.Micro.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Entry(frame, textvariable=app._band_name_var, width=16).grid(
        row=0, column=1, sticky="ew", padx=(6, 12)
    )
    ttk.Label(frame, text="Your part", style="Gaming.Micro.TLabel").grid(row=0, column=2, sticky="w")
    role_combo = ttk.Combobox(
        frame,
        textvariable=app._band_role_var,
        values=list(band_arranger.PART_LABELS),
        state="readonly",
        width=22,
    )
    role_combo.grid(row=0, column=3, sticky="ew", padx=(6, 0))
    role_combo.bind("<<ComboboxSelected>>", lambda _event: band_ui._role_changed(app))
    app._band_role_combo = role_combo

    ttk.Label(frame, text="Room code", style="Gaming.Micro.TLabel").grid(
        row=1, column=0, sticky="w", pady=(7, 0)
    )
    ttk.Entry(frame, textvariable=app._band_room_code_var, width=16).grid(
        row=1, column=1, sticky="ew", padx=(6, 12), pady=(7, 0)
    )
    buttons = ttk.Frame(frame)
    buttons.grid(row=1, column=2, columnspan=2, sticky="e", pady=(7, 0))
    ttk.Button(buttons, text="Create", command=lambda: band_ui._create_room(app)).pack(side="left")
    ttk.Button(buttons, text="Join", command=lambda: band_ui._join_room(app)).pack(side="left", padx=(5, 0))
    app._band_leave_button = ttk.Button(
        buttons,
        text="Leave",
        command=lambda: band_ui._disconnect_room(app),
        state="disabled",
    )
    app._band_leave_button.pack(side="left", padx=(5, 0))

    actions = ttk.Frame(frame)
    actions.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(7, 0))
    actions.columnconfigure(3, weight=1)
    app._band_ready_button = ttk.Button(
        actions,
        text="Ready",
        command=lambda: band_ui._toggle_ready(app),
        state="disabled",
    )
    app._band_ready_button.grid(row=0, column=0, sticky="w")
    app._band_start_button = ttk.Button(
        actions,
        text="Start Band",
        command=lambda: band_ui._start_band(app),
        state="disabled",
    )
    app._band_start_button.grid(row=0, column=1, sticky="w", padx=(6, 0))
    ttk.Label(actions, textvariable=app._band_sync_var, style="Hint.TLabel").grid(
        row=0, column=3, sticky="e"
    )

    ttk.Label(
        frame,
        textvariable=app._band_players_var,
        style="Hint.TLabel",
        wraplength=690,
        justify="left",
    ).grid(row=3, column=0, columnspan=4, sticky="ew", pady=(7, 0))
    ttk.Label(
        frame,
        textvariable=app._band_room_status_var,
        style="Hint.TLabel",
        wraplength=690,
        justify="left",
    ).grid(row=4, column=0, columnspan=4, sticky="ew", pady=(4, 0))
    ttk.Label(
        frame,
        textvariable=app._band_part_summary_var,
        style="Gaming.Micro.TLabel",
    ).grid(row=5, column=0, columnspan=4, sticky="w", pady=(4, 0))

    app.after(100, lambda: band_ui._drain_band_events(app))
    app.after(band_ui._HEARTBEAT_MS, lambda: band_ui._heartbeat(app))


def _patch_reopen_button() -> None:
    try:
        import ui_band_responsive_2026 as responsive
    except Exception:
        return
    responsive._show_band_room = _show_band_window
    responsive._hide_band_room = _hide_band_window


def install_detached_band_window() -> None:
    if getattr(band_ui, "_detached_band_window_2026_installed", False):
        return

    # install_band_mode() has already wrapped App._build_ui. Its wrapper resolves
    # these module globals at runtime, so replacing them here changes the actual
    # App instance without another invasive App-class wrapper.
    band_ui._build_band_panel = _build_detached_band_panel
    band_ui._set_band_frame_visible = _set_band_frame_visible
    _patch_reopen_button()

    original_finalize = full_ui._finalize_app_ui

    def finalize(app: Any) -> None:
        original_finalize(app)
        button = getattr(app, "_ux_band_room_button", None)
        if button is not None:
            try:
                button.configure(command=lambda: _show_band_window(app))
            except tk.TclError:
                pass
        # App construction must finish with the room window hidden until the
        # Band Mode checkbox is explicitly enabled.
        _hide_band_window(app)

    full_ui._finalize_app_ui = finalize
    band_ui._detached_band_window_2026_installed = True
