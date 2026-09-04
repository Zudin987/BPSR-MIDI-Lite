import { DurableObject } from "cloudflare:workers";

const PROTOCOL_VERSION = 2;
const MAX_MIDI_BYTES = 8 * 1024 * 1024;
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

async function uploadMidi(request, env, room, origin) {
  const length = Number(request.headers.get("content-length") || "0");
  if (!Number.isFinite(length) || length <= 0 || length > MAX_MIDI_BYTES) {
    return json({ error: "invalid MIDI size" }, 413);
  }
  const filename = safeFilename(request.headers.get("x-midi-filename"));
  const sha256 = String(request.headers.get("x-midi-sha256") || "").toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(sha256)) return json({ error: "invalid MIDI hash" }, 400);

  const token = crypto.randomUUID().replaceAll("-", "") + crypto.randomUUID().replaceAll("-", "");
  const key = `room/${room}/${token}.mid`;
  const expires = Date.now() + MIDI_TTL_MS;
  await env.MIDI_BUCKET.put(key, request.body, {
    httpMetadata: { contentType: "application/octet-stream" },
    customMetadata: {
      room,
      filename,
      sha256,
      expires: String(expires),
      size: String(length),
    },
  });

  await roomStub(env, room).fetch("https://internal/midi-register", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ key, expires }),
  });

  return json({
    url: `${origin}/api/rooms/${encodeURIComponent(room)}/midi/${token}`,
    filename,
    size: length,
    expires,
    midi_sha256: sha256,
  });
}

async function downloadMidi(env, room, token) {
  if (!/^[0-9a-f]{64}$/i.test(token)) return new Response("Not found", { status: 404 });
  const key = `room/${room}/${token}.mid`;
  const object = await env.MIDI_BUCKET.get(key);
  if (!object) return new Response("Not found", { status: 404 });
  const meta = object.customMetadata || {};
  if (meta.room !== room) return new Response("Not found", { status: 404 });
  const expires = Number(meta.expires || "0");
  if (expires && Date.now() > expires) {
    await env.MIDI_BUCKET.delete(key);
    return new Response("Expired", { status: 410 });
  }
  const headers = new Headers();
  headers.set("content-type", "application/octet-stream");
  headers.set("content-disposition", `attachment; filename="${safeFilename(meta.filename)}"`);
  headers.set("cache-control", "private, no-store");
  if (object.size != null) headers.set("content-length", String(object.size));
  return new Response(object.body, { headers });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return json({ ok: true, service: "bpsr-midi-band", protocol: PROTOCOL_VERSION });
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
    this.ctx.blockConcurrencyWhile(async () => {
      this.hostId = (await this.ctx.storage.get("host_id")) || null;
    });
  }

  async touch() {
    await this.ctx.storage.setAlarm(Date.now() + ROOM_IDLE_MS);
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

  async fetch(request) {
    const url = new URL(request.url);
    if (url.hostname === "internal" && url.pathname === "/midi-register" && request.method === "POST") {
      const data = await request.json();
      const key = String(data.key || "");
      const expires = Number(data.expires || 0);
      if (key && expires > Date.now()) {
        const files = (await this.ctx.storage.get("midi_files")) || [];
        files.push({ key, expires });
        await this.ctx.storage.put("midi_files", files.slice(-12));
        await this.touch();
      }
      return new Response(null, { status: 204 });
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
      const attachment = { playerId, state: payload };
      ws.serializeAttachment(attachment);

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
        try { ws.send(JSON.stringify({ proto: PROTOCOL_VERSION, event: "error", code: "host_only", message: "Only the room host can send this event" })); } catch (_) {}
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
    const sockets = this.ctx.getWebSockets();
    const files = (await this.ctx.storage.get("midi_files")) || [];
    const now = Date.now();
    const keep = [];
    for (const item of files) {
      if (Number(item.expires || 0) <= now) {
        try { await this.env.MIDI_BUCKET.delete(String(item.key)); } catch (_) {}
      } else {
        keep.push(item);
      }
    }
    if (keep.length) await this.ctx.storage.put("midi_files", keep);
    else await this.ctx.storage.delete("midi_files");

    if (sockets.length > 0) {
      await this.touch();
      return;
    }
    if (keep.length > 0) {
      const nextExpiry = Math.min(...keep.map((item) => Number(item.expires)));
      await this.ctx.storage.setAlarm(Math.min(nextExpiry, now + ROOM_IDLE_MS));
      return;
    }
    await this.ctx.storage.deleteAll();
    this.hostId = null;
  }
}
