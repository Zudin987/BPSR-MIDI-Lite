"""One-time, exact-match migration for the September 2026 review branch.

This script is run by the branch-only workflow, then removed in its own commit.
Every replacement is checked before writing anything, preventing partial upgrades.
"""
from __future__ import annotations

from pathlib import Path

changes: dict[Path, str] = {}


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    source = changes.get(file, file.read_text(encoding="utf-8"))
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {path}, got {count}: {old[:90]!r}")
    changes[file] = source.replace(old, new, 1)


def section(path: str, start: str, end: str, new: str) -> None:
    file = Path(path)
    source = changes.get(file, file.read_text(encoding="utf-8"))
    if source.count(start) != 1 or source.count(end) != 1:
        raise RuntimeError(f"Cannot uniquely locate section {start!r} in {path}")
    a, b = source.index(start), source.index(end)
    if b <= a:
        raise RuntimeError(f"Section bounds out of order in {path}")
    changes[file] = source[:a] + new + source[b:]


worker = "cloudflare-band/src/index.js"
replace(worker, "const MIDI_CHUNK_BYTES = 1024 * 1024;", "const MIDI_CHUNK_BYTES = 1024 * 1024;\nconst MAX_CONTROL_CHARS = 64 * 1024;")
replace(worker, '  const token = token64();\n  const response = await roomStub(env, room).fetch', '  const hostToken = String(request.headers.get("x-band-host-token") || "");\n  if (!/^[0-9a-f]{64}$/.test(hostToken)) return json({ error: "host authorization required" }, 403);\n  const token = token64();\n  const response = await roomStub(env, room).fetch')
replace(worker, '      "x-midi-sha256": sha256,', '      "x-midi-sha256": sha256,\n      "x-band-host-token": hostToken,')
replace(worker, '    this.hostId = null;\n    this.midiMeta = null;', '    this.hostId = null;\n    this.hostToken = null;\n    this.uploadInProgress = false;\n    this.midiMeta = null;')
replace(worker, '      this.hostId = (await this.ctx.storage.get("host_id")) || null;', '      this.hostId = (await this.ctx.storage.get("host_id")) || null;\n      this.hostToken = (await this.ctx.storage.get("host_token")) || null;')
section(worker, '  async storeMidi(request, token) {', '  async loadMidi(token) {', '''  async storeMidi(request, token) {
    if (!this.createdAt) return json({ error: "room not found" }, 404);
    const hostToken = String(request.headers.get("x-band-host-token") || "");
    if (!this.hostToken || hostToken !== this.hostToken) {
      return json({ error: "host authorization required" }, 403);
    }
    const expectedSize = Number(request.headers.get("content-length") || "0");
    const expectedHash = String(request.headers.get("x-midi-sha256") || "").toLowerCase();
    const filename = safeFilename(request.headers.get("x-midi-filename"));
    if (!/^[0-9a-f]{64}$/i.test(token)) return json({ error: "invalid token" }, 400);
    if (!Number.isFinite(expectedSize) || expectedSize <= 0 || expectedSize > MAX_MIDI_BYTES) {
      return json({ error: "invalid MIDI size" }, 413);
    }
    if (!/^[0-9a-f]{64}$/.test(expectedHash)) return json({ error: "invalid MIDI hash" }, 400);
    // Serialize uploads for one room: old metadata must survive a failed replacement.
    if (this.uploadInProgress) return json({ error: "another MIDI upload is in progress" }, 409);
    this.uploadInProgress = true;
    try {
      const data = await request.arrayBuffer();
      if (data.byteLength !== expectedSize) return json({ error: "MIDI size changed during upload" }, 400);
      const bytes = new Uint8Array(data);
      if (bytes.length < 4 || bytes[0] !== 0x4d || bytes[1] !== 0x54 || bytes[2] !== 0x68 || bytes[3] !== 0x64) {
        return json({ error: "not a standard MIDI file" }, 400);
      }
      const digestBuffer = await crypto.subtle.digest("SHA-256", data);
      const digest = Array.from(new Uint8Array(digestBuffer))
        .map((value) => value.toString(16).padStart(2, "0")).join("");
      if (digest !== expectedHash) return json({ error: "MIDI SHA-256 mismatch" }, 400);
      const previous = this.midiMeta;
      const chunks = Math.ceil(data.byteLength / MIDI_CHUNK_BYTES);
      const nextMeta = { token, filename, size: data.byteLength, sha256: digest,
        expires: Date.now() + MIDI_TTL_MS, chunks };
      let written = 0;
      try {
        for (let index = 0; index < chunks; index += 1) {
          const start = index * MIDI_CHUNK_BYTES;
          await this.ctx.storage.put(`midi:${token}:${index}`,
            data.slice(start, Math.min(data.byteLength, start + MIDI_CHUNK_BYTES)));
          written += 1;
        }
        // Commit the new metadata only when every chunk is safely stored.
        await this.ctx.storage.put("midi_meta", nextMeta);
      } catch (error) {
        for (let index = 0; index < written; index += 1) {
          try { await this.ctx.storage.delete(`midi:${token}:${index}`); } catch (_) {}
        }
        throw error;
      }
      this.midiMeta = nextMeta;
      // A failed deletion must never invalidate an already committed replacement.
      if (previous) {
        for (let index = 0; index < Math.min(16, Number(previous.chunks || 0)); index += 1) {
          try { await this.ctx.storage.delete(`midi:${previous.token}:${index}`); } catch (_) {}
        }
      }
      await this.touch();
      return json({ filename, size: data.byteLength, expires: nextMeta.expires, midi_sha256: digest });
    } finally {
      this.uploadInProgress = false;
    }
  }

''')
replace(worker, '''        this.createdAt = Date.now();
        await this.ctx.storage.put("created_at", this.createdAt);
        await this.touch();
        return json({ ok: true, created_at: this.createdAt });''', '''        const hostToken = token64();
        const createdAt = Date.now();
        await this.ctx.storage.put("host_token", hostToken);
        await this.ctx.storage.put("created_at", createdAt);
        this.hostToken = hostToken;
        this.createdAt = createdAt;
        await this.touch();
        return json({ ok: true, created_at: createdAt, host_token: hostToken });''')
section(worker, '  async webSocketMessage(ws, message) {', '  async webSocketClose(ws, code, reason) {', '''  async webSocketMessage(ws, message) {
    if (typeof message !== "string" || message.length > MAX_CONTROL_CHARS) return;
    let payload;
    try { payload = JSON.parse(message); } catch (_) { return; }
    if (!payload || typeof payload !== "object" || Array.isArray(payload)
        || Number(payload.proto) !== PROTOCOL_VERSION) return;
    const event = String(payload.event || "");
    const playerId = String(payload.player_id || "").slice(0, 64);
    if (!playerId) return;
    const attachment = ws.deserializeAttachment() || {};
    // Bind a player ID to the first state received on this exact socket.
    if (attachment.playerId && attachment.playerId !== playerId) return;
    if (event === "state") {
      const claimingHost = payload.host === true;
      const authorizedHost = claimingHost && !!this.hostToken
        && payload.host_token === this.hostToken;
      if (claimingHost && !authorizedHost) {
        try { ws.send(JSON.stringify({ proto: PROTOCOL_VERSION, event: "error",
          code: "host_auth", message: "Host credential invalid; recreate the room" })); } catch (_) {}
        return;
      }
      if (!authorizedHost && playerId === this.hostId) return;
      // Prevent another socket from stealing any participant's identity.
      for (const other of this.ctx.getWebSockets()) {
        if (other === ws) continue;
        const state = other.deserializeAttachment() || {};
        if (state.playerId !== playerId) continue;
        if (!authorizedHost || !state.host) return;
        // Credential-bearing host reconnects can replace a stale host socket.
        other.serializeAttachment({ playerId: "", state: null, host: false });
        try { other.close(1000, "Host reconnected"); } catch (_) {}
      }
      if (authorizedHost && this.hostId !== playerId) {
        this.hostId = playerId;
        await this.ctx.storage.put("host_id", playerId);
      }
      const { host_token: _secret, ...publicState } = payload;
      publicState.player_id = playerId;
      publicState.host = authorizedHost;
      ws.serializeAttachment({ playerId, state: publicState, host: authorizedHost });
      await this.touch();
      for (const state of this.existingStates(ws)) {
        try { ws.send(JSON.stringify(state)); } catch (_) {}
      }
      this.broadcast(publicState);
      return;
    }
    // Neither an unregistered socket nor a forged ID may perform an action.
    if (!attachment.playerId || attachment.playerId !== playerId) return;
    if (event === "leave") {
      this.broadcast(payload, ws);
      ws.serializeAttachment({ playerId: "", state: null, host: false });
      await this.touch();
      return;
    }
    if (["start", "midi_share", "midi_share_revoke"].includes(event)) {
      if (!attachment.host || playerId !== this.hostId) {
        try { ws.send(JSON.stringify({ proto: PROTOCOL_VERSION, event: "error",
          code: "host_only", message: "Only the authenticated host can send this event" })); } catch (_) {}
        return;
      }
      await this.touch();
      this.broadcast(payload);
    }
  }

''')
replace(worker, '    this.hostId = null;\n    this.midiMeta = null;\n    this.createdAt = null;\n  }\n}', '    this.hostId = null;\n    this.hostToken = null;\n    this.midiMeta = null;\n    this.createdAt = null;\n  }\n}')

registry = "band_room_registry.py"
replace(registry, 'import threading\n', 'import json\nimport threading\n')
replace(registry, 'def _request_room_create(room_code: str) -> str:', 'def _request_room_create(room_code: str) -> tuple[str, str]:')
replace(registry, '''        with urllib.request.urlopen(request, timeout=_ROOM_LOOKUP_TIMEOUT_SECONDS) as response:
            response.read(4096)
    except urllib.error.HTTPError as exc:
        if exc.code == 409:''', '''        with urllib.request.urlopen(request, timeout=_ROOM_LOOKUP_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read(4096).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise OSError("Cloud Band returned invalid room credentials") from exc
    except urllib.error.HTTPError as exc:
        if exc.code == 409:''')
replace(registry, '    return code\n\n\ndef _request_room_exists', '''    token = str(data.get("host_token", "")) if isinstance(data, dict) else ""
    if len(token) != 64 or any(char not in "0123456789abcdef" for char in token):
        raise OSError("Cloud Band did not return a valid host credential")
    return code, token


def _request_room_exists''')
replace(registry, '        selected_code = original_code\n        try:', '        selected_code = original_code\n        host_token = ""\n        try:')
replace(registry, '                        selected_code = _request_room_create(selected_code)', '                        selected_code, host_token = _request_room_create(selected_code)')
replace(registry, '                    _original_connect_room(app, host=host)', '''                    if host:
                        band_cloudflare.register_host_token(selected_code, host_token)
                    _original_connect_room(app, host=host)''')
replace(registry, '''        except (OSError, FileExistsError, ValueError) as exc:
            def failed() -> None:
                _finish_lookup(app)
                try:
                    app._band_room_status_var.set(f"Cloud Band: {exc}")''', '''        except (OSError, FileExistsError, ValueError) as exc:
            error_message = str(exc)
            def failed() -> None:
                _finish_lookup(app)
                try:
                    app._band_room_status_var.set(f"Cloud Band: {error_message}")''')

client = "band_cloudflare.py"
replace(client, '_original_start_band: Any = None', '''_HOST_TOKENS: dict[str, str] = {}


def register_host_token(room_code: str, token: str) -> None:
    code = band_sync.normalize_room_code(room_code)
    if len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
        raise ValueError("Invalid Cloud Band host credential")
    _HOST_TOKENS[code] = token


_original_start_band: Any = None''')
replace(client, 'def _open_websocket(url: str, *, timeout: float = _CONNECT_TIMEOUT_SECONDS) -> socket.socket:', '''class _BufferedSocket:
    """Retain a WebSocket frame coalesced with the HTTP 101 response."""

    def __init__(self, sock: socket.socket, buffered: bytes) -> None:
        self._sock = sock
        self._buffer = bytearray(buffered)

    def recv(self, size: int) -> bytes:
        if self._buffer:
            chunk = bytes(self._buffer[:size])
            del self._buffer[:size]
            return chunk
        return self._sock.recv(size)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._sock, name)


def _open_websocket(url: str, *, timeout: float = _CONNECT_TIMEOUT_SECONDS) -> socket.socket:''')
replace(client, '''    if remainder:
        # Cloudflare should not send application bytes before the 101 headers finish.
        sock.close()
        raise OSError("Unexpected bytes after Band WebSocket handshake")
    sock.settimeout(_SOCKET_IDLE_SECONDS)
    return sock''', '''    sock.settimeout(_SOCKET_IDLE_SECONDS)
    return _BufferedSocket(sock, remainder)''')
replace(client, '_SOCKET_IDLE_SECONDS = 35.0', '_SOCKET_IDLE_SECONDS = 35.0\n_MAX_WS_MESSAGE_BYTES = 256 * 1024')
replace(client, '''        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        with self._socket_lock:''', '''        outbound = dict(payload)
        if outbound.get("event") == "state" and outbound.get("host") is True:
            token = _HOST_TOKENS.get(self.room_code)
            if not token:
                raise OSError("Cloud Band host credential missing; recreate the room")
            outbound["host_token"] = token
        body = json.dumps(outbound, separators=(",", ":"), sort_keys=True).encode("utf-8")
        with self._socket_lock:''')
replace(client, '''            elif opcode == 0x0 and fragment_opcode is not None:
                fragments.extend(payload)
            else:
                continue
            if not fin:''', '''            elif opcode == 0x0 and fragment_opcode is not None:
                fragments.extend(payload)
            else:
                continue
            if len(fragments) > _MAX_WS_MESSAGE_BYTES:
                raise OSError("Cloud Band WebSocket message is unexpectedly large")
            if not fin:''')
replace(client, '''    filename = band_share.sanitize_midi_filename(midi_path.name)
    data = midi_path.read_bytes()
    request = urllib.request.Request(''', '''    filename = band_share.sanitize_midi_filename(midi_path.name)
    room_code = band_sync.normalize_room_code(urllib.parse.urlparse(base_url).path.rsplit("/", 1)[-1])
    host_token = _HOST_TOKENS.get(room_code)
    if not host_token:
        raise OSError("Cloud Band host credential missing; recreate the room")
    data = midi_path.read_bytes()
    request = urllib.request.Request(''')
replace(client, '            "X-Midi-Sha256": digest,', '            "X-Midi-Sha256": digest,\n            "X-Band-Host-Token": host_token,')

lite = ".github/workflows/build-windows.yml"
replace(lite, '      - "band_*.py"\n      - "online_*.py"', '      - "band_*.py"\n      - "cloudflare-band/**"\n      - "online_*.py"')
replace(lite, '''          if (gh release view $tag 2>$null) {
            gh release upload $tag `
              release/BPSR-MIDI-Lite.exe `
              release/BPSR-MIDI-Lite-Windows-x64.zip `
              release/SHA256SUMS.txt `
              --clobber
          } else {''', '''          if (gh release view $tag 2>$null) {
            throw "Release $tag already exists. Publish a new version instead of replacing validated binaries."
          } else {''')
studio = ".github/workflows/build-studio.yml"
replace(studio, '      - "band_*.py"\n      - "BPSR-MIDI-Studio.spec"', '      - "band_*.py"\n      - "cloudflare-band/**"\n      - "BPSR-MIDI-Studio.spec"')
replace(studio, '''            release-studio/FFMPEG_BUILD_INFO.txt `
            --clobber''', '''            release-studio/FFMPEG_BUILD_INFO.txt''')
replace(studio, '''          gh release delete-asset $tag BPSR-MIDI-Studio-beta.8-Windows.zip -y 2>$null | Out-Null
''', '')
# Ensure the existing tag belongs to the current build source, not a different commit.
replace(studio, '''          gh release upload $tag `
            release-studio/BPSR-MIDI-Studio-beta.9-Windows.zip''', '''          $releaseTarget = gh release view $tag --json targetCommitish --jq .targetCommitish
          if ($LASTEXITCODE -ne 0 -or $releaseTarget.Trim() -ne $env:GITHUB_SHA) {
            throw "Studio build source does not match the Lite release commit for $tag"
          }
          gh release upload $tag `
            release-studio/BPSR-MIDI-Studio-beta.9-Windows.zip''')

# Update the pre-existing source-text test: the actual server contract changes.
test = "tests/test_band_cloudflare.py"
replace(test, '''        "playerId !== this.hostId",''', '''        "!attachment.host || playerId !== this.hostId",
        "payload.host_token === this.hostToken",
        'request.headers.get("x-band-host-token")',
        "this.uploadInProgress",''')

# No partial write if a source differs from the reviewed commit.
for path, source in changes.items():
    path.write_text(source, encoding="utf-8")
    print(f"Updated {path}")
