import { DurableObject } from "cloudflare:workers";

const PROTOCOL_VERSION = 2;
const MAX_MIDI_BYTES = 8 * 1024 * 1024;
const MIDI_CHUNK_BYTES = 1024 * 1024;
const ROOM_IDLE_MS = 6 * 60 * 60 * 1000;
const MIDI_TTL_MS = 3 * 60 * 60 * 1000;
const ROOM_RE = /^[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{12}$/;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

function cleanRoom(value) {
  const room = String(value || "").toUpperCase();
  return ROOM_RE.test(room) ? room : null;
}

function safeFilename(value) {
  let name = String(value || "room-song.mid").split(/[\\/]/).pop() || "room-song.mid";
  name = name.replace(/[^A-Za-z0-9._ ()\-\[\]]+/g, "_").replace(/^[ .]+|[ .]+$/g, "");
  if (!name) name = "room-song.mid";
  if (!/\.(mid|midi)$/i.test(name)) name = `${name.replace(/\.[^.]*$/, "") || "room-song"}.mid`;
  return name.slice(0, 120);
}

function roomFromPath(pathname) {
  const match = pathname.match(/^\/api\/rooms\/([^/]+)(?:\/(.*))?$/);
  if (!match) return null;
  const room = cleanRoom(decodeURIComponent(match[1]));
  if (!room) return null;
  return { room, tail: match[2] || "" };
}

function roomStub(env, room) {
  const id = env.BAND_ROOMS.idFromName(room);
  return env.BAND_ROOMS.get(id);
}

function token64() {
  return crypto.randomUUID().replaceAll("-", "") + crypto.randomUUID().replaceAll("-", "");
}

async function uploadMidi(request, env, room, origin) {
  const length = Number(request.headers.get("content-length") || "0");
  if (!Number.isFinite(length) || length <= 0 || length > MAX_MIDI_BYTES) {
    return json({ error: "invalid MIDI size" }, 413);
  }

  const filename = safeFilename(request.headers.get("x-midi-filename"));
  const sha256 = String(request.headers.get("x-midi-sha256") || "").toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(sha256)) return json({ error: "invalid MIDI hash" }, 400);

  const token = token64();
  const response = await roomStub(env, room).fetch(`https://internal/midi/${token}`, {
    method: "PUT",
    headers: {
      "content-type": "application/octet-stream",
      "content-length": String(length),
      "x-midi-filename": filename,
      "x-midi-sha256": sha256,
    },
    body: request.body,
  });
  if (!response.ok) return response;

  const result = await response.json();
  return json({
    ...result,
    url: `${origin}/api/rooms/${encodeURIComponent(room)}/midi/${token}`,
  });
}

async function downloadMidi(env, room, token) {
  if (!/^[0-9a-f]{64}$/i.test(token)) return new Response("Not found", { status: 404 });
  return roomStub(env, room).fetch(`https://internal/midi/${token}`, { method: "GET" });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return json({
        ok: true,
        service: "bpsr-midi-band",
        protocol: PROTOCOL_VERSION,
        midi_storage: "durable-object-sqlite",
      });
    }

    const parsed = roomFromPath(url.pathname);
    if (!parsed) return new Response("Not found", { status: 404 });
    const { room, tail } = parsed;

    if (tail === "ws") {
      if (request.headers.get("upgrade")?.toLowerCase() !== "websocket") {
        return new Response("Expected WebSocket", { status: 426 });
      }
      return roomStub(env, room).fetch(request);
    }

    if (tail === "midi" && request.method === "PUT") {
      return uploadMidi(request, env, room, url.origin);
    }

    const midiMatch = tail.match(/^midi\/([0-9a-fA-F]{64})$/);
    if (midiMatch && request.method === "GET") {
      return downloadMidi(env, room, midiMatch[1]);
    }

    return new Response("Not found", { status: 404 });
  },
};

export class BandRoom extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.ctx = ctx;
    this.env = env;
    this.hostId = null;
    this.midiMeta = null;

    this.ctx.blockConcurrencyWhile(async () => {
      this.hostId = (await this.ctx.storage.get("host_id")) || null;
      this.midiMeta = (await this.ctx.storage.get("midi_meta")) || null;
    });
  }

  async touch() {
    const now = Date.now();
    let next = now + ROOM_IDLE_MS;
    if (this.midiMeta && Number(this.midiMeta.expires || 0) > now) {
      next = Math.min(next, Number(this.midiMeta.expires));
    }
    await this.ctx.storage.setAlarm(next);
  }

  broadcast(payload, except = null) {
    const text = typeof payload === "string" ? payload : JSON.stringify(payload);
    for (const socket of this.ctx.getWebSockets()) {
      if (socket === except || socket.readyState !== WebSocket.OPEN) continue;
      try { socket.send(text); } catch (_) {}
    }
  }

  existingStates(except = null) {
    const states = [];
    for (const socket of this.ctx.getWebSockets()) {
      if (socket === except) continue;
      const attachment = socket.deserializeAttachment();
      if (attachment && attachment.state && attachment.state.event === "state") {
        states.push(attachment.state);
      }
    }
    return states;
  }

  async deleteMidi(meta = this.midiMeta) {
    if (!meta) return;
    const chunks = Math.max(0, Math.min(16, Number(meta.chunks || 0)));
    const token = String(meta.token || "");
    for (let index = 0; index < chunks; index += 1) {
      await this.ctx.storage.delete(`midi:${token}:${index}`);
    }
    await this.ctx.storage.delete("midi_meta");
    if (this.midiMeta && this.midiMeta.token === token) this.midiMeta = null;
  }

  async storeMidi(request, token) {
    const expectedSize = Number(request.headers.get("content-length") || "0");
    const expectedHash = String(request.headers.get("x-midi-sha256") || "").toLowerCase();
    const filename = safeFilename(request.headers.get("x-midi-filename"));

    if (!/^[0-9a-f]{64}$/i.test(token)) return json({ error: "invalid token" }, 400);
    if (!Number.isFinite(expectedSize) || expectedSize <= 0 || expectedSize > MAX_MIDI_BYTES) {
      return json({ error: "invalid MIDI size" }, 413);
    }
    if (!/^[0-9a-f]{64}$/.test(expectedHash)) return json({ error: "invalid MIDI hash" }, 400);

    const data = await request.arrayBuffer();
    if (data.byteLength !== expectedSize) return json({ error: "MIDI size changed during upload" }, 400);

    const bytes = new Uint8Array(data);
    if (
      bytes.length < 4 ||
      bytes[0] !== 0x4d ||
      bytes[1] !== 0x54 ||
      bytes[2] !== 0x68 ||
      bytes[3] !== 0x64
    ) {
      return json({ error: "not a standard MIDI file" }, 400);
    }

    const digestBuffer = await crypto.subtle.digest("SHA-256", data);
    const digest = Array.from(new Uint8Array(digestBuffer))
      .map((value) => value.toString(16).padStart(2, "0"))
      .join("");
    if (digest !== expectedHash) return json({ error: "MIDI SHA-256 mismatch" }, 400);

    if (this.midiMeta) await this.deleteMidi(this.midiMeta);

    const chunks = Math.ceil(data.byteLength / MIDI_CHUNK_BYTES);
    let written = 0;
    try {
      for (let index = 0; index < chunks; index += 1) {
        const start = index * MIDI_CHUNK_BYTES;
        const end = Math.min(data.byteLength, start + MIDI_CHUNK_BYTES);
        await this.ctx.storage.put(`midi:${token}:${index}`, data.slice(start, end));
        written += 1;
      }
    } catch (error) {
      for (let index = 0; index < written; index += 1) {
        try { await this.ctx.storage.delete(`midi:${token}:${index}`); } catch (_) {}
      }
      throw error;
    }

    const expires = Date.now() + MIDI_TTL_MS;
    this.midiMeta = {
      token,
      filename,
      size: data.byteLength,
      sha256: digest,
      expires,
      chunks,
    };
    await this.ctx.storage.put("midi_meta", this.midiMeta);
    await this.touch();

    return json({
      filename,
      size: data.byteLength,
      expires,
      midi_sha256: digest,
    });
  }

  async loadMidi(token) {
    const meta = this.midiMeta || (await this.ctx.storage.get("midi_meta")) || null;
    this.midiMeta = meta;
    if (!meta || String(meta.token || "") !== token) {
      return new Response("Not found", { status: 404 });
    }

    if (Date.now() > Number(meta.expires || 0)) {
      await this.deleteMidi(meta);
      return new Response("Expired", { status: 410 });
    }

    const chunks = Math.max(1, Math.min(16, Number(meta.chunks || 0)));
    const parts = [];
    let total = 0;
    for (let index = 0; index < chunks; index += 1) {
      const value = await this.ctx.storage.get(`midi:${token}:${index}`);
      if (!(value instanceof ArrayBuffer)) {
        await this.deleteMidi(meta);
        return new Response("Corrupt temporary MIDI", { status: 500 });
      }
      const bytes = new Uint8Array(value);
      parts.push(bytes);
      total += bytes.byteLength;
    }

    if (total !== Number(meta.size || 0) || total > MAX_MIDI_BYTES) {
      await this.deleteMidi(meta);
      return new Response("Corrupt temporary MIDI", { status: 500 });
    }

    const body = new Uint8Array(total);
    let offset = 0;
    for (const part of parts) {
      body.set(part, offset);
      offset += part.byteLength;
    }

    const headers = new Headers();
    headers.set("content-type", "application/octet-stream");
    headers.set("content-disposition", `attachment; filename="${safeFilename(meta.filename)}"`);
    headers.set("content-length", String(total));
    headers.set("cache-control", "private, no-store");
    return new Response(body, { headers });
  }

  async fetch(request) {
    const url = new URL(request.url);

    if (url.hostname === "internal") {
      const midiMatch = url.pathname.match(/^\/midi\/([0-9a-fA-F]{64})$/);
      if (midiMatch && request.method === "PUT") {
        return this.storeMidi(request, midiMatch[1].toLowerCase());
      }
      if (midiMatch && request.method === "GET") {
        return this.loadMidi(midiMatch[1].toLowerCase());
      }
      return new Response("Not found", { status: 404 });
    }

    if (request.headers.get("upgrade")?.toLowerCase() !== "websocket") {
      return new Response("Expected WebSocket", { status: 426 });
    }

    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    this.ctx.acceptWebSocket(server);
    server.serializeAttachment({ playerId: "", state: null });

    for (const state of this.existingStates(server)) {
      try { server.send(JSON.stringify(state)); } catch (_) {}
    }
    await this.touch();
    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(ws, message) {
    if (typeof message !== "string") return;
    let payload;
    try { payload = JSON.parse(message); } catch (_) { return; }
    if (!payload || typeof payload !== "object" || Number(payload.proto) !== PROTOCOL_VERSION) return;

    const event = String(payload.event || "");
    const playerId = String(payload.player_id || "").slice(0, 64);
    if (!playerId) return;
    await this.touch();

    if (event === "state") {
      if (!this.hostId && payload.host === true) {
        this.hostId = playerId;
        await this.ctx.storage.put("host_id", this.hostId);
      }
      payload.host = playerId === this.hostId;
      ws.serializeAttachment({ playerId, state: payload });

      for (const state of this.existingStates(ws)) {
        try { ws.send(JSON.stringify(state)); } catch (_) {}
      }
      this.broadcast(payload);
      return;
    }

    const attachment = ws.deserializeAttachment() || {};
    if (attachment.playerId && attachment.playerId !== playerId) return;

    if (event === "leave") {
      this.broadcast(payload);
      ws.serializeAttachment({ playerId: "", state: null });
      return;
    }

    if (["start", "midi_share", "midi_share_revoke"].includes(event)) {
      if (playerId !== this.hostId) {
        try {
          ws.send(JSON.stringify({
            proto: PROTOCOL_VERSION,
            event: "error",
            code: "host_only",
            message: "Only the room host can send this event",
          }));
        } catch (_) {}
        return;
      }
      this.broadcast(payload);
    }
  }

  async webSocketClose(ws, code, reason) {
    const attachment = ws.deserializeAttachment() || {};
    if (attachment.playerId) {
      this.broadcast({
        proto: PROTOCOL_VERSION,
        event: "leave",
        player_id: attachment.playerId,
      }, ws);
    }
    try { ws.close(code, reason); } catch (_) {}
    await this.touch();
  }

  async webSocketError(ws) {
    const attachment = ws.deserializeAttachment() || {};
    if (attachment.playerId) {
      this.broadcast({ proto: PROTOCOL_VERSION, event: "leave", player_id: attachment.playerId }, ws);
    }
  }

  async alarm() {
    const now = Date.now();
    if (this.midiMeta && Number(this.midiMeta.expires || 0) <= now) {
      await this.deleteMidi(this.midiMeta);
    }

    const sockets = this.ctx.getWebSockets();
    if (sockets.length > 0) {
      await this.touch();
      return;
    }

    if (this.midiMeta) {
      await this.ctx.storage.setAlarm(Math.min(Number(this.midiMeta.expires), now + ROOM_IDLE_MS));
      return;
    }

    await this.ctx.storage.deleteAll();
    this.hostId = null;
    this.midiMeta = null;
  }
}
