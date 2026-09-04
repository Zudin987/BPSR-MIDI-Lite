from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import secrets
import threading
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from tkinter import ttk
from typing import Any

import band_arranger
import band_lineup
import band_sync
import band_ui


SHARE_PROTOCOL_VERSION = 1
MAX_SHARED_MIDI_BYTES = 8 * 1024 * 1024
_DOWNLOAD_TIMEOUT_SECONDS = 20.0
_UPLOAD_TIMEOUT_SECONDS = 20.0
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._ ()\-\[\]]+")

_original_connect_room: Any = None
_original_local_state_payload: Any = None
_original_handle_band_message: Any = None
_original_refresh_room_ui: Any = None


def _selected_midi_path(app: Any) -> Path | None:
    file_var = getattr(app, "file_var", None)
    if file_var is None:
        return None
    try:
        text = str(file_var.get()).strip()
    except tk.TclError:
        return None
    if not text:
        return None
    path = Path(text)
    try:
        if not path.is_file():
            return None
    except OSError:
        return None
    return path


def _midi_name(app: Any) -> str:
    path = _selected_midi_path(app)
    return path.name if path is not None else ""


def sanitize_midi_filename(name: str) -> str:
    raw = Path(str(name)).name.strip()
    cleaned = _SAFE_FILENAME_RE.sub("_", raw).strip(" .")
    if not cleaned:
        cleaned = "room-song.mid"
    suffix = Path(cleaned).suffix.lower()
    if suffix not in {".mid", ".midi"}:
        cleaned = f"{Path(cleaned).stem or 'room-song'}.mid"
    return cleaned[:120]


def _validate_local_midi(path: Path) -> tuple[int, str]:
    size = path.stat().st_size
    if size <= 0:
        raise ValueError("MIDI file is empty")
    if size > MAX_SHARED_MIDI_BYTES:
        raise ValueError(
            f"MIDI is too large to share in Band Mode ({size / 1024 / 1024:.1f} MB; "
            f"limit {MAX_SHARED_MIDI_BYTES / 1024 / 1024:.0f} MB)"
        )
    with path.open("rb") as handle:
        if handle.read(4) != b"MThd":
            raise ValueError("Selected file is not a standard MIDI file")
    return size, band_sync.midi_sha256(path)


def _attachment_topic() -> str:
    return f"bpsr-band-file-{secrets.token_hex(16)}"


def _base_host(base_url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(base_url)
    return parsed.scheme.lower(), parsed.netloc.lower()


def _validate_attachment_url(url: str, base_url: str) -> str:
    parsed = urllib.parse.urlparse(str(url))
    base_scheme, base_host = _base_host(base_url)
    if parsed.scheme.lower() != base_scheme or parsed.netloc.lower() != base_host:
        raise ValueError("Room MIDI attachment is not hosted by the configured Band relay")
    if not parsed.path.startswith("/file/"):
        raise ValueError("Room MIDI attachment URL is invalid")
    return parsed.geturl()


def upload_midi_attachment(
    path: str | Path,
    *,
    base_url: str = band_sync.DEFAULT_NTFY_BASE_URL,
    timeout: float = _UPLOAD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    midi_path = Path(path)
    size, digest = _validate_local_midi(midi_path)
    filename = sanitize_midi_filename(midi_path.name)
    data = midi_path.read_bytes()
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/{_attachment_topic()}",
        data=data,
        method="PUT",
        headers={
            "Filename": filename,
            "Content-Type": "application/octet-stream",
            "Firebase": "no",
            "User-Agent": f"BPSR-MIDI-Lite-Band-Share/{SHARE_PROTOCOL_VERSION}",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(64 * 1024)
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OSError("Band relay returned an invalid attachment response") from exc
    attachment = envelope.get("attachment")
    if not isinstance(attachment, dict):
        raise OSError("Band relay did not return an attachment URL")
    url = _validate_attachment_url(str(attachment.get("url", "")), base_url)
    remote_size = int(attachment.get("size", size) or size)
    if remote_size != size:
        raise OSError("Band relay attachment size does not match the uploaded MIDI")
    return {
        "url": url,
        "filename": filename,
        "size": size,
        "expires": int(attachment.get("expires", 0) or 0),
        "midi_sha256": digest,
    }


def make_midi_share_payload(
    *,
    room_code: str,
    player_id: str,
    midi_hash: str,
    attachment: dict[str, Any],
) -> dict[str, Any]:
    return {
        "proto": band_sync.BAND_PROTOCOL_VERSION,
        "share_proto": SHARE_PROTOCOL_VERSION,
        "event": "midi_share",
        "room": band_sync.normalize_room_code(room_code),
        "player_id": str(player_id),
        "midi_sha256": str(midi_hash),
        "filename": sanitize_midi_filename(str(attachment.get("filename", "room-song.mid"))),
        "size": int(attachment.get("size", 0)),
        "expires": int(attachment.get("expires", 0) or 0),
        "url": str(attachment.get("url", "")),
    }


def validate_midi_share_payload(
    payload: dict[str, Any],
    *,
    room_code: str,
    base_url: str = band_sync.DEFAULT_NTFY_BASE_URL,
) -> dict[str, Any]:
    if int(payload.get("proto", 0)) != band_sync.BAND_PROTOCOL_VERSION:
        raise ValueError("Band protocol mismatch")
    if int(payload.get("share_proto", 0)) != SHARE_PROTOCOL_VERSION:
        raise ValueError("Room MIDI share protocol mismatch")
    if str(payload.get("event", "")) != "midi_share":
        raise ValueError("Not a Room MIDI share message")
    if str(payload.get("room", "")) != band_sync.normalize_room_code(room_code):
        raise ValueError("Room MIDI share belongs to another room")
    digest = str(payload.get("midi_sha256", "")).lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("Room MIDI hash is invalid")
    size = int(payload.get("size", 0))
    if size <= 0 or size > MAX_SHARED_MIDI_BYTES:
        raise ValueError("Room MIDI size is invalid")
    filename = sanitize_midi_filename(str(payload.get("filename", "room-song.mid")))
    url = _validate_attachment_url(str(payload.get("url", "")), base_url)
    return {
        "proto": band_sync.BAND_PROTOCOL_VERSION,
        "share_proto": SHARE_PROTOCOL_VERSION,
        "event": "midi_share",
        "room": band_sync.normalize_room_code(room_code),
        "player_id": str(payload.get("player_id", "")),
        "midi_sha256": digest,
        "filename": filename,
        "size": size,
        "expires": int(payload.get("expires", 0) or 0),
        "url": url,
    }


def band_cache_dir(root: str | Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "BPSR MIDI Lite" / "Band Cache"
    return Path.home() / ".bpsr-midi-lite" / "Band Cache"


def cache_path_for_share(
    filename: str,
    midi_hash: str,
    *,
    root: str | Path | None = None,
) -> Path:
    safe = sanitize_midi_filename(filename)
    path = Path(safe)
    stem = path.stem[:80] or "room-song"
    suffix = path.suffix.lower() if path.suffix.lower() in {".mid", ".midi"} else ".mid"
    return band_cache_dir(root) / f"{stem}-{midi_hash[:8]}{suffix}"


def download_shared_midi(
    payload: dict[str, Any],
    *,
    room_code: str,
    base_url: str = band_sync.DEFAULT_NTFY_BASE_URL,
    cache_root: str | Path | None = None,
    timeout: float = _DOWNLOAD_TIMEOUT_SECONDS,
) -> Path:
    share = validate_midi_share_payload(payload, room_code=room_code, base_url=base_url)
    request = urllib.request.Request(
        share["url"],
        method="GET",
        headers={"User-Agent": f"BPSR-MIDI-Lite-Band-Share/{SHARE_PROTOCOL_VERSION}"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read(MAX_SHARED_MIDI_BYTES + 1)
    if len(data) > MAX_SHARED_MIDI_BYTES:
        raise OSError("Downloaded Room MIDI exceeded the Band Mode size limit")
    if len(data) != int(share["size"]):
        raise OSError("Downloaded Room MIDI size does not match the host")
    if data[:4] != b"MThd":
        raise OSError("Downloaded Room file is not a standard MIDI")
    digest = hashlib.sha256(data).hexdigest()
    if digest != share["midi_sha256"]:
        raise OSError("Downloaded Room MIDI failed SHA-256 verification")

    destination = cache_path_for_share(
        share["filename"],
        share["midi_sha256"],
        root=cache_root,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(destination)
    return destination


def _share_allowed(app: Any) -> bool:
    variable = getattr(app, "_band_share_allowed_var", None)
    try:
        return bool(variable.get()) if variable is not None else False
    except tk.TclError:
        return False


def _local_state_payload(app: Any) -> dict[str, Any] | None:
    assert _original_local_state_payload is not None
    payload = _original_local_state_payload(app)
    if payload is None and getattr(app, "_band_connected", False):
        room = str(app._band_room_code_var.get()).strip()
        if not room:
            return None
        payload = band_sync.make_state_payload(
            room_code=room,
            player_id=app._band_player_id,
            name=app._band_name_var.get(),
            role=band_ui._band_part(app),
            active_parts=band_lineup.active_parts(app),
            ready=False,
            midi_hash=band_ui._current_midi_hash(app),
            app_version=band_ui._current_app_version(app),
            speed_percent=int(app.speed_var.get()),
            clock_sample=getattr(app, "_band_clock_sample", None),
            host=bool(app._band_is_host),
        )
    if payload is not None:
        payload["midi_name"] = _midi_name(app)
        payload["midi_share_allowed"] = bool(
            getattr(app, "_band_is_host", False) and _share_allowed(app)
        )
    return payload


def _connect_room(app: Any, *, host: bool) -> None:
    assert _original_connect_room is not None
    if host or band_ui._current_midi_hash(app):
        _original_connect_room(app, host=host)
        _refresh_share_ui(app)
        return

    if not bool(app._band_enabled_var.get()):
        app._band_room_status_var.set("Enable Band Mode first")
        return
    parts = band_lineup.active_parts(app)
    if band_ui._band_part(app) not in parts:
        band_lineup._refresh_role_values(app)
    try:
        code = band_sync.normalize_room_code(app._band_room_code_var.get())
    except ValueError as exc:
        app._band_room_status_var.set(str(exc))
        return

    band_ui._disconnect_room(app, announce=False)
    app._band_is_host = False
    app._band_connected = True
    app._band_ready = False
    app._band_roster = band_sync.BandRoster()
    app._band_room_status_var.set("Connecting… waiting for the host MIDI")
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
    band_lineup._set_lineup_control_state(app)
    band_ui._publish_state(app)
    band_ui._sync_clock_async(app)
    _refresh_share_ui(app)


def _share_needs_upload(app: Any) -> bool:
    if not (
        getattr(app, "_band_connected", False)
        and getattr(app, "_band_is_host", False)
        and _share_allowed(app)
    ):
        return False
    host_hash = band_ui._current_midi_hash(app)
    if not host_hash:
        return False
    for player_id, state in app._band_roster.players.items():
        if player_id == app._band_player_id:
            continue
        if state.midi_sha256 != host_hash:
            return True
    return False


def _ensure_share_uploaded_async(app: Any, *, force_announce: bool = False) -> None:
    if not _share_needs_upload(app):
        return
    path = _selected_midi_path(app)
    if path is None:
        return
    midi_hash = band_ui._current_midi_hash(app)
    existing = getattr(app, "_band_share_payload", None)
    if isinstance(existing, dict) and existing.get("midi_sha256") == midi_hash:
        if force_announce:
            transport = getattr(app, "_band_transport", None)
            if transport is not None:
                transport.publish_async(existing)
        return
    if bool(getattr(app, "_band_share_uploading", False)):
        return

    app._band_share_uploading = True
    app._band_share_status_var.set(f"Sharing {path.name}…")
    base_url = getattr(getattr(app, "_band_transport", None), "base_url", band_sync.DEFAULT_NTFY_BASE_URL)

    def worker() -> None:
        try:
            attachment = upload_midi_attachment(path, base_url=base_url)
            if attachment["midi_sha256"] != midi_hash:
                raise OSError("Selected MIDI changed while it was being shared")
            payload = make_midi_share_payload(
                room_code=app._band_room_code_var.get(),
                player_id=app._band_player_id,
                midi_hash=midi_hash,
                attachment=attachment,
            )
            app._band_share_queue.put(("uploaded", payload))
        except Exception as exc:  # noqa: BLE001
            app._band_share_queue.put(("upload_error", str(exc)))

    threading.Thread(target=worker, daemon=True).start()


def _start_download_async(app: Any, payload: dict[str, Any]) -> None:
    expected_hash = str(payload.get("midi_sha256", ""))
    if band_ui._current_midi_hash(app) == expected_hash:
        app._band_share_status_var.set("Room MIDI: exact match ✓")
        return
    if str(getattr(app, "_band_share_downloading_hash", "")) == expected_hash:
        return

    transport = getattr(app, "_band_transport", None)
    base_url = getattr(transport, "base_url", band_sync.DEFAULT_NTFY_BASE_URL)
    try:
        share = validate_midi_share_payload(
            payload,
            room_code=app._band_room_code_var.get(),
            base_url=base_url,
        )
    except ValueError as exc:
        app._band_share_status_var.set(f"Room MIDI offer rejected: {exc}")
        return

    app._band_share_payload_received = share
    host_id = band_ui._host_player_id(app)
    sender = str(share.get("player_id", ""))
    if host_id is not None and sender != host_id:
        app._band_share_status_var.set("Ignored a Room MIDI offer that did not come from the host")
        return
    if host_id is None:
        app._band_pending_share_payload = share
        app._band_share_status_var.set("Room MIDI offer received; waiting to verify the host")
        return

    app._band_share_downloading_hash = expected_hash
    app._band_share_status_var.set(f"Downloading room MIDI: {share['filename']}…")

    def worker() -> None:
        try:
            path = download_shared_midi(
                share,
                room_code=app._band_room_code_var.get(),
                base_url=base_url,
            )
            app._band_share_queue.put(("downloaded", (share, path)))
        except Exception as exc:  # noqa: BLE001
            app._band_share_queue.put(("download_error", str(exc)))

    threading.Thread(target=worker, daemon=True).start()


def _handle_band_message(app: Any, payload: dict[str, Any]) -> None:
    assert _original_handle_band_message is not None
    event = str(payload.get("event", ""))
    if event == "midi_share":
        _start_download_async(app, payload)
        return
    if event == "midi_share_revoke":
        host_id = band_ui._host_player_id(app)
        sender = str(payload.get("player_id", ""))
        if host_id is None or sender == host_id:
            app._band_share_payload_received = None
            app._band_pending_share_payload = None
            app._band_share_downloading_hash = ""
            app._band_share_status_var.set("Host disabled Room MIDI sharing")
            _refresh_share_ui(app)
        return

    _original_handle_band_message(app, payload)

    if event != "state":
        return

    player_id = str(payload.get("player_id", ""))
    if bool(payload.get("host", False)) and player_id != app._band_player_id:
        name = str(payload.get("midi_name", "")).strip()
        if name:
            app._band_room_song_var.set(f"Room song: {name}")
        host_hash = str(payload.get("midi_sha256", ""))
        local_hash = band_ui._current_midi_hash(app)
        current_offer = getattr(app, "_band_share_payload_received", None)
        if isinstance(current_offer, dict) and current_offer.get("midi_sha256") != host_hash:
            app._band_share_payload_received = None
            app._band_pending_share_payload = None
        if not bool(payload.get("midi_share_allowed", False)):
            app._band_share_payload_received = None
            app._band_pending_share_payload = None
        if host_hash and local_hash == host_hash:
            app._band_share_status_var.set("Room MIDI: exact match ✓")
        elif bool(payload.get("midi_share_allowed", False)):
            app._band_share_status_var.set("Room MIDI differs — waiting for host download link…")
        else:
            app._band_share_status_var.set(
                "Room MIDI differs — host has MIDI sharing disabled"
            )
        pending = getattr(app, "_band_pending_share_payload", None)
        if isinstance(pending, dict):
            app._band_pending_share_payload = None
            _start_download_async(app, pending)

    if getattr(app, "_band_is_host", False) and player_id != app._band_player_id:
        host_hash = band_ui._current_midi_hash(app)
        guest_hash = str(payload.get("midi_sha256", ""))
        if host_hash and guest_hash != host_hash:
            _ensure_share_uploaded_async(app, force_announce=True)


def _download_last_offer(app: Any) -> None:
    payload = getattr(app, "_band_share_payload_received", None)
    if not isinstance(payload, dict):
        payload = getattr(app, "_band_pending_share_payload", None)
    if not isinstance(payload, dict):
        app._band_share_status_var.set("No Room MIDI download is available yet")
        return
    _start_download_async(app, payload)


def _toggle_share_allowed(app: Any) -> None:
    if getattr(app, "_band_connected", False) and not getattr(app, "_band_is_host", False):
        app._band_share_allowed_var.set(False)
        app._band_share_status_var.set("Only the room host can share the Room MIDI")
        return
    if _share_allowed(app):
        app._band_share_status_var.set(
            "MIDI sharing enabled — upload happens only if a room member needs the file"
        )
        if getattr(app, "_band_connected", False):
            band_ui._publish_state(app)
            _ensure_share_uploaded_async(app, force_announce=True)
    else:
        app._band_share_payload = None
        app._band_share_hash = ""
        app._band_share_status_var.set(
            "MIDI sharing disabled (an already uploaded temporary file may remain until relay expiry)"
        )
        if getattr(app, "_band_connected", False):
            transport = getattr(app, "_band_transport", None)
            if transport is not None and getattr(app, "_band_is_host", False):
                transport.publish_async(
                    {
                        "proto": band_sync.BAND_PROTOCOL_VERSION,
                        "event": "midi_share_revoke",
                        "room": band_sync.normalize_room_code(app._band_room_code_var.get()),
                        "player_id": app._band_player_id,
                    }
                )
            band_ui._publish_state(app)
    _refresh_share_ui(app)


def _refresh_share_ui(app: Any) -> None:
    try:
        connected = bool(getattr(app, "_band_connected", False))
        host = bool(getattr(app, "_band_is_host", False))
        app._band_share_checkbox.configure(state="normal" if not connected or host else "disabled")
        offer = getattr(app, "_band_share_payload_received", None)
        local_matches = False
        if isinstance(offer, dict):
            local_matches = band_ui._current_midi_hash(app) == str(offer.get("midi_sha256", ""))
        app._band_download_button.configure(
            state="normal"
            if connected and not host and isinstance(offer, dict) and not local_matches
            else "disabled"
        )
        if host:
            name = _midi_name(app)
            app._band_room_song_var.set(f"Room song: {name or 'choose a MIDI'}")
    except (AttributeError, tk.TclError):
        pass


def _refresh_room_ui(app: Any) -> None:
    assert _original_refresh_room_ui is not None
    _original_refresh_room_ui(app)
    _refresh_share_ui(app)


def _drain_share_events(app: Any) -> None:
    try:
        while True:
            kind, payload = app._band_share_queue.get_nowait()
            if kind == "uploaded" and isinstance(payload, dict):
                app._band_share_uploading = False
                app._band_share_payload = payload
                app._band_share_hash = str(payload.get("midi_sha256", ""))
                transport = getattr(app, "_band_transport", None)
                if transport is not None and _share_allowed(app):
                    transport.publish_async(payload)
                app._band_share_status_var.set(
                    f"Room MIDI ready to download: {payload.get('filename', 'MIDI')} "
                    "(temporary relay attachment)"
                )
            elif kind == "upload_error":
                app._band_share_uploading = False
                app._band_share_status_var.set(f"Could not share Room MIDI: {payload}")
            elif kind == "downloaded" and isinstance(payload, tuple) and len(payload) == 2:
                share, path = payload
                app._band_share_downloading_hash = ""
                app._band_share_payload_received = share
                try:
                    app.file_var.set(str(path))
                except tk.TclError:
                    pass
                app._band_hash_cache_key = None
                app._band_hash_cache_value = ""
                app._band_ready = False
                try:
                    app._band_ready_button.configure(text="Ready")
                except (AttributeError, tk.TclError):
                    pass
                app._band_room_song_var.set(f"Room song: {share.get('filename', path.name)}")
                app._band_share_status_var.set(
                    f"Room MIDI downloaded + SHA-256 verified ✓ · {path}"
                )
                try:
                    app._schedule_analysis(20)
                    app.after(100, lambda: band_ui._publish_state(app))
                except (AttributeError, tk.TclError):
                    pass
            elif kind == "download_error":
                app._band_share_downloading_hash = ""
                app._band_share_status_var.set(f"Room MIDI download failed: {payload}")
        _refresh_share_ui(app)
    except queue.Empty:
        pass
    try:
        app.after(100, lambda: _drain_share_events(app))
    except tk.TclError:
        pass


def _build_share_controls(app: Any) -> None:
    frame = getattr(app, "_band_frame", None)
    if frame is None or hasattr(app, "_band_share_allowed_var"):
        return

    app._band_share_allowed_var = tk.BooleanVar(master=app, value=True)
    app._band_room_song_var = tk.StringVar(
        master=app,
        value=f"Room song: {_midi_name(app) or 'not selected'}",
    )
    app._band_share_status_var = tk.StringVar(
        master=app,
        value="Host sharing is enabled; upload happens only if another player needs the MIDI.",
    )
    app._band_share_payload = None
    app._band_share_payload_received = None
    app._band_pending_share_payload = None
    app._band_share_hash = ""
    app._band_share_uploading = False
    app._band_share_downloading_hash = ""
    app._band_share_queue = queue.Queue()

    share_frame = ttk.LabelFrame(frame, text="Room MIDI", padding=(7, 5))
    share_frame.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(7, 0))
    share_frame.columnconfigure(0, weight=1)
    app._band_share_frame = share_frame

    ttk.Label(
        share_frame,
        textvariable=app._band_room_song_var,
        style="Gaming.Micro.TLabel",
    ).grid(row=0, column=0, sticky="w")
    app._band_share_checkbox = ttk.Checkbutton(
        share_frame,
        text="Allow room members to download this MIDI",
        variable=app._band_share_allowed_var,
        command=lambda: _toggle_share_allowed(app),
    )
    app._band_share_checkbox.grid(row=0, column=1, sticky="e", padx=(10, 0))
    app._band_download_button = ttk.Button(
        share_frame,
        text="Download Room MIDI",
        command=lambda: _download_last_offer(app),
        state="disabled",
    )
    app._band_download_button.grid(row=0, column=2, sticky="e", padx=(6, 0))
    ttk.Label(
        share_frame,
        textvariable=app._band_share_status_var,
        style="Hint.TLabel",
        wraplength=690,
        justify="left",
    ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 0))

    app.after(100, lambda: _drain_share_events(app))
    _refresh_share_ui(app)


def install_band_midi_sharing(app_module: Any) -> None:
    """Add lazy host-to-room MIDI sharing on top of Band Mode."""
    global _original_connect_room
    global _original_local_state_payload
    global _original_handle_band_message
    global _original_refresh_room_ui

    if getattr(app_module, "_band_midi_sharing_installed", False):
        return
    if not getattr(app_module, "_band_runtime_hardening_installed", False):
        raise RuntimeError("Band runtime hardening must be installed before MIDI sharing.")

    _original_connect_room = band_ui._connect_room
    _original_local_state_payload = band_ui._local_state_payload
    _original_handle_band_message = band_ui._handle_band_message
    _original_refresh_room_ui = band_ui._refresh_room_ui

    band_ui._connect_room = _connect_room
    band_ui._local_state_payload = _local_state_payload
    band_ui._handle_band_message = _handle_band_message
    band_ui._refresh_room_ui = _refresh_room_ui

    app_class = app_module.App
    original_build = app_class._build_ui
    original_analyze = app_class._analyze

    def build_ui(self: Any) -> None:
        original_build(self)
        _build_share_controls(self)

    def analyze(self: Any) -> None:
        previous_hash = str(getattr(self, "_band_share_hash_seen", ""))
        original_analyze(self)
        if not hasattr(self, "_band_share_allowed_var"):
            return
        current_hash = band_ui._current_midi_hash(self)
        if previous_hash and current_hash != previous_hash:
            self._band_share_payload = None
            self._band_share_hash = ""
            self._band_share_payload_received = None
            self._band_share_downloading_hash = ""
            if getattr(self, "_band_is_host", False):
                self._band_room_song_var.set(f"Room song: {_midi_name(self) or 'choose a MIDI'}")
                if _share_needs_upload(self):
                    _ensure_share_uploaded_async(self)
        self._band_share_hash_seen = current_hash
        _refresh_share_ui(self)

    app_class._build_ui = build_ui
    app_class._analyze = analyze
    app_module._band_midi_sharing_installed = True
