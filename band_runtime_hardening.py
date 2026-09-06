from __future__ import annotations

import time
import tkinter as tk
from pathlib import Path
from typing import Any

import band_arranger
import band_sync
import band_ui
import player as player_module


_original_player_run: Any = None
_original_schedule_synchronized_playback: Any = None
_original_toggle_ready: Any = None


def _safe_current_midi_hash(app: Any) -> str:
    """Hash the selected MIDI without creating fallback Tk variables."""
    file_var = getattr(app, "file_var", None)
    if file_var is None:
        return ""
    try:
        path_text = str(file_var.get()).strip()
    except tk.TclError:
        return ""
    if not path_text:
        return ""
    path = Path(path_text)
    try:
        stat = path.stat()
    except OSError:
        return ""
    key = (str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size))
    if getattr(app, "_band_hash_cache_key", None) == key:
        return str(getattr(app, "_band_hash_cache_value", ""))
    try:
        digest = band_sync.midi_sha256(path)
    except OSError:
        return ""
    app._band_hash_cache_key = key
    app._band_hash_cache_value = digest
    return digest


def _band_compatibility_version(_app: Any) -> str:
    """Shared Lite/Studio token for deterministic Band clients."""
    return (
        f"band-proto-{band_sync.BAND_PROTOCOL_VERSION}"
        f"-arr-{band_arranger.BAND_ARRANGEMENT_VERSION}"
    )


def _deadline_preserving_player_run(
    self: Any,
    plan: Any,
    start_delay: float,
    on_status: Any,
    on_finished: Any,
    input_backend: str = "scan",
) -> None:
    """Convert the Band deadline back to delay inside the worker thread."""
    assert _original_player_run is not None
    deadline = getattr(self, "_band_start_deadline_perf", None)
    if deadline is not None:
        try:
            delattr(self, "_band_start_deadline_perf")
        except AttributeError:
            pass
        start_delay = max(0.0, float(deadline) - time.perf_counter())
    _original_player_run(
        self,
        plan,
        start_delay,
        on_status,
        on_finished,
        input_backend,
    )


def _hardened_schedule_synchronized_playback(app: Any, payload: dict[str, Any]) -> None:
    assert _original_schedule_synchronized_playback is not None

    start_utc_ms = int(payload.get("start_utc_ms", 0))
    if start_utc_ms <= 0:
        _original_schedule_synchronized_playback(app, payload)
        return

    # ntfy delivers published messages to the publisher too, and Start is sent
    # redundantly. Never arm the same client twice for one absolute deadline.
    if getattr(getattr(app, "player", None), "is_playing", False):
        return
    if int(getattr(app, "_band_last_start_utc_ms", 0)) == start_utc_ms:
        return

    try:
        compatible = band_ui._start_payload_is_compatible(app, payload)
        sample = getattr(app, "_band_clock_sample", None)
        delay = (
            band_sync.delay_until_utc_ms(start_utc_ms, sample)
            if sample is not None
            else 0.0
        )
    except Exception:
        compatible = False
        sample = None
        delay = 0.0

    # Piano/Guitar/Bass/Drums all use the same absolute local deadline. Drum
    # mapping is now verified C4-B5 and therefore no longer needs an exception.
    if compatible and sample is not None and delay >= 0.75:
        app.player._band_start_deadline_perf = time.perf_counter() + delay

    _original_schedule_synchronized_playback(app, payload)

    if getattr(getattr(app, "player", None), "is_playing", False):
        app._band_last_start_utc_ms = start_utc_ms
    else:
        try:
            delattr(app.player, "_band_start_deadline_perf")
        except (AttributeError, TypeError):
            pass


def _sync_part_after_manual_instrument_change(app: Any) -> None:
    enabled_var = getattr(app, "_band_enabled_var", None)
    role_var = getattr(app, "_band_role_var", None)
    if enabled_var is None or role_var is None:
        return
    try:
        if not bool(enabled_var.get()):
            return
        instrument = str(app._instrument_code())
    except (tk.TclError, AttributeError):
        return
    if instrument not in {"keyboard", "guitar", "bass"}:
        return

    active_parts = band_arranger._active_parts_from_app(app)
    if instrument not in active_parts:
        try:
            app._band_room_status_var.set(
                f"{instrument.title()} is not enabled in the current Band lineup"
            )
        except (AttributeError, tk.TclError):
            pass
        return

    expected = band_arranger.part_label(instrument)  # type: ignore[arg-type]
    try:
        if str(role_var.get()) == expected:
            return
        role_var.set(expected)
        app._band_ready = False
        ready_button = getattr(app, "_band_ready_button", None)
        if ready_button is not None:
            ready_button.configure(text="Ready")
        status_var = getattr(app, "_band_room_status_var", None)
        if status_var is not None:
            status_var.set("Instrument changed — band part updated; press Ready again")
        if getattr(app, "_band_connected", False):
            band_ui._publish_state(app)
    except tk.TclError:
        pass


def _prepare_local_band_practice(app: Any) -> bool:
    """Withdraw Ready before local practice; all verified Band parts may play."""
    enabled_var = getattr(app, "_band_enabled_var", None)
    if enabled_var is None:
        return True
    try:
        if not bool(enabled_var.get()):
            return True
    except tk.TclError:
        return True

    current_part = band_ui._band_part(app)
    if current_part not in band_arranger._active_parts_from_app(app):
        try:
            app._band_room_status_var.set(
                "Practice blocked: your selected part is disabled in the Band lineup"
            )
        except (AttributeError, tk.TclError):
            pass
        return False

    if bool(getattr(app, "_band_ready", False)):
        app._band_ready = False
        try:
            app._band_ready_button.configure(text="Ready")
        except (AttributeError, tk.TclError):
            pass
        if getattr(app, "_band_connected", False):
            band_ui._publish_state(app)
    return True


def _hardened_toggle_ready(app: Any) -> None:
    """Only let a client Ready after its selected Band part is actually usable."""
    assert _original_toggle_ready is not None
    if bool(getattr(app, "_band_ready", False)):
        _original_toggle_ready(app)
        return
    if not getattr(app, "_band_connected", False):
        return

    current_part = band_ui._band_part(app)
    if current_part not in band_arranger._active_parts_from_app(app):
        try:
            app._band_room_status_var.set(
                "Cannot Ready: your selected part is disabled in the current lineup"
            )
        except tk.TclError:
            pass
        return

    try:
        app._analyze()
    except Exception:
        pass
    plan = getattr(app, "current_plan", None)
    info = band_arranger.plan_info(plan)
    if (
        plan is None
        or info is None
        or info.part != current_part
        or info.stats.selected_notes <= 0
        or int(getattr(plan, "note_count", 0)) <= 0
    ):
        label = {
            "keyboard": "Piano",
            "guitar": "Guitar",
            "bass": "Bass",
            "drums": "Drums",
        }.get(current_part, current_part)
        try:
            app._band_room_status_var.set(
                f"Cannot Ready: this MIDI has no usable {label} part in the current Band lineup"
            )
        except tk.TclError:
            pass
        return

    if current_part == "drums" and (
        int(getattr(plan, "octave_switches", 0))
        or any(event.kind == "state" for event in getattr(plan, "events", ()))
    ):
        try:
            app._band_room_status_var.set(
                "Cannot Ready: Drum plan unexpectedly requested High/Low Octave"
            )
        except tk.TclError:
            pass
        return

    _original_toggle_ready(app)


def install_band_runtime_hardening(app_module: Any) -> None:
    """Install timing/dedup/Ready guards after Band UI and lineup hooks."""
    global _original_player_run, _original_schedule_synchronized_playback, _original_toggle_ready
    if getattr(app_module, "_band_runtime_hardening_installed", False):
        return

    _original_player_run = player_module.MidiPlayer._run
    player_module.MidiPlayer._run = _deadline_preserving_player_run

    _original_schedule_synchronized_playback = band_ui._schedule_synchronized_playback
    _original_toggle_ready = band_ui._toggle_ready
    band_ui._schedule_synchronized_playback = _hardened_schedule_synchronized_playback
    band_ui._toggle_ready = _hardened_toggle_ready
    band_ui._current_midi_hash = _safe_current_midi_hash
    band_ui._current_app_version = _band_compatibility_version

    app_class = app_module.App
    original_instrument_changed = app_class._instrument_changed
    original_start = app_class._start

    def instrument_changed(self: Any) -> None:
        previous_part = (
            band_ui._band_part(self)
            if hasattr(self, "_band_role_var")
            else "keyboard"
        )
        original_instrument_changed(self)
        enabled_var = getattr(self, "_band_enabled_var", None)
        try:
            enabled = bool(enabled_var.get()) if enabled_var is not None else False
        except tk.TclError:
            enabled = False
        if enabled:
            instrument = str(self._instrument_code())
            active_parts = band_arranger._active_parts_from_app(self)
            if instrument not in active_parts and previous_part in {"keyboard", "guitar", "bass"}:
                restore_label = {
                    "keyboard": "Keyboard",
                    "guitar": "Guitar",
                    "bass": "Bass",
                }[previous_part]
                try:
                    self.instrument_var.set(restore_label)
                    original_instrument_changed(self)
                except (tk.TclError, AttributeError):
                    pass
        _sync_part_after_manual_instrument_change(self)

    def start(self: Any) -> None:
        if not _prepare_local_band_practice(self):
            return
        original_start(self)

    app_class._instrument_changed = instrument_changed
    app_class._start = start
    app_module._band_runtime_hardening_installed = True
