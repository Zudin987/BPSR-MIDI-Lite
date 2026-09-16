"""One-shot exact-match edit for concurrent Cloud Band cleanup and upload."""
from pathlib import Path

worker = Path('cloudflare-band/src/index.js')
source = worker.read_text(encoding='utf-8')
old = '''  async deleteMidi(meta = this.midiMeta) {
    if (!meta) return;
    const chunks = Math.max(0, Math.min(16, Number(meta.chunks || 0)));
    const token = String(meta.token || "");
    for (let index = 0; index < chunks; index += 1) {
      await this.ctx.storage.delete(`midi:${token}:${index}`);
    }
    await this.ctx.storage.delete("midi_meta");
    if (this.midiMeta && this.midiMeta.token === token) this.midiMeta = null;
  }
'''
new = '''  async deleteMidi(meta = this.midiMeta) {
    if (!meta || this.uploadInProgress) return;
    // The same lock covers writes and expiry/corruption cleanup. Never remove
    // a newer upload's metadata while deleting an expired, superseded token.
    this.uploadInProgress = true;
    try {
      const chunks = Math.max(0, Math.min(16, Number(meta.chunks || 0)));
      const token = String(meta.token || "");
      for (let index = 0; index < chunks; index += 1) {
        await this.ctx.storage.delete(`midi:${token}:${index}`);
      }
      if (this.midiMeta && this.midiMeta.token === token) {
        await this.ctx.storage.delete("midi_meta");
        this.midiMeta = null;
      }
    } finally {
      this.uploadInProgress = false;
    }
  }
'''
assert source.count(old) == 1, 'MIDI cleanup changed unexpectedly'
worker.write_text(source.replace(old, new, 1), encoding='utf-8')

tests = Path('cloudflare-band/test-security.cjs')
source = tests.read_text(encoding='utf-8')
old = '''  assert.equal(values.get('midi_meta').token, second);
  assert.equal((await room.loadMidi(second)).status, 200);
});
'''
new = '''  assert.equal(values.get('midi_meta').token, second);
  assert.equal((await room.loadMidi(second)).status, 200);
  // A delayed expiry/corruption cleanup must never remove newer metadata.
  await room.deleteMidi({ token: first, chunks: 1 });
  assert.equal(values.get('midi_meta').token, second);
  assert.equal((await room.loadMidi(second)).status, 200);
});
'''
assert source.count(old) == 1, 'Storage regression anchor changed unexpectedly'
tests.write_text(source.replace(old, new, 1), encoding='utf-8')
print('Fixed stale deletion and added regression')
