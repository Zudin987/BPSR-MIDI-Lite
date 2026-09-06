from __future__ import annotations

import json
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime
from tkinter import ttk
from typing import Any

import band_lineup
import band_sync
import band_ui


# ntfy's anonymous public relay refills its per-IP request bucket at roughly one
# request every 5 seconds. Keep steady-state Band traffic comfortably below
# that even when several clients share one public IP/NAT.
HEARTBEAT_MS = 30_000
PLAYER_STALE_SECONDS = 90.0
STATE_MIN_INTERVAL_SECONDS = 2.0
RATE_LIMIT_FALLBACK_SECONDS = 15.0
RATE_LIMIT_MAX_SECONDS = 90.0
SUBSCRIBE_RETRY_SECONDS = 3.0

_original_roster_prune: Any = None
_original_build_ui: Any = None
_original_refresh_room_ui: Any = None


def _ensure_transport_state(transport: Any) -> None:
    if hasattr(transport, "_band_publish_lock"):
        return
    transport._band_publish_lock = threading.Lock()
    transport._band_state_pending = None
    transport._band_state_worker = None
    transport._band_last_state_sent_at = 0.0
    transport._band_last_state_signature = ""
    transport._band_rate_limit_until = 0.0
    transport._band_rate_limit_strikes = 0


def _state_signature(payload: dict[str, Any]) -> str:
    try:
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError):
        return repr(sorted(payload.items()))


def _retry_after_seconds(exc: urllib.error.HTTPError, strikes: int) -> float:
    retry_after = None
    try:
        retry_after = exc.headers.get("Retry-After") if exc.headers is not None else None
    except Exception:
        retry_after = None
    if retry_after:
        text = str(retry_after).strip()
        try:
            return min(RATE_LIMIT_MAX_SECONDS, max(1.0, float(text)))
        except ValueError:
            try:
                target = parsedate_to_datetime(text).timestamp()
                return min(RATE_LIMIT_MAX_SECONDS, max(1.0, target - time.time()))
            except Exception:
                pass
    exponential = RATE_LIMIT_FALLBACK_SECONDS * (2 ** max(0, min(int(strikes), 3)))
    return min(RATE_LIMIT_MAX_SECONDS, exponential)


def _mark_rate_limited(transport: Any, exc: urllib.error.HTTPError) -> float:
    _ensure_transport_state(transport)
    with transport._band_publish_lock:
        transport._band_rate_limit_strikes = int(transport._band_rate_limit_strikes) + 1
        delay = _retry_after_seconds(exc, transport._band_rate_limit_strikes - 1)
        transport._band_rate_limit_until = max(
            float(transport._band_rate_limit_until), time.monotonic() + delay
        )
    if transport.on_status is not None and not transport.stop_event.is_set():
        transport.on_status(
            f"Band relay rate-limited (HTTP 429) — backing off for {delay:.0f}s; room will recover automatically"
        )
    return delay


def _mark_publish_success(transport: Any) -> None:
    _ensure_transport_state(transport)
    with transport._band_publish_lock:
        transport._band_rate_limit_strikes = 0
        transport._band_rate_limit_until = 0.0


def _wait_for_rate_limit(transport: Any) -> bool:
    _ensure_transport_state(transport)
    while not transport.stop_event.is_set():
        with transport._band_publish_lock:
            delay = max(0.0, float(transport._band_rate_limit_until) - time.monotonic())
        if delay <= 0.0:
            return True
        if transport.stop_event.wait(min(delay, 1.0)):
            return False
    return False


def _state_publish_worker(transport: Any) -> None:
    while not transport.stop_event.is_set():
        with transport._band_publish_lock:
            payload = transport._band_state_pending
            transport._band_state_pending = None
            earliest = float(transport._band_last_state_sent_at) + STATE_MIN_INTERVAL_SECONDS
            wait_for = max(
                0.0,
                earliest - time.monotonic(),
                float(transport._band_rate_limit_until) - time.monotonic(),
            )
        if payload is None:
            break
        if wait_for > 0.0 and transport.stop_event.wait(wait_for):
            break

        signature = _state_signature(payload)
        try:
            transport.publish(payload)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                _mark_rate_limited(transport, exc)
                with transport._band_publish_lock:
                    # Keep only the newest state. A later state change supersedes
                    # this heartbeat while the relay cools down.
                    if transport._band_state_pending is None:
                        transport._band_state_pending = payload
                continue
            if transport.on_status is not None and not transport.stop_event.is_set():
                transport.on_status(f"Band network error: {exc}")
            break
        except (OSError, urllib.error.URLError) as exc:
            if transport.on_status is not None and not transport.stop_event.is_set():
                transport.on_status(f"Band network error: {exc}")
            break
        else:
            now = time.monotonic()
            with transport._band_publish_lock:
                transport._band_last_state_sent_at = now
                transport._band_last_state_signature = signature
            _mark_publish_success(transport)

    with transport._band_publish_lock:
        transport._band_state_worker = None
        pending = transport._band_state_pending
    if pending is not None and not transport.stop_event.is_set():
        _hardened_publish_async(transport, pending)


def _hardened_publish_async(transport: Any, payload: dict[str, Any]) -> None:
    _ensure_transport_state(transport)
    event = str(payload.get("event", ""))

    if event == "state":
        signature = _state_signature(payload)
        now = time.monotonic()
        with transport._band_publish_lock:
            # Collapse duplicate UI-triggered publishes. A real changed state is
            # still sent immediately (subject only to the tiny 2s coalesce gap).
            if (
                signature == transport._band_last_state_signature
                and now - float(transport._band_last_state_sent_at) < HEARTBEAT_MS / 1000.0 * 0.8
            ):
                return
            transport._band_state_pending = dict(payload)
            worker = transport._band_state_worker
            if worker is not None and worker.is_alive():
                return
            worker = threading.Thread(
                target=_state_publish_worker,
                args=(transport,),
                daemon=True,
            )
            transport._band_state_worker = worker
            worker.start()
        return

    def worker() -> None:
        if not _wait_for_rate_limit(transport):
            return
        attempts = band_sync.START_PUBLISH_ATTEMPTS if event == "start" else 1
        for attempt in range(attempts):
            if transport.stop_event.is_set() and event != "leave":
                return
            try:
                transport.publish(payload)
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    _mark_rate_limited(transport, exc)
                    return
                if transport.on_status is not None and not transport.stop_event.is_set():
                    transport.on_status(f"Band network error: {exc}")
                return
            except (OSError, urllib.error.URLError) as exc:
                if transport.on_status is not None and not transport.stop_event.is_set():
                    transport.on_status(f"Band network error: {exc}")
                return
            else:
                _mark_publish_success(transport)
            if attempt + 1 < attempts:
                if transport.stop_event.wait(band_sync.START_PUBLISH_GAP_SECONDS):
                    return

    threading.Thread(target=worker, daemon=True).start()


def _hardened_subscribe_loop(transport: Any) -> None:
    _ensure_transport_state(transport)
    while not transport.stop_event.is_set():
        if not _wait_for_rate_limit(transport):
            return
        request = urllib.request.Request(
            f"{transport.base_url}/{transport.topic}/json",
            method="GET",
            headers={
                "Accept": "application/x-ndjson",
                "User-Agent": f"BPSR-MIDI-Lite-Band/{band_sync.BAND_PROTOCOL_VERSION}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=75.0) as response:
                _mark_publish_success(transport)
                if transport.on_status is not None:
                    transport.on_status("Band room connected")
                for raw_line in response:
                    if transport.stop_event.is_set():
                        return
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        envelope = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if envelope.get("event") != "message":
                        continue
                    try:
                        payload = json.loads(str(envelope.get("message", "")))
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    if payload.get("room") != transport.room_code:
                        continue
                    try:
                        transport.on_message(payload)
                    except Exception:
                        continue
        except urllib.error.HTTPError as exc:
            if transport.stop_event.is_set():
                return
            if exc.code == 429:
                _mark_rate_limited(transport, exc)
                continue
            if transport.on_status is not None:
                transport.on_status(f"Band room reconnecting: {exc}")
            transport.stop_event.wait(SUBSCRIBE_RETRY_SECONDS)
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            if transport.stop_event.is_set():
                return
            if transport.on_status is not None:
                transport.on_status(f"Band room reconnecting: {exc}")
            transport.stop_event.wait(SUBSCRIBE_RETRY_SECONDS)


def _hardened_roster_prune(
    roster: Any,
    *,
    now: float | None = None,
    max_age: float | None = None,
) -> None:
    assert _original_roster_prune is not None
    _original_roster_prune(
        roster,
        now=now,
        max_age=PLAYER_STALE_SECONDS if max_age is None else float(max_age),
    )


def _start_gate_text(app: Any) -> str:
    if not getattr(app, "_band_connected", False):
        return "Start: create or join a room first"
    if not getattr(app, "_band_is_host", False):
        return "Start: waiting for room host"
    try:
        issues = app._band_roster.compatibility_issues(
            expected_hash=band_ui._current_midi_hash(app),
            expected_version=band_ui._current_app_version(app),
            expected_speed=int(app.speed_var.get()),
            expected_active_parts=band_lineup.active_parts(app),
        )
    except Exception:
        return "Start: checking room…"
    if not issues:
        return "Start: READY ✓"
    return "Start blocked: " + " · ".join(issues[:2])


def _refresh_room_ui(app: Any) -> None:
    assert _original_refresh_room_ui is not None
    _original_refresh_room_ui(app)
    try:
        app._band_start_gate_var.set(_start_gate_text(app))
    except (AttributeError, tk.TclError):
        pass


def _build_start_gate(app: Any) -> None:
    lineup = getattr(app, "_band_lineup_frame", None)
    if lineup is None or hasattr(app, "_band_start_gate_var"):
        return
    app._band_start_gate_var = tk.StringVar(master=app, value="Start: create or join a room first")
    ttk.Label(
        lineup,
        textvariable=app._band_start_gate_var,
        style="Gaming.Micro.TLabel",
        wraplength=690,
        justify="left",
    ).grid(row=2, column=0, columnspan=4, sticky="ew", pady=(5, 0))


def install_band_network_hardening(app_module: Any) -> None:
    """Lower ntfy traffic, recover safely from HTTP 429, and explain Start gating."""
    global _original_roster_prune, _original_build_ui, _original_refresh_room_ui
    if getattr(app_module, "_band_network_hardening_installed", False):
        return
    if not getattr(app_module, "_band_midi_sharing_installed", False):
        raise RuntimeError("Band MIDI sharing must be installed before network hardening.")

    band_ui._HEARTBEAT_MS = HEARTBEAT_MS

    _original_roster_prune = band_sync.BandRoster.prune
    band_sync.BandRoster.prune = _hardened_roster_prune
    band_sync.NtfyBandTransport.publish_async = _hardened_publish_async
    band_sync.NtfyBandTransport._subscribe_loop = _hardened_subscribe_loop

    _original_refresh_room_ui = band_ui._refresh_room_ui
    band_ui._refresh_room_ui = _refresh_room_ui

    app_class = app_module.App
    _original_build_ui = app_class._build_ui

    def build_ui(self: Any) -> None:
        _original_build_ui(self)
        _build_start_gate(self)
        _refresh_room_ui(self)

    app_class._build_ui = build_ui
    app_module._band_network_hardening_installed = True
