from __future__ import annotations

import json
from pathlib import Path

import band_cloudflare


def test_cloudflare_endpoint_and_room_websocket_url() -> None:
    assert band_cloudflare.DEFAULT_CLOUDFLARE_BAND_URL == (
        "https://bpsr-midi-band.zudinonline.workers.dev"
    )
    url = band_cloudflare._ws_url_for_room(
        band_cloudflare.DEFAULT_CLOUDFLARE_BAND_URL,
        "ABCDEFGHJKLM",
    )
    assert url == "wss://bpsr-midi-band.zudinonline.workers.dev/api/rooms/ABCDEFGHJKLM/ws"


def test_cloudflare_attachment_validation_is_same_service_and_room() -> None:
    base = "https://bpsr-midi-band.zudinonline.workers.dev/api/rooms/ABCDEFGHJKLM"
    token = "a" * 64
    url = f"{base}/midi/{token}"
    assert band_cloudflare._cloud_attachment_url(url, base) == url

    for bad in (
        f"https://evil.example/api/rooms/ABCDEFGHJKLM/midi/{token}",
        f"https://bpsr-midi-band.zudinonline.workers.dev/api/rooms/ZZZZZZZZZZZZ/midi/{token}",
        f"{base}/midi/not-a-token",
    ):
        try:
            band_cloudflare._cloud_attachment_url(bad, base)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unexpectedly accepted {bad}")


def test_launchers_install_cloudflare_after_existing_band_layers() -> None:
    for filename in ("modern_launcher.py", "studio_launcher.py"):
        source = Path(filename).read_text(encoding="utf-8")
        assert "install_cloudflare_band_transport" in source
        assert source.index("install_band_midi_sharing(app)") < source.index(
            "install_cloudflare_band_transport(app)"
        )
        assert source.index("install_band_network_hardening(app)") < source.index(
            "install_cloudflare_band_transport(app)"
        )


def test_worker_uses_durable_object_websockets_and_private_r2() -> None:
    source = Path("cloudflare-band/src/index.js").read_text(encoding="utf-8")
    for text in (
        "extends DurableObject",
        "acceptWebSocket",
        "webSocketMessage",
        "MIDI_BUCKET.put",
        "MIDI_BUCKET.get",
        "MIDI_BUCKET.delete",
        'event === "state"',
        '"start", "midi_share", "midi_share_revoke"',
        "playerId !== this.hostId",
        'url.pathname === "/health"',
    ):
        assert text in source


def test_wrangler_config_uses_sqlite_do_and_expected_r2_bucket() -> None:
    config = json.loads(Path("cloudflare-band/wrangler.jsonc").read_text(encoding="utf-8"))
    assert config["name"] == "bpsr-midi-band"
    assert config["durable_objects"]["bindings"][0] == {
        "name": "BAND_ROOMS",
        "class_name": "BandRoom",
    }
    assert config["migrations"][0]["new_sqlite_classes"] == ["BandRoom"]
    assert config["r2_buckets"][0] == {
        "binding": "MIDI_BUCKET",
        "bucket_name": "bpsr-midi-band-midi",
    }
