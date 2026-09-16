"""Run the one-time migration with corrected unique anchors and extra bounds check."""
from pathlib import Path

script = Path("tools/apply_review_fixes.py").read_text(encoding="utf-8")
old_constructor = '''replace(worker, '    this.hostId = null;\\n    this.midiMeta = null;', '    this.hostId = null;\\n    this.hostToken = null;\\n    this.uploadInProgress = false;\\n    this.midiMeta = null;')'''
new_constructor = '''replace(worker, '    this.hostId = null;\\n    this.midiMeta = null;\\n    this.createdAt = null;\\n\\n    this.ctx.blockConcurrencyWhile', '    this.hostId = null;\\n    this.hostToken = null;\\n    this.uploadInProgress = false;\\n    this.midiMeta = null;\\n    this.createdAt = null;\\n\\n    this.ctx.blockConcurrencyWhile')'''
if script.count(old_constructor) != 1:
    raise RuntimeError("Expected exact constructor replacement anchor")
script = script.replace(old_constructor, new_constructor)
# Push and pull_request have identical path filters; replace both intentionally.
old_check = '    if count != 1:\n        raise RuntimeError(f"Expected one match in {path}, got {count}: {old[:90]!r}")\n    changes[file] = source.replace(old, new, 1)'
new_check = '''    both_filters = path == ".github/workflows/build-studio.yml" and old.startswith('      - "band_*.py"')
    expected = 2 if both_filters else 1
    if count != expected:
        raise RuntimeError(f"Expected {expected} match(es) in {path}, got {count}: {old[:90]!r}")
    changes[file] = source.replace(old, new, expected)'''
if script.count(old_check) != 1:
    raise RuntimeError("Expected exact checked replacement helper")
script = script.replace(old_check, new_check)
marker = 'replace(client, \'_SOCKET_IDLE_SECONDS = 35.0\', \'_SOCKET_IDLE_SECONDS = 35.0\\n_MAX_WS_MESSAGE_BYTES = 256 * 1024\')'
if script.count(marker) != 1:
    raise RuntimeError("Expected WebSocket frame-size anchor")
script = script.replace(marker, marker + '''\nreplace(client, '    if length > 16 * 1024 * 1024:', '    if length > _MAX_WS_MESSAGE_BYTES:')''')
exec(compile(script, "tools/apply_review_fixes.py", "exec"), {"__name__": "__main__"})
