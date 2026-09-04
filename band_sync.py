from __future__ import annotations

import hashlib
import json
import secrets
import socket
import struct
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


BAND_PROTOCOL_VERSION = 1
DEFAULT_NTFY_BASE_URL = "https://ntfy.sh"
ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ROOM_CODE_LENGTH = 12
PLAYER_STALE_SECONDS = 25.0
START_LEAD_SECONDS = 6.0
START_PUBLISH_ATTEMPTS = 3
START_PUBLISH_GAP_SECONDS = 0.18
_NTP_UNIX_DELTA = 2_208_988_800


@dataclass(frozen=True, slots=True)
class ClockSample:
    server: str
    offset_ms: float
    rtt_ms: float

    @property
    def synced(self) -> bool:
        return self.rtt_ms >= 0.0


@dataclass(slots=True)
class PlayerState:
    player_id: str
    name: str
    role: str
    ready: bool
    midi_sha256: str
    app_version: str
    speed_percent: int
    clock_synced: bool
    clock_rtt_ms: float
    host: bool
    last_seen: float


class BandRoster:
    def __init__(self) -> None:
        self.players: dict[str, PlayerState] = {}

    def apply(self, payload: dict[str, Any], *, now: float | None = None) -> None:
        if int(payload.get("proto", 0)) != BAND_PROTOCOL_VERSION:
            return
        event = str(payload.get("event", ""))
        player_id = str(payload.get("player_id", "")).strip()
        if not player_id:
            return
        if event == "leave":
            self.players.pop(player_id, None)
            return
        if event != "state":
            return
        timestamp = time.monotonic() if now is None else float(now)
        self.players[player_id] = PlayerState(
            player_id=player_id,
            name=str(payload.get("name", "Player"))[:32],
            role=str(payload.get("role", "keyboard")),
            ready=bool(payload.get("ready", False)),
            midi_sha256=str(payload.get("midi_sha256", "")),
            app_version=str(payload.get("app_version", "")),
            speed_percent=int(payload.get("speed_percent", 100)),
            clock_synced=bool(payload.get("clock_synced", False)),
            clock_rtt_ms=float(payload.get("clock_rtt_ms", -1.0)),
            host=bool(payload.get("host", False)),
            last_seen=timestamp,
        )

    def prune(self, *, now: float | None = None, max_age: float = PLAYER_STALE_SECONDS) -> None:
        timestamp = time.monotonic() if now is None else float(now)
        for player_id, state in tuple(self.players.items()):
            if timestamp - state.last_seen > max_age:
                self.players.pop(player_id, None)

    def compatibility_issues(
        self,
        *,
        expected_hash: str,
        expected_version: str,
        expected_speed: int,
        drums_supported: bool = False,
        minimum_players: int = 2,
        now: float | None = None,
    ) -> list[str]:
        self.prune(now=now)
        players = list(self.players.values())
        issues: list[str] = []
        if len(players) < minimum_players:
            issues.append(f"Need at least {minimum_players} players in the room")
            return issues
        if any(not player.ready for player in players):
            issues.append("Everyone must be Ready")
        if any(not player.clock_synced for player in players):
            issues.append("Every player needs a synchronized clock")
        if any(player.midi_sha256 != expected_hash for player in players):
            issues.append("MIDI files do not all match")
        if any(player.app_version != expected_version for player in players):
            issues.append("Everyone must use the same BPSR MIDI version")
        if any(player.speed_percent != expected_speed for player in players):
            issues.append("Song speed does not match between players")
        roles = [player.role for player in players]
        if len(set(roles)) != len(roles):
            issues.append("Two players selected the same band part")
        if not drums_supported and "drums" in roles:
            issues.append("BPSR drum mapping is not configured yet")
        return issues

    def compact_text(self, *, now: float | None = None) -> str:
        self.prune(now=now)
        if not self.players:
            return "No players connected"
        ordered = sorted(
            self.players.values(),
            key=lambda item: (not item.host, item.role, item.name.casefold()),
        )
        role_labels = {
            "keyboard": "Piano",
            "guitar": "Guitar",
            "bass": "Bass",
            "drums": "Drums",
        }
        bits = []
        for player in ordered[:4]:
            ready = "READY" if player.ready else "not ready"
            host = " • host" if player.host else ""
            bits.append(f"{player.name} · {role_labels.get(player.role, player.role)} · {ready}{host}")
        return "   |   ".join(bits)


def generate_room_code() -> str:
    return "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LENGTH))


def normalize_room_code(value: str) -> str:
    cleaned = "".join(ch for ch in str(value).upper() if ch in ROOM_CODE_ALPHABET)
    if len(cleaned) != ROOM_CODE_LENGTH:
        raise ValueError(f"Room code must be {ROOM_CODE_LENGTH} characters")
    return cleaned


def topic_for_room(room_code: str) -> str:
    code = normalize_room_code(room_code)
    return f"bpsr-band-{code.lower()}"


def midi_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def new_player_id() -> str:
    return secrets.token_hex(8)


def make_state_payload(
    *,
    room_code: str,
    player_id: str,
    name: str,
    role: str,
    ready: bool,
    midi_hash: str,
    app_version: str,
    speed_percent: int,
    clock_sample: ClockSample | None,
    host: bool,
) -> dict[str, Any]:
    return {
        "proto": BAND_PROTOCOL_VERSION,
        "event": "state",
        "room": normalize_room_code(room_code),
        "player_id": player_id,
        "name": str(name).strip()[:32] or "Player",
        "role": role,
        "ready": bool(ready),
        "midi_sha256": midi_hash,
        "app_version": app_version,
        "speed_percent": int(speed_percent),
        "clock_synced": clock_sample is not None,
        "clock_rtt_ms": round(clock_sample.rtt_ms, 2) if clock_sample else -1.0,
        "host": bool(host),
    }


def make_leave_payload(*, room_code: str, player_id: str) -> dict[str, Any]:
    return {
        "proto": BAND_PROTOCOL_VERSION,
        "event": "leave",
        "room": normalize_room_code(room_code),
        "player_id": player_id,
    }


def make_start_payload(
    *,
    room_code: str,
    player_id: str,
    start_utc_ms: int,
    midi_hash: str,
    app_version: str,
    speed_percent: int,
) -> dict[str, Any]:
    return {
        "proto": BAND_PROTOCOL_VERSION,
        "event": "start",
        "room": normalize_room_code(room_code),
        "player_id": player_id,
        "start_utc_ms": int(start_utc_ms),
        "midi_sha256": midi_hash,
        "app_version": app_version,
        "speed_percent": int(speed_percent),
    }


def corrected_utc_ms(sample: ClockSample | None) -> float:
    offset = sample.offset_ms if sample is not None else 0.0
    return time.time() * 1000.0 + offset


def delay_until_utc_ms(start_utc_ms: int, sample: ClockSample | None) -> float:
    return max(0.0, (float(start_utc_ms) - corrected_utc_ms(sample)) / 1000.0)


def _ntp_timestamp(seconds: int, fraction: int) -> float:
    return float(seconds) - _NTP_UNIX_DELTA + float(fraction) / 2**32


def query_ntp(server: str, *, timeout: float = 1.5) -> ClockSample:
    packet = b"\x1b" + 47 * b"\0"
    address = (server, 123)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        t1 = time.time()
        sock.sendto(packet, address)
        response, _peer = sock.recvfrom(512)
        t4 = time.time()
    if len(response) < 48:
        raise OSError("Short NTP response")
    words = struct.unpack("!12I", response[:48])
    t2 = _ntp_timestamp(words[8], words[9])
    t3 = _ntp_timestamp(words[10], words[11])
    offset = ((t2 - t1) + (t3 - t4)) / 2.0
    rtt = max(0.0, (t4 - t1) - (t3 - t2))
    return ClockSample(server=server, offset_ms=offset * 1000.0, rtt_ms=rtt * 1000.0)


def synchronize_clock(
    servers: tuple[str, ...] = ("time.cloudflare.com", "time.google.com", "pool.ntp.org"),
) -> ClockSample | None:
    samples: list[ClockSample] = []
    for server in servers:
        try:
            samples.append(query_ntp(server))
        except (OSError, socket.timeout, struct.error):
            continue
    if not samples:
        return None
    return min(samples, key=lambda item: item.rtt_ms)


class NtfyBandTransport:
    """Tiny zero-account room transport using ntfy's public HTTP stream API.

    Only control/state JSON is sent. MIDI/audio never leaves the player's PC.
    Messages use Cache:no and Firebase:no so room state is not deliberately
    retained or forwarded to mobile push infrastructure by ntfy.
    """

    def __init__(
        self,
        room_code: str,
        on_message: Callable[[dict[str, Any]], None],
        *,
        base_url: str = DEFAULT_NTFY_BASE_URL,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        self.room_code = normalize_room_code(room_code)
        self.topic = topic_for_room(self.room_code)
        self.base_url = base_url.rstrip("/")
        self.on_message = on_message
        self.on_status = on_status
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def start(self) -> None:
        if self.is_running:
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._subscribe_loop, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def publish(self, payload: dict[str, Any], *, timeout: float = 5.0) -> None:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/{self.topic}",
            data=body,
            method="POST",
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "Cache": "no",
                "Firebase": "no",
                "User-Agent": "BPSR-MIDI-Lite-Band/1",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read(4096)

    def publish_async(self, payload: dict[str, Any]) -> None:
        def worker() -> None:
            attempts = START_PUBLISH_ATTEMPTS if payload.get("event") == "start" else 1
            for attempt in range(attempts):
                if self.stop_event.is_set() and payload.get("event") != "leave":
                    return
                try:
                    self.publish(payload)
                except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
                    if self.on_status is not None and not self.stop_event.is_set():
                        self.on_status(f"Band network error: {exc}")
                if attempt + 1 < attempts:
                    time.sleep(START_PUBLISH_GAP_SECONDS)

        threading.Thread(target=worker, daemon=True).start()

    def _subscribe_loop(self) -> None:
        while not self.stop_event.is_set():
            request = urllib.request.Request(
                f"{self.base_url}/{self.topic}/json",
                method="GET",
                headers={
                    "Accept": "application/x-ndjson",
                    "User-Agent": "BPSR-MIDI-Lite-Band/1",
                },
            )
            try:
                if self.on_status is not None:
                    self.on_status("Band room connected")
                with urllib.request.urlopen(request, timeout=75.0) as response:
                    for raw_line in response:
                        if self.stop_event.is_set():
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
                        if payload.get("room") != self.room_code:
                            continue
                        try:
                            self.on_message(payload)
                        except Exception:
                            continue
            except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                if self.stop_event.is_set():
                    return
                if self.on_status is not None:
                    self.on_status(f"Band room reconnecting: {exc}")
                self.stop_event.wait(1.0)
