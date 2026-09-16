from __future__ import annotations

import hashlib
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


def test_host_credentials_are_only_added_to_outbound_state(monkeypatch) -> None:
    code = "ABCDEFGHJKLM"
    token = "a" * 64
    band_cloudflare.register_host_token(code, token)
    transport = band_cloudflare.CloudflareBandTransport(code, lambda _: None)
    transport._socket = object()
    transport._connected.set()
    sent = []
    monkeypatch.setattr(band_cloudflare, "_send_ws_frame", lambda sock, data, **kwargs: sent.append(json.loads(data)))
    payload = {"proto": 2, "event": "state", "player_id": "HOST", "host": True}
    transport.publish(payload)
    assert sent == [{**payload, "host_token": token}]
    assert transport._latest_state == payload
    assert "host_token" not in payload


def test_websocket_reader_preserves_frame_coalesced_with_handshake() -> None:
    class EmptySocket:
        def recv(self, count):
            raise AssertionError("Buffered bytes should be read before touching the socket")

    sock = band_cloudflare._BufferedSocket(EmptySocket(), b"\x81\x02OK")
    opcode, fin, payload = band_cloudflare._receive_ws_frame(sock)
    assert (opcode, fin, payload) == (1, True, b"OK")


def test_cloud_upload_passes_credential_without_exposing_it_in_result(tmp_path, monkeypatch) -> None:
    code = "ABCDEFGHJKLM"
    secret = "b" * 64
    band_cloudflare.register_host_token(code, secret)
    midi = tmp_path / "song.mid"
    data = b"MThd\x00\x00\x00\x06"
    midi.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    base = f"https://bpsr-midi-band.zudinonline.workers.dev/api/rooms/{code}"
    token = "c" * 64

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, count):
            return json.dumps({
                "url": f"{base}/midi/{token}", "size": len(data),
                "midi_sha256": digest, "expires": 123,
            }).encode()

    def fake_urlopen(request, timeout):
        assert request.get_header("X-band-host-token") == secret
        return Response()

    monkeypatch.setattr(band_cloudflare.urllib.request, "urlopen", fake_urlopen)
    result = band_cloudflare._cloud_upload_midi_attachment(midi, base_url=base)
    assert result["midi_sha256"] == digest
    assert "host_token" not in result


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


def test_worker_uses_durable_object_websockets_and_sqlite_midi_chunks() -> None:
    source = Path("cloudflare-band/src/index.js").read_text(encoding="utf-8")
    for text in (
        "extends DurableObject",
        "acceptWebSocket",
        "webSocketMessage",
        "MIDI_CHUNK_BYTES",
        "ctx.storage.put(`midi:${token}:${index}`",
        "ctx.storage.get(`midi:${token}:${index}`",
        'ctx.storage.put("midi_meta"',
        'midi_storage: "durable-object-sqlite"',
        'event === "state"',
        '"start", "midi_share", "midi_share_revoke"',
        "!attachment.host || playerId !== this.hostId",
        "payload.host_token === this.hostToken",
        'request.headers.get("x-band-host-token")',
        "this.uploadInProgress",
        'url.pathname === "/health"',
    ):
        assert text in source
    assert "MIDI_BUCKET" not in source
    assert "r2" not in source.lower()


def test_wrangler_config_uses_only_sqlite_durable_object() -> None:
    config = json.loads(Path("cloudflare-band/wrangler.jsonc").read_text(encoding="utf-8"))
    assert config["name"] == "bpsr-midi-band"
    assert config["durable_objects"]["bindings"][0] == {
        "name": "BAND_ROOMS",
        "class_name": "BandRoom",
    }
    assert config["migrations"][0]["new_sqlite_classes"] == ["BandRoom"]
    assert "r2_buckets" not in config
