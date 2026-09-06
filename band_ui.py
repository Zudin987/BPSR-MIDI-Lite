from __future__ import annotations

import getpass
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

import band_arranger
import band_sync


_ROLE_TO_INSTRUMENT_LABEL = {
    "keyboard": "Keyboard",
    "guitar": "Guitar",
    "bass": "Bass",
}
_HEARTBEAT_MS = 8_000
_ROSTER_REFRESH_MS = 500
_CLOCK_REFRESH_SECONDS = 60.0


def _safe_username() -> str:
    try:
        value = getpass.getuser().strip()
    except Exception:
        value = "Player"
    return value[:24] or "Player"


def _current_app_version(app: Any) -> str:
    return str(getattr(getattr(app, "_modern_module", None), "APP_VERSION", "unknown"))


def _current_midi_hash(app: Any) -> str:
    path_text = str(getattr(app, "file_var", tk.StringVar(value="")).get()).strip()
    if not path_text:
        return ""
    path = Path(path_text)
    try:
        stat = path.stat()
    except OSError:
        return ""
    key = (str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size))
    cached_key = getattr(app, "_band_hash_cache_key", None)
    if cached_key == key:
        return str(getattr(app, "_band_hash_cache_value", ""))
    try:
        digest = band_sync.midi_sha256(path)
    except OSError:
        return ""
    app._band_hash_cache_key = key
    app._band_hash_cache_value = digest
    return digest


def _band_part(app: Any) -> band_arranger.BandPart:
    return band_arranger.part_from_label(str(app._band_role_var.get()))


def _set_band_frame_visible(app: Any, visible: bool) -> None:
    frame = getattr(app, "_band_frame", None)
    if frame is None:
        return
    try:
        if visible:
            frame.grid()
        else:
            frame.grid_remove()
    except tk.TclError:
        pass


def _sync_role_to_instrument(app: Any) -> None:
    part = _band_part(app)
    target = _ROLE_TO_INSTRUMENT_LABEL.get(part)
    if target is None:
        return
    try:
        if app.instrument_var.get() != target:
            app.instrument_var.set(target)
            app._instrument_changed()
    except (tk.TclError, AttributeError):
        return


def _disconnect_room(app: Any, *, announce: bool = True) -> None:
    transport = getattr(app, "_band_transport", None)
    if transport is not None:
        if announce:
            try:
                transport.publish_async(
                    band_sync.make_leave_payload(
                        room_code=app._band_room_code_var.get(),
                        player_id=app._band_player_id,
                    )
                )
            except Exception:
                pass
        transport.stop()
    app._band_transport = None
    app._band_connected = False
    app._band_is_host = False
    app._band_ready = False
    app._band_clock_sample = None
    app._band_roster = band_sync.BandRoster()
    try:
        app._band_ready_button.configure(text="Ready", state="disabled")
        app._band_start_button.configure(state="disabled")
        app._band_leave_button.configure(state="disabled")
        app._band_sync_var.set("Clock: not synchronized")
        app._band_room_status_var.set("Not connected")
        app._band_players_var.set("No players connected")
    except (tk.TclError, AttributeError):
        pass


def _queue_band_status(app: Any, text: str) -> None:
    try:
        app._band_event_queue.put(("status", text))
    except Exception:
        pass


def _queue_band_message(app: Any, payload: dict[str, Any]) -> None:
    try:
        app._band_event_queue.put(("message", payload))
    except Exception:
        pass


def _local_state_payload(app: Any) -> dict[str, Any] | None:
    if not getattr(app, "_band_connected", False):
        return None
    room = str(app._band_room_code_var.get()).strip()
    midi_hash = _current_midi_hash(app)
    if not room or not midi_hash:
        return None
    return band_sync.make_state_payload(
        room_code=room,
        player_id=app._band_player_id,
        name=app._band_name_var.get(),
        role=_band_part(app),
        ready=bool(app._band_ready),
        midi_hash=midi_hash,
        app_version=_current_app_version(app),
        speed_percent=int(app.speed_var.get()),
        clock_sample=getattr(app, "_band_clock_sample", None),
        host=bool(app._band_is_host),
    )


def _publish_state(app: Any) -> None:
    payload = _local_state_payload(app)
    transport = getattr(app, "_band_transport", None)
    if payload is None or transport is None:
        return
    app._band_roster.apply(payload)
    transport.publish_async(payload)
    _refresh_room_ui(app)


def _heartbeat(app: Any) -> None:
    try:
        if getattr(app, "_band_connected", False):
            _publish_state(app)
        app.after(_HEARTBEAT_MS, lambda: _heartbeat(app))
    except tk.TclError:
        pass


def _sync_clock_async(app: Any) -> None:
    if getattr(app, "_band_clock_sync_running", False):
        return
    app._band_clock_sync_running = True
    try:
        app._band_sync_var.set("Clock: synchronizing…")
        app._band_ready_button.configure(state="disabled")
    except (tk.TclError, AttributeError):
        pass

    def worker() -> None:
        sample = band_sync.synchronize_clock()
        try:
            app._band_event_queue.put(("clock", sample))
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


def _maybe_refresh_clock(app: Any) -> None:
    if not getattr(app, "_band_connected", False):
        return
    last = float(getattr(app, "_band_clock_synced_at", 0.0))
    if time.monotonic() - last >= _CLOCK_REFRESH_SECONDS:
        _sync_clock_async(app)


def _connect_room(app: Any, *, host: bool) -> None:
    if not bool(app._band_enabled_var.get()):
        app._band_room_status_var.set("Enable Band Mode first")
        return
    if _band_part(app) == "drums":
        app._band_room_status_var.set("Drums can join later, after the real BPSR drum mapping is added")
        return
    midi_hash = _current_midi_hash(app)
    if not midi_hash:
        app._band_room_status_var.set("Choose a valid MIDI first")
        return
    try:
        code = band_sync.normalize_room_code(app._band_room_code_var.get())
    except ValueError as exc:
        app._band_room_status_var.set(str(exc))
        return

    _disconnect_room(app, announce=False)
    app._band_is_host = bool(host)
    app._band_connected = True
    app._band_ready = False
    app._band_roster = band_sync.BandRoster()
    app._band_room_status_var.set("Connecting…")
    transport = band_sync.NtfyBandTransport(
        code,
        lambda payload: _queue_band_message(app, payload),
        on_status=lambda text: _queue_band_status(app, text),
    )
    app._band_transport = transport
    transport.start()
    try:
        app._band_leave_button.configure(state="normal")
    except tk.TclError:
        pass
    _publish_state(app)
    _sync_clock_async(app)


def _create_room(app: Any) -> None:
    app._band_room_code_var.set(band_sync.generate_room_code())
    _connect_room(app, host=True)


def _join_room(app: Any) -> None:
    _connect_room(app, host=False)


def _role_changed(app: Any) -> None:
    app._band_ready = False
    try:
        app._band_ready_button.configure(text="Ready")
    except tk.TclError:
        pass
    _sync_role_to_instrument(app)
    if _band_part(app) == "drums":
        app._band_room_status_var.set(
            "Drum part detection is ready, but playback is disabled until the BPSR drum key layout is verified."
        )
    elif getattr(app, "_band_connected", False):
        app._band_room_status_var.set("Part changed — press Ready again")
        _publish_state(app)
    try:
        app._schedule_analysis(20)
    except Exception:
        pass
    _refresh_room_ui(app)


def _toggle_band_mode(app: Any) -> None:
    enabled = bool(app._band_enabled_var.get())
    _set_band_frame_visible(app, enabled)
    if enabled:
        instrument = str(app._instrument_code())
        if instrument in band_arranger.PART_LABELS_REVERSE:
            app._band_role_var.set(band_arranger.part_label(instrument))
        _sync_role_to_instrument(app)
        try:
            app.start_button.configure(text="Practice Part")
        except tk.TclError:
            pass
        app._band_room_status_var.set("Band part enabled — create or join a room for synchronized start")
    else:
        _disconnect_room(app)
        try:
            app.start_button.configure(text="Play in BPSR")
        except tk.TclError:
            pass
    try:
        app._schedule_analysis(20)
    except Exception:
        pass
    _refresh_room_ui(app)


def _toggle_ready(app: Any) -> None:
    if not getattr(app, "_band_connected", False):
        return
    if _band_part(app) == "drums":
        return
    if getattr(app, "_band_clock_sample", None) is None:
        app._band_room_status_var.set("Clock sync must finish before Ready")
        return
    if not _current_midi_hash(app):
        app._band_room_status_var.set("Choose a valid MIDI first")
        return
    app._band_ready = not bool(app._band_ready)
    app._band_ready_button.configure(text="Unready" if app._band_ready else "Ready")
    _publish_state(app)


def _host_player_id(app: Any) -> str | None:
    for state in app._band_roster.players.values():
        if state.host:
            return state.player_id
    return None


def _start_payload_is_compatible(app: Any, payload: dict[str, Any]) -> bool:
    if int(payload.get("proto", 0)) != band_sync.BAND_PROTOCOL_VERSION:
        return False
    if str(payload.get("room", "")) != str(app._band_room_code_var.get()):
        return False
    host_id = _host_player_id(app)
    if host_id is not None and str(payload.get("player_id", "")) != host_id:
        app._band_room_status_var.set("Ignored a Start command that did not come from the room host")
        return False
    if str(payload.get("midi_sha256", "")) != _current_midi_hash(app):
        app._band_room_status_var.set("Start blocked: your MIDI no longer matches the host")
        return False
    if str(payload.get("app_version", "")) != _current_app_version(app):
        app._band_room_status_var.set("Start blocked: BPSR MIDI versions do not match")
        return False
    if int(payload.get("speed_percent", -1)) != int(app.speed_var.get()):
        app._band_room_status_var.set("Start blocked: song speed does not match")
        return False
    return True


def _schedule_synchronized_playback(app: Any, payload: dict[str, Any]) -> None:
    if not _start_payload_is_compatible(app, payload):
        return
    if _band_part(app) == "drums":
        app._band_room_status_var.set("Start blocked: Drum key mapping is not configured")
        return
    sample = getattr(app, "_band_clock_sample", None)
    if sample is None:
        app._band_room_status_var.set("Start blocked: clock is not synchronized")
        return

    app._analyze()
    plan = getattr(app, "current_plan", None)
    if plan is None:
        app._band_room_status_var.set("Start blocked: band part could not be prepared")
        return
    if plan.page_switches or any(event.kind == "page" for event in plan.events):
        app._band_room_status_var.set("Start blocked: this Category produced a page key")
        return

    delay = band_sync.delay_until_utc_ms(int(payload.get("start_utc_ms", 0)), sample)
    if delay < 0.75:
        app._band_room_status_var.set("Start signal arrived too late — ask the host to Start Band again")
        return
    try:
        app.player.start(
            plan,
            delay,
            app._thread_status,
            app._thread_finished,
            input_backend=app._input_backend_code(),
        )
    except Exception as exc:  # noqa: BLE001
        app._band_room_status_var.set(f"Could not start band playback: {exc}")
        return

    try:
        app.start_button.configure(state="disabled")
        app.pause_button.configure(state="disabled", text="Pause")
        app.stop_button.configure(state="normal")
        app.progress["value"] = 0
    except tk.TclError:
        pass
    app._band_ready = False
    try:
        app._band_ready_button.configure(text="Ready")
    except tk.TclError:
        pass
    app._band_room_status_var.set(
        f"Synchronized start armed — switch to BPSR before the {delay:.1f}s countdown ends"
    )
    _publish_state(app)


def _start_band(app: Any) -> None:
    if not getattr(app, "_band_connected", False) or not getattr(app, "_band_is_host", False):
        return
    midi_hash = _current_midi_hash(app)
    sample = getattr(app, "_band_clock_sample", None)
    if sample is None:
        app._band_room_status_var.set("Host clock is not synchronized yet")
        return
    _publish_state(app)
    issues = app._band_roster.compatibility_issues(
        expected_hash=midi_hash,
        expected_version=_current_app_version(app),
        expected_speed=int(app.speed_var.get()),
        drums_supported=False,
    )
    if issues:
        app._band_room_status_var.set("Cannot start: " + issues[0])
        _refresh_room_ui(app)
        return

    start_utc_ms = int(band_sync.corrected_utc_ms(sample) + band_sync.START_LEAD_SECONDS * 1000.0)
    payload = band_sync.make_start_payload(
        room_code=app._band_room_code_var.get(),
        player_id=app._band_player_id,
        start_utc_ms=start_utc_ms,
        midi_hash=midi_hash,
        app_version=_current_app_version(app),
        speed_percent=int(app.speed_var.get()),
    )
    transport = getattr(app, "_band_transport", None)
    if transport is None:
        return
    transport.publish_async(payload)
    _schedule_synchronized_playback(app, payload)


def _handle_band_message(app: Any, payload: dict[str, Any]) -> None:
    event = str(payload.get("event", ""))
    if event in {"state", "leave"}:
        new_player = (
            event == "state"
            and str(payload.get("player_id", "")) not in app._band_roster.players
            and str(payload.get("player_id", "")) != app._band_player_id
        )
        app._band_roster.apply(payload)
        if new_player:
            try:
                app.after(150, lambda: _publish_state(app))
            except tk.TclError:
                pass
        _refresh_room_ui(app)
        return
    if event == "start":
        _schedule_synchronized_playback(app, payload)


def _drain_band_events(app: Any) -> None:
    try:
        while True:
            kind, payload = app._band_event_queue.get_nowait()
            if kind == "status":
                app._band_room_status_var.set(str(payload))
            elif kind == "message" and isinstance(payload, dict):
                _handle_band_message(app, payload)
            elif kind == "clock":
                app._band_clock_sync_running = False
                app._band_clock_sample = payload
                app._band_clock_synced_at = time.monotonic()
                if payload is None:
                    app._band_sync_var.set("Clock: sync failed (UDP/NTP blocked?)")
                    app._band_room_status_var.set("Clock sync failed; synchronized Start Band is unavailable")
                else:
                    app._band_sync_var.set(
                        f"Clock: synced · {payload.rtt_ms:.0f} ms RTT · {payload.offset_ms:+.1f} ms offset"
                    )
                    if getattr(app, "_band_connected", False):
                        app._band_room_status_var.set("Room ready — choose your part and press Ready")
                _publish_state(app)
                _refresh_room_ui(app)
    except queue.Empty:
        pass
    _maybe_refresh_clock(app)
    try:
        app.after(100, lambda: _drain_band_events(app))
    except tk.TclError:
        pass


def _refresh_room_ui(app: Any) -> None:
    try:
        app._band_roster.prune()
        app._band_players_var.set(app._band_roster.compact_text())
        connected = bool(getattr(app, "_band_connected", False))
        clock_ok = getattr(app, "_band_clock_sample", None) is not None
        drums = _band_part(app) == "drums"
        app._band_ready_button.configure(
            state="normal" if connected and clock_ok and not drums else "disabled"
        )
        app._band_leave_button.configure(state="normal" if connected else "disabled")
        if connected and getattr(app, "_band_is_host", False):
            issues = app._band_roster.compatibility_issues(
                expected_hash=_current_midi_hash(app),
                expected_version=_current_app_version(app),
                expected_speed=int(app.speed_var.get()),
                drums_supported=False,
            )
            app._band_start_button.configure(state="normal" if not issues else "disabled")
        else:
            app._band_start_button.configure(state="disabled")
    except (tk.TclError, AttributeError, ValueError):
        pass


def _update_band_plan_summary(app: Any) -> None:
    if not bool(getattr(app, "_band_enabled_var", tk.BooleanVar(value=False)).get()):
        return
    info = band_arranger.plan_info(getattr(app, "current_plan", None))
    if info is None:
        try:
            app._band_part_summary_var.set("Band part: waiting for a playable MIDI")
        except tk.TclError:
            pass
        return
    stats = info.stats
    labels = {
        "keyboard": "Piano",
        "guitar": "Guitar",
        "bass": "Bass",
        "drums": "Drums",
    }
    text = (
        f"Band part: {labels[info.part]} · {stats.selected_notes:,}/{stats.original_notes:,} source notes · "
        f"split v{info.arrangement_version}"
    )
    try:
        app._band_part_summary_var.set(text)
        if hasattr(app, "_product_summary_var"):
            current = str(app._product_summary_var.get())
            if not current.startswith("Band "):
                app._product_summary_var.set(f"Band {labels[info.part]} · {current}")
    except tk.TclError:
        pass


def _build_band_panel(app: Any) -> None:
    center = getattr(app, "_product_center", None)
    setup = getattr(app, "_product_setup_frame", None)
    if center is None or setup is None:
        return

    app._band_enabled_var = tk.BooleanVar(master=app, value=False)
    current_part = str(app._instrument_code())
    app._band_role_var = tk.StringVar(
        master=app,
        value=band_arranger.part_label(current_part if current_part in {"keyboard", "guitar", "bass"} else "keyboard"),
    )
    app._band_room_code_var = tk.StringVar(master=app, value="")
    app._band_name_var = tk.StringVar(master=app, value=_safe_username())
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

    ttk.Checkbutton(
        setup,
        text="Band Mode (Beta)",
        variable=app._band_enabled_var,
        command=lambda: _toggle_band_mode(app),
    ).grid(row=3, column=0, sticky="w", pady=(7, 0))
    ttk.Label(
        setup,
        text="Same MIDI → separate parts → synchronized room start",
        style="Hint.TLabel",
    ).grid(row=3, column=1, sticky="w", pady=(7, 0))

    # Insert the Band card between BPSR setup and Song Check without creating a
    # second window. Move the existing center rows down once.
    for child in tuple(center.grid_slaves()):
        try:
            info = child.grid_info()
            row = int(info.get("row", 0))
            if row >= 1:
                child.grid_configure(row=row + 1)
        except (tk.TclError, TypeError, ValueError):
            continue
    center.rowconfigure(3, weight=0)
    center.rowconfigure(4, weight=1)

    frame = ttk.LabelFrame(center, text="Band room", padding=8)
    frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
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
    role_combo.bind("<<ComboboxSelected>>", lambda _event: _role_changed(app))
    app._band_role_combo = role_combo

    ttk.Label(frame, text="Room code", style="Gaming.Micro.TLabel").grid(
        row=1, column=0, sticky="w", pady=(7, 0)
    )
    ttk.Entry(frame, textvariable=app._band_room_code_var, width=16).grid(
        row=1, column=1, sticky="ew", padx=(6, 12), pady=(7, 0)
    )
    buttons = ttk.Frame(frame)
    buttons.grid(row=1, column=2, columnspan=2, sticky="e", pady=(7, 0))
    ttk.Button(buttons, text="Create", command=lambda: _create_room(app)).pack(side="left")
    ttk.Button(buttons, text="Join", command=lambda: _join_room(app)).pack(side="left", padx=(5, 0))
    app._band_leave_button = ttk.Button(
        buttons,
        text="Leave",
        command=lambda: _disconnect_room(app),
        state="disabled",
    )
    app._band_leave_button.pack(side="left", padx=(5, 0))

    actions = ttk.Frame(frame)
    actions.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(7, 0))
    actions.columnconfigure(3, weight=1)
    app._band_ready_button = ttk.Button(
        actions,
        text="Ready",
        command=lambda: _toggle_ready(app),
        state="disabled",
    )
    app._band_ready_button.grid(row=0, column=0, sticky="w")
    app._band_start_button = ttk.Button(
        actions,
        text="Start Band",
        command=lambda: _start_band(app),
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

    _set_band_frame_visible(app, False)
    app.after(100, lambda: _drain_band_events(app))
    app.after(_HEARTBEAT_MS, lambda: _heartbeat(app))


def install_band_mode(app_module: Any) -> None:
    """Install deterministic Band parts plus zero-account synchronized rooms."""
    if getattr(app_module, "_band_mode_installed", False):
        return

    band_arranger.install_band_arranger(app_module)
    app_class = app_module.App
    original_build = app_class._build_ui
    original_analyze = app_class._analyze
    original_close = app_class._on_close

    def build_ui(self: Any) -> None:
        original_build(self)
        _build_band_panel(self)

    def analyze(self: Any) -> None:
        previous_hash = str(getattr(self, "_band_last_analyzed_hash", ""))
        previous_speed = int(getattr(self, "_band_last_analyzed_speed", int(self.speed_var.get())))
        original_analyze(self)
        if not hasattr(self, "_band_enabled_var"):
            return
        current_hash = _current_midi_hash(self)
        current_speed = int(self.speed_var.get())
        if getattr(self, "_band_connected", False) and (
            (previous_hash and previous_hash != current_hash) or previous_speed != current_speed
        ):
            self._band_ready = False
            try:
                self._band_ready_button.configure(text="Ready")
            except tk.TclError:
                pass
            self._band_room_status_var.set("Song or speed changed — press Ready again")
            _publish_state(self)
        self._band_last_analyzed_hash = current_hash
        self._band_last_analyzed_speed = current_speed
        _update_band_plan_summary(self)
        _refresh_room_ui(self)

    def on_close(self: Any) -> None:
        try:
            _disconnect_room(self)
        except Exception:
            pass
        original_close(self)

    app_class._build_ui = build_ui
    app_class._analyze = analyze
    app_class._on_close = on_close
    app_module._band_mode_installed = True
