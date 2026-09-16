const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Load the Worker class without Cloudflare infrastructure; exercise real methods.
const source = fs.readFileSync(require('node:path').join(__dirname, 'src/index.js'), 'utf8')
  .replace('import { DurableObject } from "cloudflare:workers";', 'class DurableObject { constructor() {} }')
  .replace('export default {', 'const worker = {')
  .replace('export class BandRoom extends DurableObject {', 'class BandRoom extends DurableObject {');
const sandbox = {
  crypto: globalThis.crypto, Request, Response, Headers, URL, Uint8Array, ArrayBuffer,
  Date, String, Number, JSON, Math, WebSocket: { OPEN: 1 },
};
vm.runInNewContext(`${source}\nglobalThis.testExports = { BandRoom, worker };`, sandbox);
const { BandRoom } = sandbox.testExports;

function makeRoom() {
  const values = new Map();
  const sockets = [];
  const storage = {
    failKey: null,
    get: async key => values.get(key),
    put: async (key, value) => {
      if (key === storage.failKey) throw Error('simulated storage failure');
      values.set(key, value);
    },
    delete: async key => values.delete(key),
    deleteAll: async () => values.clear(),
    setAlarm: async () => {},
  };
  const ctx = {
    storage,
    getWebSockets: () => sockets,
    acceptWebSocket: socket => sockets.push(socket),
    blockConcurrencyWhile: fn => { ctx.init = fn(); },
  };
  const room = new BandRoom(ctx, {});
  return { room, ctx, storage, sockets, values };
}

function socket(sockets) {
  const result = {
    readyState: 1, received: [], attachment: { playerId: '', state: null },
    serializeAttachment(value) { this.attachment = value; },
    deserializeAttachment() { return this.attachment; },
    send(value) { this.received.push(JSON.parse(value)); },
    close() { this.readyState = 3; },
  };
  sockets.push(result);
  return result;
}

async function createdRoom() {
  const fixture = makeRoom();
  await fixture.ctx.init;
  const response = await fixture.room.fetch(new Request('https://internal/room-create', { method: 'POST' }));
  assert.equal(response.status, 200);
  const { host_token: token } = await response.json();
  assert.match(token, /^[0-9a-f]{64}$/);
  return { ...fixture, token };
}

function state(id, host = false, extra = {}) {
  return JSON.stringify({ proto: 2, event: 'state', room: 'ABCDEFGHJKLM', player_id: id, host, ...extra });
}

async function requestForMidi(token, bytes, hostToken) {
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)))
    .map(n => n.toString(16).padStart(2, '0')).join('');
  return new Request(`https://internal/midi/${token}`, {
    method: 'PUT', body: bytes,
    headers: {
      'content-length': String(bytes.byteLength), 'x-midi-sha256': digest,
      'x-midi-filename': 'test.mid', ...(hostToken ? { 'x-band-host-token': hostToken } : {}),
    },
  });
}

test('host credential is private and IDs are bound to WebSocket connections', async () => {
  const { room, sockets, token } = await createdRoom();
  const owner = socket(sockets);
  const visitor = socket(sockets);
  await room.webSocketMessage(visitor, state('HOST', true));
  assert.equal(visitor.deserializeAttachment().playerId, '');
  await room.webSocketMessage(owner, state('HOST', true, { host_token: token }));
  assert.equal(room.hostId, 'HOST');
  assert.ok(visitor.received.some(item => item.event === 'state' && item.host === true));
  assert.ok(visitor.received.every(item => !Object.hasOwn(item, 'host_token')));
  await room.webSocketMessage(visitor, state('GUEST'));
  const count = owner.received.length;
  await room.webSocketMessage(visitor, JSON.stringify({ proto: 2, event: 'start', player_id: 'HOST' }));
  await room.webSocketMessage(visitor, JSON.stringify({ proto: 2, event: 'start', player_id: 'GUEST' }));
  assert.equal(owner.received.length, count);
  assert.ok(visitor.received.some(item => item.code === 'host_only'));
  await room.webSocketMessage(owner, JSON.stringify({ proto: 2, event: 'start', player_id: 'HOST' }));
  assert.ok(visitor.received.some(item => item.event === 'start'));
  // An existing socket cannot silently switch to another player's identity.
  await room.webSocketMessage(visitor, state('HOST', true, { host_token: token }));
  assert.equal(visitor.deserializeAttachment().playerId, 'GUEST');
});

test('guest uploads fail and failed replacements retain the previous MIDI', async () => {
  const { room, values, storage, token } = await createdRoom();
  const bytes = new Uint8Array([0x4d, 0x54, 0x68, 0x64, 0, 0, 0, 6]);
  const first = 'a'.repeat(64);
  const second = 'b'.repeat(64);
  const guest = await room.storeMidi(await requestForMidi(first, bytes), first);
  assert.equal(guest.status, 403);
  const saved = await room.storeMidi(await requestForMidi(first, bytes, token), first);
  assert.equal(saved.status, 200);
  assert.equal(values.get('midi_meta').token, first);
  storage.failKey = `midi:${second}:0`;
  await assert.rejects(room.storeMidi(await requestForMidi(second, bytes, token), second));
  assert.equal(values.get('midi_meta').token, first);
  assert.equal((await room.loadMidi(first)).status, 200);
  storage.failKey = null;
  const replaced = await room.storeMidi(await requestForMidi(second, bytes, token), second);
  assert.equal(replaced.status, 200);
  assert.equal(values.get('midi_meta').token, second);
  assert.equal((await room.loadMidi(second)).status, 200);
  // A delayed expiry/corruption cleanup must never remove newer metadata.
  await room.deleteMidi({ token: first, chunks: 1 });
  assert.equal(values.get('midi_meta').token, second);
  assert.equal((await room.loadMidi(second)).status, 200);
});


test('racing room creates issue exactly one host credential', async () => {
  const { room, ctx } = makeRoom();
  await ctx.init;
  const create = () => room.fetch(new Request('https://internal/room-create', { method: 'POST' }));
  const [first, second] = await Promise.all([create(), create()]);
  assert.equal(first.status, 200);
  assert.equal(second.status, 409);
});

test('credentialed host reconnect evicts previous host and a squatting guest', async () => {
  const { room, sockets, token } = await createdRoom();
  const host = socket(sockets);
  const witness = socket(sockets);
  await room.webSocketMessage(host, state('OLD_HOST', true, { host_token: token }));
  await room.webSocketMessage(witness, state('WITNESS'));
  const newHost = socket(sockets);
  await room.webSocketMessage(newHost, state('NEW_HOST', true, { host_token: token }));
  assert.equal(host.readyState, 3);
  assert.equal(room.hostId, 'NEW_HOST');
  assert.ok(witness.received.some(m => m.event === 'leave' && m.player_id === 'OLD_HOST'));
  assert.equal(sockets.filter(ws => ws.readyState === 1 && ws.attachment.host).length, 1);

  // A guest can reserve a publicly known ID but must not lock out the owner.
  const squatter = socket(sockets);
  await room.webSocketMessage(squatter, state('REJOIN_ID'));
  const rejoined = socket(sockets);
  await room.webSocketMessage(rejoined, state('REJOIN_ID', true, { host_token: token }));
  assert.equal(squatter.readyState, 3);
  assert.equal(newHost.readyState, 3);
  assert.equal(room.hostId, 'REJOIN_ID');
  assert.equal(sockets.filter(ws => ws.readyState === 1 && ws.attachment.host).length, 1);
});

test('expiry alarm defers while uploads are underway and does not spin', async () => {
  const { room, ctx, values } = await createdRoom();
  let nextAlarm = 0;
  ctx.storage.setAlarm = async at => { nextAlarm = at; };
  room.midiMeta = { token: 'a'.repeat(64), expires: Date.now() - 1000, chunks: 1 };
  values.set('midi_meta', room.midiMeta);
  room.uploadInProgress = true;
  await room.alarm();
  assert.ok(nextAlarm > Date.now() + 50_000);
  assert.equal(values.get('midi_meta').token, 'a'.repeat(64));
  room.uploadInProgress = false;
  await room.alarm();
  assert.equal(values.has('midi_meta'), false);
});
