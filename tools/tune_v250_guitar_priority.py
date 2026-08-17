from pathlib import Path

p = Path("midi_engine.py")
text = p.read_text(encoding="utf-8")
old = '''        cost += mapped.priority_fold_penalty * 300.0\n        cost += mapped.priority_displacement * 1.5\n'''
new = '''        cost += mapped.priority_fold_penalty * 20.0\n        cost += mapped.priority_displacement * 0.25\n'''
if old not in text:
    raise SystemExit("Guitar priority weights not found")
p.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Made Guitar melody weighting a conservative tie-breaker")
