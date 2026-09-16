"""Single-use exact-match hardening; raise rather than patch unfamiliar source."""
from pathlib import Path

worker = Path('cloudflare-band/src/index.js')
src = worker.read_text(encoding='utf-8')
patches = [
    (
        '    this.uploadInProgress = false;\n    this.midiMeta = null;',
        '    this.uploadInProgress = false;\n    this.creationInProgress = false;\n    this.midiMeta = null;',
    ),
    (
        '''        if (this.createdAt) return json({ error: "room already exists" }, 409);
        const hostToken = token64();
        const createdAt = Date.now();
        await this.ctx.storage.put("host_token", hostToken);
        await this.ctx.storage.put("created_at", createdAt);
        this.hostToken = hostToken;
        this.createdAt = createdAt;
        await this.touch();
        return json({ ok: true, created_at: createdAt, host_token: hostToken });''',
        '''        if (this.createdAt || this.creationInProgress) {
          return json({ error: "room already exists or is being created" }, 409);
        }
        this.creationInProgress = true;
        try {
          const hostToken = token64();
          const createdAt = Date.now();
          await this.ctx.storage.put("host_token", hostToken);
          await this.ctx.storage.put("created_at", createdAt);
          this.hostToken = hostToken;
          this.createdAt = createdAt;
          await this.touch();
          return json({ ok: true, created_at: createdAt, host_token: hostToken });
        } finally {
          this.creationInProgress = false;
        }''',
    ),
    (
        '''        if (state.playerId !== playerId) continue;
        if (!authorizedHost || !state.host) return;
        // Credential-bearing host reconnects can replace a stale host socket.
        other.serializeAttachment({ playerId: "", state: null, host: false });
        try { other.close(1000, "Host reconnected"); } catch (_) {}''',
        '''        if (authorizedHost && (state.host || state.playerId === playerId)) {
          // One credential-bearing host wins, even if their app restarted with
          // a new player ID or a guest reserved the previous ID during reconnect.
          if (state.playerId) {
            this.broadcast({ proto: PROTOCOL_VERSION, event: "leave",
              player_id: state.playerId }, other);
          }
          other.serializeAttachment({ playerId: "", state: null, host: false });
          try { other.close(1000, "Host reconnected"); } catch (_) {}
          continue;
        }
        if (state.playerId === playerId) return;''',
    ),
    (
        '''  async alarm() {
    const now = Date.now();
    if (this.midiMeta && Number(this.midiMeta.expires || 0) <= now) {''',
        '''  async alarm() {
    const now = Date.now();
    if (this.uploadInProgress || this.creationInProgress) {
      // A pending upload cannot be expired or deleted mid-commit. In
      // particular, do not reschedule an already-past MIDI expiry in a loop.
      await this.ctx.storage.setAlarm(now + 60_000);
      return;
    }
    if (this.midiMeta && Number(this.midiMeta.expires || 0) <= now) {''',
    ),
    (
        '''    await this.ctx.storage.deleteAll();
    this.hostId = null;''',
        '''    if (this.uploadInProgress || this.creationInProgress) {
      await this.ctx.storage.setAlarm(now + 60_000);
      return;
    }
    await this.ctx.storage.deleteAll();
    this.hostId = null;''',
    ),
]
for before, after in patches:
    assert src.count(before) == 1, f'Unexpected Worker source anchor: {before[:90]!r}'
    src = src.replace(before, after, 1)
worker.write_text(src, encoding='utf-8')

path = Path('cloudflare-band/test-security.cjs')
src = path.read_text(encoding='utf-8')
src += '''

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
'''
path.write_text(src, encoding='utf-8')
print('Hardened concurrent room creation, reconnect host ownership and upload-time expiry')
