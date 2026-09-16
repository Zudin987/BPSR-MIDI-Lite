// Run explicitly after deployment: node cloudflare-band/smoke-live.mjs [https://worker.example]
// Creates one short-lived random test room; does not print or store its secret.
import assert from 'node:assert/strict';
import { createHash, randomInt } from 'node:crypto';

const origin = (process.argv[2] || process.env.BPSR_BAND_SERVICE_URL ||
  'https://bpsr-midi-band.zudinonline.workers.dev').replace(/\/$/, '');
const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
const code = Array.from({ length: 12 }, () => alphabet[randomInt(alphabet.length)]).join('');
const room = `${origin}/api/rooms/${code}`;
const midi = Buffer.from([0x4d, 0x54, 0x68, 0x64, 0, 0, 0, 6]);
const digest = createHash('sha256').update(midi).digest('hex');
const headers = { 'Content-Type': 'application/octet-stream',
  'X-Midi-Filename': 'smoke.mid', 'X-Midi-Sha256': digest };
const timeout = AbortSignal.timeout(12000);
const health = await fetch(`${origin}/health`, { signal: timeout });
assert.equal(health.status, 200, 'Worker health check failed');
assert.equal((await health.json()).protocol, 2, 'Unexpected protocol version');
const creation = await fetch(`${room}/create`, { method: 'POST', signal: timeout });
assert.equal(creation.status, 200, 'Room creation failed');
const { host_token: secret } = await creation.json();
assert.match(secret, /^[0-9a-f]{64}$/, 'Host credential missing');
const lookup = await fetch(`${room}/exists`, { signal: timeout });
assert.equal(lookup.status, 200, 'New room not discoverable');
const guestUpload = await fetch(`${room}/midi`, {
  method: 'PUT', headers, body: midi, signal: timeout,
});
assert.equal(guestUpload.status, 403, 'Guest MIDI upload was not rejected');
const hostUpload = await fetch(`${room}/midi`, {
  method: 'PUT', headers: { ...headers, 'X-Band-Host-Token': secret },
  body: midi, signal: timeout,
});
assert.equal(hostUpload.status, 200, 'Authenticated MIDI upload failed');
const offer = await hostUpload.json();
assert.equal(offer.midi_sha256, digest);
assert.equal(offer.size, midi.length);
assert.ok(offer.url.startsWith(`${room}/midi/`), 'Unexpected attachment URL');
const download = await fetch(offer.url, { signal: timeout });
assert.equal(download.status, 200, 'Uploaded MIDI could not be retrieved');
assert.deepEqual(Buffer.from(await download.arrayBuffer()), midi);

function connect(url) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    const timer = setTimeout(() => { ws.close(); reject(Error('WebSocket open timed out')); }, 8000);
    ws.addEventListener('open', () => { clearTimeout(timer); resolve(ws); }, { once: true });
    ws.addEventListener('error', () => { clearTimeout(timer); reject(Error('WebSocket open failed')); }, { once: true });
  });
}
async function until(test, label) {
  const deadline = Date.now() + 5000;
  while (!test()) {
    if (Date.now() >= deadline) throw Error(`${label} timed out`);
    await new Promise(resolve => setTimeout(resolve, 30));
  }
}
const wsUrl = `${origin.replace(/^http/, 'ws')}/api/rooms/${code}/ws`;
const host = await connect(wsUrl);
const guest = await connect(wsUrl);
const guestMessages = [];
const hostMessages = [];
guest.addEventListener('message', message => guestMessages.push(JSON.parse(message.data)));
host.addEventListener('message', message => hostMessages.push(JSON.parse(message.data)));
try {
  host.send(JSON.stringify({ proto: 2, event: 'state', room: code,
    player_id: 'SMOKE_HOST', host: true, host_token: secret }));
  await until(() => guestMessages.some(m => m.event === 'state' && m.host), 'host roster');
  assert.ok(guestMessages.every(m => !Object.hasOwn(m, 'host_token')), 'Host token leaked');
  guest.send(JSON.stringify({ proto: 2, event: 'state', room: code,
    player_id: 'SMOKE_GUEST', host: false }));
  await until(() => hostMessages.some(m => m.event === 'state' && m.player_id === 'SMOKE_GUEST'), 'guest roster');
  guest.send(JSON.stringify({ proto: 2, event: 'start', player_id: 'SMOKE_HOST' }));
  guest.send(JSON.stringify({ proto: 2, event: 'start', player_id: 'SMOKE_GUEST' }));
  await until(() => guestMessages.some(m => m.code === 'host_only'), 'host-only rejection');
  assert.ok(!hostMessages.some(m => m.event === 'start'), 'Guest triggered playback');
  host.send(JSON.stringify({ proto: 2, event: 'start', player_id: 'SMOKE_HOST' }));
  await until(() => guestMessages.some(m => m.event === 'start'), 'authorized start');
} finally {
  host.close();
  guest.close();
}
console.log('PASS: health, room creation, host credentials, upload/download, identity and start authorization');
