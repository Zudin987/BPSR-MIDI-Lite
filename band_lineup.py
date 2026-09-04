from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

import band_arranger
import band_sync
import band_ui


_PART_LABELS = {
    "keyboard": "Piano",
    "guitar": "Guitar",
    "bass": "Bass",
    "drums": "Drums",
}

_original_disconnect: Any = None


def active_parts(app: Any) -> tuple[band_arranger.BandPart, ...]:
    variables = getattr(app, "_band_lineup_vars", None)
    if not isinstance(variables, dict):
        return band_arranger.DEFAULT_ACTIVE_PARTS
    selected = [
        part
        for part in band_arranger.PART_ORDER
        if part in variables and bool(variables[part].get())
    ]
    try:
        return band_arranger.normalize_active_parts(selected)
    except ValueError:
        return band_arranger.DEFAULT_ACTIVE_PARTS


def _lineup_text(parts: tuple[band_arranger.BandPart, ...]) -> str:
    return " + ".join(_PART_LABELS[part] for part in parts)


def _set_lineup_control_state(app: Any) -> None:
    state = (
        "disabled"
        if getattr(app, "_band_connected", False) and not getattr(app, "_band_is_host", False)
        else "normal"
    )
    for widget in getattr(app, "_band_lineup_checks", {}).values():
        try:
            widget.configure(state=state)
        except tk.TclError:
            pass


def _choose_available_part(
    app: Any,
    parts: tuple[band_arranger.BandPart, ...],
) -> band_arranger.BandPart:
    occupied = {
        state.role
        for player_id, state in getattr(app, "_band_roster", band_sync.BandRoster()).players.items()
        if player_id != getattr(app, "_band_player_id", "")
    }
    for part in parts:
        if part not in occupied:
            return part
    return parts[0]


def _refresh_role_values(app: Any, *, force_valid: bool = True) -> None:
    parts = active_parts(app)
    combo = getattr(app, "_band_role_combo", None)
    if combo is not None:
        try:
            combo.configure(values=[band_arranger.part_label(part) for part in parts])
        except tk.TclError:
            pass

    current = band_ui._band_part(app)
    if force_valid and current not in parts:
        replacement = _choose_available_part(app, parts)
        try:
            app._band_role_var.set(band_arranger.part_label(replacement))
            band_ui._sync_role_to_instrument(app)
        except tk.TclError:
            pass


def _withdraw_ready(app: Any) -> None:
    if not bool(getattr(app, "_band_ready", False)):
        return
    app._band_ready = False
    try:
        app._band_ready_button.configure(text="Ready")
    except (AttributeError, tk.TclError):
        pass


def _schedule_reanalysis(app: Any) -> None:
    try:
        app._schedule_analysis(20)
    except Exception:
        pass


def _lineup_changed(app: Any, changed_part: band_arranger.BandPart) -> None:
    if bool(getattr(app, "_band_lineup_syncing", False)):
        return

    if getattr(app, "_band_connected", False) and not getattr(app, "_band_is_host", False):
        host = app._band_roster.host_state()
        if host is not None:
            _apply_lineup(app, host.active_parts, announce=False)
        app._band_room_status_var.set("Only the room host can change the active instruments")
        return

    variables = app._band_lineup_vars
    selected = [part for part in band_arranger.PART_ORDER if bool(variables[part].get())]
    if not selected:
        variables[changed_part].set(True)
        app._band_room_status_var.set("Band lineup needs at least one instrument")
        return

    _withdraw_ready(app)
    _refresh_role_values(app)
    _schedule_reanalysis(app)
    parts = active_parts(app)
    app._band_room_status_var.set(
        f"Lineup: {_lineup_text(parts)} — arrangement adapted; everyone must Ready again"
    )
    if getattr(app, "_band_connected", False):
        band_ui._publish_state(app)
    band_ui._refresh_room_ui(app)


def _apply_lineup(
    app: Any,
    parts: tuple[str, ...] | list[str],
    *,
    announce: bool = True,
) -> None:
    normalized = band_arranger.normalize_active_parts(parts)
    if normalized == active_parts(app):
        _set_lineup_control_state(app)
        _refresh_role_values(app)
        return

    app._band_lineup_syncing = True
    try:
        for part in band_arranger.PART_ORDER:
            app._band_lineup_vars[part].set(part in normalized)
    finally:
        app._band_lineup_syncing = False

    _withdraw_ready(app)
    _refresh_role_values(app)
    _schedule_reanalysis(app)
    _set_lineup_control_state(app)
    if announce:
        app._band_room_status_var.set(
            f"Host lineup updated: {_lineup_text(normalized)} — press Ready again"
        )


def _build_lineup_controls(app: Any) -> None:
    frame = getattr(app, "_band_frame", None)
    if frame is None or hasattr(app, "_band_lineup_vars"):
        return

    app._band_lineup_syncing = False
    app._band_lineup_vars = {
        part: tk.BooleanVar(master=app, value=True)
        for part in band_arranger.PART_ORDER
    }
    app._band_lineup_checks: dict[str, Any] = {}

    lineup = ttk.LabelFrame(frame, text="Players / instruments present", padding=(7, 5))
    lineup.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(7, 0))
    app._band_lineup_frame = lineup

    for column, part in enumerate(band_arranger.PART_ORDER):
        check = ttk.Checkbutton(
            lineup,
            text=_PART_LABELS[part],
            variable=app._band_lineup_vars[part],
            command=lambda p=part: _lineup_changed(app, p),
        )
        check.grid(row=0, column=column, sticky="w", padx=(0 if column == 0 else 10, 0))
        app._band_lineup_checks[part] = check

    ttk.Label(
        lineup,
        text=(
            "Tick only instruments your group actually has. Missing melodic parts are reassigned "
            "to the remaining players. If Drums is unticked, percussion is omitted. "
            "Drums use C4-B5 only; no High/Low Octave."
        ),
        style="Hint.TLabel",
        wraplength=690,
        justify="left",
    ).grid(row=1, column=0, columnspan=4, sticky="ew", pady=(4, 0))

    _refresh_role_values(app)
    _set_lineup_control_state(app)


def _local_state_payload(app: Any) -> dict[str, Any] | None:
    if not getattr(app, "_band_connected", False):
        return None
    room = str(app._band_room_code_var.get()).strip()
    midi_hash = band_ui._current_midi_hash(app)
    if not room or not midi_hash:
        return None
    return band_sync.make_state_payload(
        room_code=room,
        player_id=app._band_player_id,
        name=app._band_name_var.get(),
        role=band_ui._band_part(app),
        active_parts=active_parts(app),
        ready=bool(app._band_ready),
        midi_hash=midi_hash,
        app_version=band_ui._current_app_version(app),
        speed_percent=int(app.speed_var.get()),
        clock_sample=getattr(app, "_band_clock_sample", None),
        host=bool(app._band_is_host),
    )


def _disconnect_room(app: Any, *, announce: bool = True) -> None:
    assert _original_disconnect is not None
    _original_disconnect(app, announce=announce)
    _set_lineup_control_state(app)
    _refresh_role_values(app)


def _connect_room(app: Any, *, host: bool) -> None:
    if not bool(app._band_enabled_var.get()):
        app._band_room_status_var.set("Enable Band Mode first")
        return
    parts = active_parts(app)
    if band_ui._band_part(app) not in parts:
        _refresh_role_values(app)
    midi_hash = band_ui._current_midi_hash(app)
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
    app._band_room_status_var.set(
        f"Connecting… lineup: {_lineup_text(active_parts(app))}"
    )
    transport = band_sync.NtfyBandTransport(
        code,
        lambda payload: band_ui._queue_band_message(app, payload),
        on_status=lambda text: band_ui._queue_band_status(app, text),
    )
    app._band_transport = transport
    transport.start()
    try:
        app._band_leave_button.configure(state="normal")
    except tk.TclError:
        pass
    _set_lineup_control_state(app)
    band_ui._publish_state(app)
    band_ui._sync_clock_async(app)


def _role_changed(app: Any) -> None:
    parts = active_parts(app)
    if band_ui._band_part(app) not in parts:
        _refresh_role_values(app)
    _withdraw_ready(app)
    band_ui._sync_role_to_instrument(app)
    if getattr(app, "_band_connected", False):
        app._band_room_status_var.set("Part changed — press Ready again")
        band_ui._publish_state(app)
    else:
        app._band_room_status_var.set(
            f"Band part selected: {_PART_LABELS[band_ui._band_part(app)]}"
        )
    _schedule_reanalysis(app)
    band_ui._refresh_room_ui(app)


def _toggle_ready(app: Any) -> None:
    if not getattr(app, "_band_connected", False):
        return
    if band_ui._band_part(app) not in active_parts(app):
        app._band_room_status_var.set("Choose a part that is enabled in the lineup")
        return
    if getattr(app, "_band_clock_sample", None) is None:
        app._band_room_status_var.set("Clock sync must finish before Ready")
        return
    if not band_ui._current_midi_hash(app):
        app._band_room_status_var.set("Choose a valid MIDI first")
        return
    app._band_ready = not bool(app._band_ready)
    app._band_ready_button.configure(text="Unready" if app._band_ready else "Ready")
    band_ui._publish_state(app)


def _start_payload_is_compatible(app: Any, payload: dict[str, Any]) -> bool:
    if int(payload.get("proto", 0)) != band_sync.BAND_PROTOCOL_VERSION:
        return False
    if str(payload.get("room", "")) != str(app._band_room_code_var.get()):
        return False
    host_id = band_ui._host_player_id(app)
    if host_id is not None and str(payload.get("player_id", "")) != host_id:
        app._band_room_status_var.set("Ignored a Start command that did not come from the room host")
        return False
    if str(payload.get("midi_sha256", "")) != band_ui._current_midi_hash(app):
        app._band_room_status_var.set("Start blocked: your MIDI no longer matches the host")
        return False
    if str(payload.get("app_version", "")) != band_ui._current_app_version(app):
        app._band_room_status_var.set("Start blocked: BPSR MIDI versions do not match")
        return False
    if int(payload.get("speed_percent", -1)) != int(app.speed_var.get()):
        app._band_room_status_var.set("Start blocked: song speed does not match")
        return False
    try:
        remote_parts = band_sync.normalize_active_parts(payload.get("active_parts"))
    except (TypeError, ValueError):
        app._band_room_status_var.set("Start blocked: invalid Band lineup")
        return False
    if remote_parts != active_parts(app):
        app._band_room_status_var.set("Start blocked: Band lineup does not match the host")
        return False
    if band_ui._band_part(app) not in remote_parts:
        app._band_room_status_var.set("Start blocked: your selected part is not in the host lineup")
        return False
    return True


def _schedule_synchronized_playback(app: Any, payload: dict[str, Any]) -> None:
    if not _start_payload_is_compatible(app, payload):
        return
    sample = getattr(app, "_band_clock_sample", None)
    if sample is None:
        app._band_room_status_var.set("Start blocked: clock is not synchronized")
        return

    app._analyze()
    plan = getattr(app, "current_plan", None)
    info = band_arranger.plan_info(plan)
    if plan is None or info is None or info.stats.selected_notes <= 0:
        app._band_room_status_var.set("Start blocked: your selected Band part is empty")
        return
    if plan.page_switches or any(event.kind == "page" for event in plan.events):
        app._band_room_status_var.set("Start blocked: this Band part produced a page key")
        return
    if info.part == "drums" and (
        int(getattr(plan, "octave_switches", 0))
        or any(event.kind == "state" for event in plan.events)
    ):
        app._band_room_status_var.set("Start blocked: Drums unexpectedly requested High/Low Octave")
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
    band_ui._publish_state(app)


def _start_band(app: Any) -> None:
    if not getattr(app, "_band_connected", False) or not getattr(app, "_band_is_host", False):
        return
    midi_hash = band_ui._current_midi_hash(app)
    sample = getattr(app, "_band_clock_sample", None)
    if sample is None:
        app._band_room_status_var.set("Host clock is not synchronized yet")
        return

    parts = active_parts(app)
    band_ui._publish_state(app)
    issues = app._band_roster.compatibility_issues(
        expected_hash=midi_hash,
        expected_version=band_ui._current_app_version(app),
        expected_speed=int(app.speed_var.get()),
        expected_active_parts=parts,
    )
    if issues:
        app._band_room_status_var.set("Cannot start: " + issues[0])
        band_ui._refresh_room_ui(app)
        return

    start_utc_ms = int(
        band_sync.corrected_utc_ms(sample) + band_sync.START_LEAD_SECONDS * 1000.0
    )
    payload = band_sync.make_start_payload(
        room_code=app._band_room_code_var.get(),
        player_id=app._band_player_id,
        start_utc_ms=start_utc_ms,
        midi_hash=midi_hash,
        app_version=band_ui._current_app_version(app),
        speed_percent=int(app.speed_var.get()),
        active_parts=parts,
    )
    transport = getattr(app, "_band_transport", None)
    if transport is None:
        return
    transport.publish_async(payload)
    band_ui._schedule_synchronized_playback(app, payload)


def _handle_band_message(app: Any, payload: dict[str, Any]) -> None:
    event = str(payload.get("event", ""))
    if event in {"state", "leave"}:
        player_id = str(payload.get("player_id", ""))
        new_player = (
            event == "state"
            and player_id not in app._band_roster.players
            and player_id != app._band_player_id
        )
        app._band_roster.apply(payload)

        if (
            event == "state"
            and bool(payload.get("host", False))
            and not getattr(app, "_band_is_host", False)
            and player_id != app._band_player_id
        ):
            try:
                host_parts = band_sync.normalize_active_parts(payload.get("active_parts"))
                changed = host_parts != active_parts(app)
                _apply_lineup(app, host_parts, announce=changed)
                if changed:
                    app.after(80, lambda: band_ui._publish_state(app))
            except (TypeError, ValueError, tk.TclError):
                pass

        if new_player:
            try:
                app.after(150, lambda: band_ui._publish_state(app))
            except tk.TclError:
                pass
        band_ui._refresh_room_ui(app)
        return
    if event == "start":
        band_ui._schedule_synchronized_playback(app, payload)


def _refresh_room_ui(app: Any) -> None:
    try:
        app._band_roster.prune()
        app._band_players_var.set(app._band_roster.compact_text())
        connected = bool(getattr(app, "_band_connected", False))
        clock_ok = getattr(app, "_band_clock_sample", None) is not None
        valid_part = band_ui._band_part(app) in active_parts(app)
        app._band_ready_button.configure(
            state="normal" if connected and clock_ok and valid_part else "disabled"
        )
        app._band_leave_button.configure(state="normal" if connected else "disabled")
        _set_lineup_control_state(app)

        if connected and getattr(app, "_band_is_host", False):
            issues = app._band_roster.compatibility_issues(
                expected_hash=band_ui._current_midi_hash(app),
                expected_version=band_ui._current_app_version(app),
                expected_speed=int(app.speed_var.get()),
                expected_active_parts=active_parts(app),
            )
            app._band_start_button.configure(state="normal" if not issues else "disabled")
        else:
            app._band_start_button.configure(state="disabled")
    except (tk.TclError, AttributeError, ValueError):
        pass


def _update_band_plan_summary(app: Any) -> None:
    enabled_var = getattr(app, "_band_enabled_var", None)
    if enabled_var is None or not bool(enabled_var.get()):
        return
    info = band_arranger.plan_info(getattr(app, "current_plan", None))
    if info is None:
        try:
            app._band_part_summary_var.set(
                f"Band part: waiting · lineup {_lineup_text(active_parts(app))}"
            )
        except tk.TclError:
            pass
        return

    stats = info.stats
    text = (
        f"Band part: {_PART_LABELS[info.part]} · {stats.selected_notes:,}/{stats.original_notes:,} "
        f"source notes · lineup {_lineup_text(stats.active_parts)} · split v{info.arrangement_version}"
    )
    if info.part == "drums":
        text += (
            f" · C4-B5 fixed · {stats.drum_remapped_notes:,} percussion note(s) mapped"
            " · no octave controls"
        )
    try:
        app._band_part_summary_var.set(text)
        if hasattr(app, "_product_summary_var"):
            current = str(app._product_summary_var.get())
            if not current.startswith("Band "):
                app._product_summary_var.set(f"Band {_PART_LABELS[info.part]} · {current}")
    except tk.TclError:
        pass


def install_band_lineup(app_module: Any) -> None:
    """Add host-selected active instruments and verified C4-B5 Drum support."""
    global _original_disconnect
    if getattr(app_module, "_band_lineup_installed", False):
        return
    if not getattr(app_module, "_band_mode_installed", False):
        raise RuntimeError("Band Mode must be installed before Band lineup support.")

    _original_disconnect = band_ui._disconnect_room

    # Existing Band UI callbacks resolve these module globals at click/runtime,
    # so replacing them upgrades the already-built room workflow cleanly.
    band_ui._local_state_payload = _local_state_payload
    band_ui._disconnect_room = _disconnect_room
    band_ui._connect_room = _connect_room
    band_ui._role_changed = _role_changed
    band_ui._toggle_ready = _toggle_ready
    band_ui._start_payload_is_compatible = _start_payload_is_compatible
    band_ui._schedule_synchronized_playback = _schedule_synchronized_playback
    band_ui._start_band = _start_band
    band_ui._handle_band_message = _handle_band_message
    band_ui._refresh_room_ui = _refresh_room_ui
    band_ui._update_band_plan_summary = _update_band_plan_summary

    app_class = app_module.App
    original_build = app_class._build_ui

    def build_ui(self: Any) -> None:
        original_build(self)
        _build_lineup_controls(self)

    app_class._build_ui = build_ui
    app_module._band_lineup_installed = True
