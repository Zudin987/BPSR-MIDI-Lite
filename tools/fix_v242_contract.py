from pathlib import Path

path = Path("tests/test_ui_contract.py")
text = path.read_text(encoding="utf-8")
old = '    assert "plan.folded_notes" in source\n'
if text.count(old) != 1:
    raise SystemExit(f"expected one stale folded-notes assertion, found {text.count(old)}")
path.write_text(text.replace(old, ""), encoding="utf-8")
