from __future__ import annotations

import threading
import tkinter as tk
import urllib.error
import urllib.request
from typing import Any

import band_cloudflare
import band_sync
import band_ui


_ROOM_LOOKUP_TIMEOUT_SECONDS = 6.0
_CREATE_COLLISION_RETRIES = 3
_original_connect_room: Any = None


def _room_endpoint(room_code: str, action: str) -> str:
    code = band_sync.normalize_room_code(room_code)
    if action not in {"create", "exists"}:
        raise ValueError("Invalid room registry action")
    return f"{band_cloudflare.service_origin()}/api/rooms/{code}/{action}"


def _request_room_create(room_code: str) -> str:
    code = band_sync.normalize_room_code(room_code)
    request = urllib.request.Request(
        _room_endpoint(code, "create"),
        data=b"",
        method="POST",
        headers={"User-Agent": f"BPSR-MIDI-Lite-Band/{band_sync.BAND_PROTOCOL_VERSION}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_ROOM_LOOKUP_TIMEOUT_SECONDS) as response:
            response.read(4096)
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            raise FileExistsError("Band room code already exists") from exc
        raise OSError(f"Cloud Band room creation failed: HTTP {exc.code}") from exc
    return code


def _request_room_exists(room_code: str) -> bool:
    code = band_sync.normalize_room_code(room_code)
    request = urllib.request.Request(
        _room_endpoint(code, "exists"),
        method="GET",
        headers={"User-Agent": f"BPSR-MIDI-Lite-Band/{band_sync.BAND_PROTOCOL_VERSION}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_ROOM_LOOKUP_TIMEOUT_SECONDS) as response:
            response.read(4096)
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise OSError(f"Cloud Band room lookup failed: HTTP {exc.code}") from exc


def _finish_lookup(app: Any) -> None:
    app._band_room_lookup_running = False


def _connect_room(app: Any, *, host: bool) -> None:
    assert _original_connect_room is not None
    if bool(getattr(app, "_band_room_lookup_running", False)):
        try:
            app._band_room_status_var.set("Cloud Band: room check already in progress…")
        except tk.TclError:
            pass
        return

    try:
        original_code = band_sync.normalize_room_code(app._band_room_code_var.get())
    except ValueError as exc:
        try:
            app._band_room_status_var.set(str(exc))
        except tk.TclError:
            pass
        return

    app._band_room_lookup_running = True
    try:
        app._band_room_status_var.set(
            "Cloud Band: creating room…" if host else "Cloud Band: checking room code…"
        )
    except tk.TclError:
        pass

    def worker() -> None:
        selected_code = original_code
        try:
            if host:
                for attempt in range(_CREATE_COLLISION_RETRIES):
                    try:
                        selected_code = _request_room_create(selected_code)
                        break
                    except FileExistsError:
                        if attempt + 1 >= _CREATE_COLLISION_RETRIES:
                            raise
                        selected_code = band_sync.generate_room_code()
            else:
                if not _request_room_exists(selected_code):
                    def not_found() -> None:
                        _finish_lookup(app)
                        try:
                            app._band_room_status_var.set(
                                "Room not found — check the room code or ask the host to create it again"
                            )
                        except tk.TclError:
                            pass
                    try:
                        app.after(0, not_found)
                    except tk.TclError:
                        pass
                    return

            def connect() -> None:
                _finish_lookup(app)
                try:
                    if str(app._band_room_code_var.get()) != selected_code:
                        app._band_room_code_var.set(selected_code)
                    _original_connect_room(app, host=host)
                except tk.TclError:
                    return

            try:
                app.after(0, connect)
            except tk.TclError:
                pass
        except (OSError, FileExistsError, ValueError) as exc:
            def failed() -> None:
                _finish_lookup(app)
                try:
                    app._band_room_status_var.set(f"Cloud Band: {exc}")
                except tk.TclError:
                    pass
            try:
                app.after(0, failed)
            except tk.TclError:
                pass

    threading.Thread(target=worker, daemon=True).start()


def install_band_room_registry(app_module: Any) -> None:
    """Require explicit room creation and reject nonexistent/expired room codes."""
    global _original_connect_room
    if getattr(app_module, "_band_room_registry_installed", False):
        return
    if not getattr(app_module, "_cloudflare_band_transport_installed", False):
        raise RuntimeError("Cloudflare Band transport must be installed before room registry checks.")

    _original_connect_room = band_ui._connect_room
    band_ui._connect_room = _connect_room
    app_module._band_room_registry_installed = True
