from __future__ import annotations

import base64
import hashlib
import json
import os
import queue
import secrets
import socket
import ssl
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

import band_arranger
import band_lineup
import band_share
import band_sync
import band_ui


DEFAULT_CLOUDFLARE_BAND_URL = "https://bpsr-midi-band.zudinonline.workers.dev"
_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_CONNECT_TIMEOUT_SECONDS = 10.0
_RECONNECT_MIN_SECONDS = 1.0
_RECONNECT_MAX_SECONDS = 15.0
_SOCKET_IDLE_SECONDS = 35.0

_original_start_band: Any = None
_original_validate_attachment_url: Any = None
_original_upload_midi_attachment: Any = None


def service_origin() -> str:
    return os.environ.get("BPSR_BAND_SERVICE_URL", DEFAULT_CLOUDFLARE_BAND_URL).strip().rstrip("/")


def _origin_parts(url: str) -> tuple[str, str, int]:
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("Invalid Band service URL")
    port = parsed.port or (443 if scheme == "https" else 80)
    return scheme, parsed.hostname, port


def _ws_url_for_room(origin: str, room_code: str) -> str:
    parsed = urllib.parse.urlparse(origin)
    scheme = "wss" if parsed.scheme.lower() == "https" else "ws"
    code = band_sync.normalize_room_code(room_code)
    return urllib.parse.urlunparse((scheme, parsed.netloc, f"/api/rooms/{code}/ws", "", "", ""))


def _read_exact(sock: socket.socket, count: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < count:
        chunk = sock.recv(count - len(chunks))
        if not chunk:
            raise OSError("Band WebSocket closed")
        chunks.extend(chunk)
    return bytes(chunks)


def _send_ws_frame(sock: socket.socket, payload: bytes, *, opcode: int = 0x1) -> None:
    first = 0x80 | (opcode & 0x0F)
    length = len(payload)
    mask = secrets.token_bytes(4)
    if length < 126:
        header = struct.pack("!BB", first, 0x80 | length)
    elif length <= 0xFFFF:
        header = struct.pack("!BBH", first, 0x80 | 126, length)
    else:
        header = struct.pack("!BBQ", first, 0x80 | 127, length)
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    sock.sendall(header + mask + masked)


def _receive_ws_frame(sock: socket.socket) -> tuple[int, bool, bytes]:
    first, second = _read_exact(sock, 2)
    fin = bool(first & 0x80)
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", _read_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _read_exact(sock, 8))[0]
    if length > 16 * 1024 * 1024:
        raise OSError("Band WebSocket frame is unexpectedly large")
    mask = _read_exact(sock, 4) if masked else b""
    payload = _read_exact(sock, int(length)) if length else b""
    if masked:
        payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return opcode, fin, payload


def _open_websocket(url: str, *, timeout: float = _CONNECT_TIMEOUT_SECONDS) -> socket.socket:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
        raise ValueError("Invalid Band WebSocket URL")
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    raw = socket.create_connection((parsed.hostname, port), timeout=timeout)
    if parsed.scheme == "wss":
        context = ssl.create_default_context()
        sock: socket.socket = context.wrap_socket(raw, server_hostname=parsed.hostname)
    else:
        sock = raw
    sock.settimeout(timeout)

    key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    default_port = 443 if parsed.scheme == "wss" else 80
    host_header = parsed.hostname if port == default_port else f"{parsed.hostname}:{port}"
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host_header}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        f"User-Agent: BPSR-MIDI-Lite-Band/{band_sync.BAND_PROTOCOL_VERSION}\r\n"
        "\r\n"
    ).encode("ascii")
    sock.sendall(request)

    response = bytearray()
    while b"\r\n\r\n" not in response:
        chunk = sock.recv(4096)
        if not chunk:
            sock.close()
            raise OSError("Band service closed during WebSocket handshake")
        response.extend(chunk)
        if len(response) > 64 * 1024:
            sock.close()
            raise OSError("Band service returned an oversized handshake")
    header_blob, remainder = bytes(response).split(b"\r\n\r\n", 1)
    lines = header_blob.decode("iso-8859-1", errors="replace").split("\r\n")
    if not lines or " 101 " not in f" {lines[0]} ":
        sock.close()
        raise OSError(f"Band WebSocket handshake failed: {lines[0] if lines else 'no response'}")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
    expected = base64.b64encode(hashlib.sha1((key + _WS_GUID).encode("ascii")).digest()).decode("ascii")
    if headers.get("sec-websocket-accept") != expected:
        sock.close()
        raise OSError("Band WebSocket handshake verification failed")
    if remainder:
        # Cloudflare should not send application bytes before the 101 headers finish.
        sock.close()
        raise OSError("Unexpected bytes after Band WebSocket handshake")
    sock.settimeout(_SOCKET_IDLE_SECONDS)
    return sock


class CloudflareBandTransport:
    """Persistent Cloudflare WebSocket room transport with no polling/request-rate pressure."""

    def __init__(
        self,
        room_code: str,
        on_message: Callable[[dict[str, Any]], None],
        *,
        base_url: str | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        self.room_code = band_sync.normalize_room_code(room_code)
        self.origin = (base_url or service_origin()).rstrip("/")
        self.base_url = f"{self.origin}/api/rooms/{self.room_code}"
        self.ws_url = _ws_url_for_room(self.origin, self.room_code)
        self.on_message = on_message
        self.on_status = on_status
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self._socket: socket.socket | None = None
        self._socket_lock = threading.RLock()
        self._latest_state: dict[str, Any] | None = None
        self._connected = threading.Event()

    @property
    def is_running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set() and self._socket is not None

    def _status(self, text: str) -> None:
        if self.on_status is not None and not self.stop_event.is_set():
            try:
                self.on_status(text)
            except Exception:
                pass

    def start(self) -> None:
        if self.is_running:
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self._connected.clear()
        with self._socket_lock:
            sock = self._socket
            self._socket = None
            if sock is not None:
                try:
                    _send_ws_frame(sock, b"", opcode=0x8)
                except Exception:
                    pass
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    sock.close()
                except OSError:
                    pass

    def publish(self, payload: dict[str, Any]) -> None:
        if payload.get("event") == "state":
            self._latest_state = dict(payload)
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        with self._socket_lock:
            sock = self._socket
            if sock is None or not self._connected.is_set():
                raise OSError("Cloud Band room is reconnecting")
            _send_ws_frame(sock, body, opcode=0x1)

    def publish_async(self, payload: dict[str, Any]) -> None:
        if payload.get("event") == "state":
            self._latest_state = dict(payload)
        try:
            self.publish(payload)
        except OSError as exc:
            # State is replayed automatically after reconnect. Other events are deliberately
            # not queued because a stale Start/Leave/share command is worse than a clear retry.
            if payload.get("event") != "state":
                self._status(f"Cloud Band send failed: {exc}")

    def _set_socket(self, sock: socket.socket | None) -> None:
        with self._socket_lock:
            old = self._socket
            self._socket = sock
            if sock is None:
                self._connected.clear()
            else:
                self._connected.set()
            if old is not None and old is not sock:
                try:
                    old.close()
                except OSError:
                    pass

    def _send_latest_state(self) -> None:
        if self._latest_state is None:
            return
        try:
            self.publish(self._latest_state)
        except OSError:
            pass

    def _run(self) -> None:
        delay = _RECONNECT_MIN_SECONDS
        while not self.stop_event.is_set():
            try:
                self._status("Cloud Band: connecting…")
                sock = _open_websocket(self.ws_url)
                self._set_socket(sock)
                self._status("Cloud Band: connected ✓")
                delay = _RECONNECT_MIN_SECONDS
                self._send_latest_state()
                self._receive_loop(sock)
            except Exception as exc:  # noqa: BLE001
                if not self.stop_event.is_set():
                    self._status(f"Cloud Band: reconnecting ({exc})")
            finally:
                self._set_socket(None)
            if self.stop_event.wait(delay):
                return
            delay = min(_RECONNECT_MAX_SECONDS, delay * 1.7)

    def _receive_loop(self, sock: socket.socket) -> None:
        fragments = bytearray()
        fragment_opcode: int | None = None
        while not self.stop_event.is_set():
            try:
                opcode, fin, payload = _receive_ws_frame(sock)
            except socket.timeout:
                with self._socket_lock:
                    if self._socket is not sock:
                        return
                    _send_ws_frame(sock, b"bpsr", opcode=0x9)
                continue
            if opcode == 0x8:
                raise OSError("Cloud Band server closed the room socket")
            if opcode == 0x9:
                with self._socket_lock:
                    _send_ws_frame(sock, payload, opcode=0xA)
                continue
            if opcode == 0xA:
                continue
            if opcode in {0x1, 0x2}:
                fragments = bytearray(payload)
                fragment_opcode = opcode
            elif opcode == 0x0 and fragment_opcode is not None:
                fragments.extend(payload)
            else:
                continue
            if not fin:
                continue
            if fragment_opcode != 0x1:
                fragments.clear()
                fragment_opcode = None
                continue
            text = bytes(fragments).decode("utf-8", errors="replace")
            fragments.clear()
            fragment_opcode = None
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            if message.get("event") == "error":
                self._status(f"Cloud Band: {message.get('message', 'server rejected a command')}")
                continue
            try:
                self.on_message(message)
            except Exception:
                continue


def _cloud_attachment_url(url: str, base_url: str) -> str:
    parsed = urllib.parse.urlparse(str(url))
    base = urllib.parse.urlparse(str(base_url))
    if parsed.scheme.lower() != base.scheme.lower() or parsed.netloc.lower() != base.netloc.lower():
        raise ValueError("Room MIDI attachment is not hosted by the configured Cloud Band service")
    base_path = base.path.rstrip("/")
    if not parsed.path.startswith(base_path + "/midi/"):
        raise ValueError("Room MIDI attachment URL is invalid")
    token = parsed.path.rsplit("/", 1)[-1]
    if len(token) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in token):
        raise ValueError("Room MIDI attachment token is invalid")
    return parsed.geturl()


def _cloud_upload_midi_attachment(
    path: str | Path,
    *,
    base_url: str = DEFAULT_CLOUDFLARE_BAND_URL,
    timeout: float = 20.0,
) -> dict[str, Any]:
    midi_path = Path(path)
    size, digest = band_share._validate_local_midi(midi_path)
    filename = band_share.sanitize_midi_filename(midi_path.name)
    data = midi_path.read_bytes()
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/midi",
        data=data,
        method="PUT",
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Length": str(size),
            "X-Midi-Filename": filename,
            "X-Midi-Sha256": digest,
            "User-Agent": f"BPSR-MIDI-Lite-Cloud-Band/{band_sync.BAND_PROTOCOL_VERSION}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(64 * 1024)
    except urllib.error.HTTPError as exc:
        raise OSError(f"Cloud Band MIDI upload failed: HTTP {exc.code}") from exc
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OSError("Cloud Band returned an invalid MIDI upload response") from exc
    if not isinstance(result, dict):
        raise OSError("Cloud Band returned an invalid MIDI upload response")
    url = _cloud_attachment_url(str(result.get("url", "")), base_url)
    remote_size = int(result.get("size", 0) or 0)
    remote_hash = str(result.get("midi_sha256", "")).lower()
    if remote_size != size or remote_hash != digest:
        raise OSError("Cloud Band MIDI upload metadata does not match the local file")
    return {
        "url": url,
        "filename": filename,
        "size": size,
        "expires": int(result.get("expires", 0) or 0),
        "midi_sha256": digest,
    }


def _cloud_start_band(app: Any) -> None:
    assert _original_start_band is not None
    transport = getattr(app, "_band_transport", None)
    if isinstance(transport, CloudflareBandTransport) and not transport.is_connected:
        try:
            app._band_room_status_var.set("Cannot start: Cloud Band room is reconnecting")
        except Exception:
            pass
        return
    _original_start_band(app)


def _cloud_start_gate_text(app: Any) -> str | None:
    transport = getattr(app, "_band_transport", None)
    if isinstance(transport, CloudflareBandTransport) and getattr(app, "_band_connected", False):
        if not transport.is_connected:
            return "Start blocked: Cloud Band room is reconnecting"
    return None


def install_cloudflare_band_transport(app_module: Any) -> None:
    """Switch Band Mode from the public ntfy relay to the project's Cloudflare backend."""
    global _original_start_band, _original_validate_attachment_url, _original_upload_midi_attachment
    if getattr(app_module, "_cloudflare_band_transport_installed", False):
        return
    if not getattr(app_module, "_band_midi_sharing_installed", False):
        raise RuntimeError("Band MIDI sharing must be installed before Cloudflare Band transport.")

    _original_start_band = band_ui._start_band
    _original_validate_attachment_url = band_share._validate_attachment_url
    _original_upload_midi_attachment = band_share.upload_midi_attachment

    band_sync.NtfyBandTransport = CloudflareBandTransport
    band_share._validate_attachment_url = _cloud_attachment_url
    band_share.upload_midi_attachment = _cloud_upload_midi_attachment
    band_ui._start_band = _cloud_start_band

    # Add Cloud connection state to the existing explicit Start-gate text without
    # removing its lineup/hash/version diagnostics.
    try:
        import band_network_hardening

        original_gate = band_network_hardening._start_gate_text

        def gate_text(app: Any) -> str:
            cloud = _cloud_start_gate_text(app)
            return cloud if cloud is not None else original_gate(app)

        band_network_hardening._start_gate_text = gate_text
    except Exception:
        pass

    app_module._cloudflare_band_transport_installed = True
