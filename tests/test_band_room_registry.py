from __future__ import annotations

from pathlib import Path

import band_room_registry


def test_room_registry_urls_use_cloudflare_service() -> None:
    code = "ABCDEFGHJKLM"
    assert band_room_registry._room_endpoint(code, "create") == (
        "https://bpsr-midi-band.zudinonline.workers.dev/api/rooms/ABCDEFGHJKLM/create"
    )
    assert band_room_registry._room_endpoint(code, "exists") == (
        "https://bpsr-midi-band.zudinonline.workers.dev/api/rooms/ABCDEFGHJKLM/exists"
    )


def test_launchers_install_room_registry_after_cloudflare_transport() -> None:
    for filename in ("modern_launcher.py", "studio_launcher.py"):
        source = Path(filename).read_text(encoding="utf-8")
        assert "install_band_room_registry" in source
        assert source.index("install_cloudflare_band_transport(app)") < source.index(
            "install_band_room_registry(app)"
        )


def test_worker_requires_explicit_room_creation() -> None:
    source = Path("cloudflare-band/src/index.js").read_text(encoding="utf-8")
    for text in (
        'tail === "create"',
        'tail === "exists"',
        'url.pathname === "/room-create"',
        'url.pathname === "/room-exists"',
        'ctx.storage.put("created_at"',
        'json({ exists: false }, 404)',
        'new Response("Room not found", { status: 404 })',
    ):
        assert text in source
