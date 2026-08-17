from __future__ import annotations

import re
from pathlib import Path


app_path = Path("app.py")
source = app_path.read_text(encoding="utf-8")

required_replacements = {
    "import threading\n": "",
    "from diagnostics import build_diagnostic_text\n": "",
    'APP_VERSION = "2.4.0"': 'APP_VERSION = "2.4.1"',
    '        self._last_input_test = "Not run"\n': "",
    '        self._input_test_running = False\n': "",
    '        self.status_var = tk.StringVar(value="Add a MIDI to the library, then press Reload.")':
        '        self.status_var = tk.StringVar(value="Open the song folder and add a MIDI file.")',
}
for old, new in required_replacements.items():
    if old not in source:
        raise RuntimeError(f"Expected app.py text not found: {old!r}")
    source = source.replace(old, new, 1)

for old in ('    BACKEND_NAMES,\n', '    WindowsKeySender,\n'):
    if old not in source:
        raise RuntimeError(f"Expected win_input import not found: {old!r}")
    source = source.replace(old, "", 1)

legacy_controls = re.compile(
    r'\n        ttk\.Button\(\n'
    r'            run_frame,\n'
    r'            text="Copy diagnostics",.*?'
    r'        self\.test_button\.grid\(row=1, column=6, padx=\(8, 0\), pady=\(9, 0\)\)\n',
    re.S,
)
source, count = legacy_controls.subn("\n", source, count=1)
if count != 1:
    raise RuntimeError("Could not remove legacy diagnostics/test controls")

copy_diagnostics = re.compile(
    r'\n    def _copy_diagnostics\(self\) -> None:.*?(?=\n    def _input_error_message)',
    re.S,
)
source, count = copy_diagnostics.subn("", source, count=1)
if count != 1:
    raise RuntimeError("Could not remove _copy_diagnostics")

test_input = re.compile(
    r'\n    def _test_input\(self\) -> None:.*?(?=\n    def _start)',
    re.S,
)
source, count = test_input.subn("", source, count=1)
if count != 1:
    raise RuntimeError("Could not remove _test_input")

source = source.replace('        self.test_button.configure(state="disabled")\n', "")
source = source.replace('                    self.test_button.configure(state="normal")\n', "")

queue_test_branches = re.compile(
    r'                elif kind == "test_status":.*?(?=                elif kind == "finished":)',
    re.S,
)
source, count = queue_test_branches.subn("", source, count=1)
if count != 1:
    raise RuntimeError("Could not remove input-test queue branches")

for forbidden in (
    "build_diagnostic_text",
    "_copy_diagnostics",
    "_test_input",
    "_last_input_test",
    "_input_test_running",
    "self.test_button",
    "BACKEND_NAMES",
    "WindowsKeySender",
):
    if forbidden in source:
        raise RuntimeError(f"Removed feature still referenced in app.py: {forbidden}")

app_path.write_text(source, encoding="utf-8")

for path in (Path("diagnostics.py"), Path("tests/test_diagnostics.py")):
    if path.exists():
        path.unlink()

changelog = Path("CHANGELOG.md")
text = changelog.read_text(encoding="utf-8")
if "## v2.4.1" not in text:
    entry = """## v2.4.1

- Removed **Test keyboard input** and **Copy support info**, including the unused diagnostics/test-input implementation.
- Made **Keyboard connection** permanently visible under **Help & recovery** and kept all four input backends available.
- Kept **Help & recovery** to two user choices only: restore recommended settings and keyboard connection.
- Replaced **Add MIDI…** with **Open folder** and added automatic MIDI-library refresh when files are copied or removed.
- Renamed the speed reset action to **Restore song speed to default 100%**.
- Placed **What are you playing?** and **Which category have you unlocked?** side-by-side in the Instrument section.
- Kept the scrollable v2.4 layout, Song Check remap counts, safe instrument mappings, MIDI engine, and playback timing unchanged.

"""
    text = text.replace("# Changelog\n\n", "# Changelog\n\n" + entry, 1)
    changelog.write_text(text, encoding="utf-8")
