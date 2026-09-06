from __future__ import annotations

from email.message import Message
from pathlib import Path
import threading
import time
import urllib.error

import band_network_hardening as network


def test_band_network_uses_low_traffic_keepalive_budget() -> None:
    assert network.HEARTBEAT_MS >= 30_000
    assert network.PLAYER_STALE_SECONDS >= (network.HEARTBEAT_MS / 1000.0) * 2.5
    assert network.STATE_MIN_INTERVAL_SECONDS >= 2.0


def test_retry_after_header_is_respected() -> None:
    headers = Message()
    headers["Retry-After"] = "7"
    exc = urllib.error.HTTPError("https://ntfy.sh/x", 429, "Too Many Requests", headers, None)
    assert network._retry_after_seconds(exc, 0) == 7.0


def test_identical_state_publish_is_collapsed() -> None:
    class FakeTransport:
        def __init__(self) -> None:
            self.stop_event = threading.Event()
            self.on_status = None
            self.calls: list[dict[str, object]] = []

        def publish(self, payload, timeout=5.0):
            self.calls.append(dict(payload))

    transport = FakeTransport()
    payload = {"event": "state", "room": "ABCDEFGHJKLM", "ready": True}
    network._hardened_publish_async(transport, payload)
    deadline = time.monotonic() + 1.0
    while not transport.calls and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(transport.calls) == 1

    network._hardened_publish_async(transport, payload)
    time.sleep(0.05)
    assert len(transport.calls) == 1
    transport.stop_event.set()


def test_launchers_install_network_hardening_after_midi_sharing() -> None:
    for path in ("modern_launcher.py", "studio_launcher.py"):
        source = Path(path).read_text(encoding="utf-8")
        assert "install_band_network_hardening(app)" in source
        assert source.index("install_band_midi_sharing(app)") < source.index(
            "install_band_network_hardening(app)"
        )


def test_start_gate_explains_disabled_start() -> None:
    source = Path("band_network_hardening.py").read_text(encoding="utf-8")
    assert "Start blocked:" in source
    assert "Need" in Path("band_sync.py").read_text(encoding="utf-8")
    assert "Missing player for" in Path("band_sync.py").read_text(encoding="utf-8")
