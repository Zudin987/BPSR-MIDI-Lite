from pathlib import Path

p = Path("tools/apply_v250_instrument_policy.py")
text = p.read_text(encoding="utf-8")
replacements = {
    "transition = abs(mapped_interval - source_interval) * 3.0":
        "transition = abs(mapped_interval - source_interval) * 6.0",
    "transition += 40.0":
        "transition += 120.0",
    "transition += max(0, abs(mapped_interval) - 12) * 8.0":
        "transition += max(0, abs(mapped_interval) - 7) * 12.0",
}
for old, new in replacements.items():
    if old not in text:
        raise SystemExit(f"Expected Bass contour expression not found: {old}")
    text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")
print("Strengthened Bass contour/voice-leading priority")
