from __future__ import annotations

import re
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


# --- modern_ui.py ---------------------------------------------------------
path = Path("modern_ui.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    "from typing import Any, Callable\n\n\n",
    "from typing import Any, Callable\n\nimport online_ui\n\n\n",
    "modern_ui import",
)
text = replace_once(
    text,
    "        if not self.player.is_playing:\n            folder = Path(self.midi_folder_var.get())",
    "        if not self.player.is_playing and online_ui.is_local_source(self):\n            folder = Path(self.midi_folder_var.get())",
    "local-only folder polling",
)
text = replace_once(
    text,
    "    self._apply_system_theme(force=True)\n    _apply_simple_styles(self)\n\n    self.geometry(\"780x700\")",
    "    self._apply_system_theme(force=True)\n    _apply_simple_styles(self)\n    online_ui.initialize(self)\n\n    self.geometry(\"780x700\")",
    "initialize online UI",
)
old_picker = '''    self.midi_combo = ttk.Combobox(
        songs,
        textvariable=self.midi_display_var,
        state="readonly",
        values=(),
    )
    self.midi_combo.grid(row=0, column=0, sticky="ew")
    self.midi_combo.bind("<<ComboboxSelected>>", lambda _event: self._midi_selected())
    ttk.Button(songs, text="Open folder", command=self._open_midi_folder).grid(
        row=0, column=1, padx=(8, 0)
    )
'''
text = replace_once(
    text,
    old_picker,
    "    online_ui.build_song_source_ui(self, songs)\n",
    "song source tabs",
)
text = replace_once(
    text,
    '''        text=(
            "Open the song folder and copy .mid/.midi files there; the list refreshes automatically. "
            "Normal categories fit notes automatically. Raw MIDI keeps pitches unchanged and skips out-of-range notes."
        ),''',
    '''        text=(
            "Use Local for permanent MIDI files, Online Sequencer to search/play from temporary cache, or Bookmarks to revisit online songs. "
            "Normal categories fit notes automatically. Raw MIDI keeps pitches unchanged and skips out-of-range notes."
        ),''',
    "song hint",
)
text = replace_once(
    text,
    '''def _modern_profile_changed(self: Any) -> None:
    _preserve_song_speed(self, self._modern_original_profile_changed)


def _modern_instrument_changed(self: Any) -> None:
    _preserve_song_speed(self, self._modern_original_instrument_changed)
''',
    '''def _modern_profile_changed(self: Any) -> None:
    _preserve_song_speed(self, self._modern_original_profile_changed)
    online_ui.schedule_reanalysis(self)


def _modern_instrument_changed(self: Any) -> None:
    _preserve_song_speed(self, self._modern_original_instrument_changed)
    online_ui.schedule_reanalysis(self)
''',
    "online reanalysis on profile changes",
)
text = replace_once(
    text,
    '''        data["song_speed_percent"] = max(25, min(200, int(self.speed_var.get())))
        data.pop("minimize", None)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")''',
    '''        data["song_speed_percent"] = max(25, min(200, int(self.speed_var.get())))
        data.pop("minimize", None)
        online_ui.save_bookmarks_to_config(self, data)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")''',
    "save bookmarks",
)
text = replace_once(
    text,
    '''        if not isinstance(data, dict):
            return
        speed = int(data.get("song_speed_percent", 100))''',
    '''        if not isinstance(data, dict):
            return
        online_ui.load_bookmarks_from_config(self, data)
        speed = int(data.get("song_speed_percent", 100))''',
    "load bookmarks",
)
text = replace_once(
    text,
    '''        if not self.file_var.get():
            self.suitability_var.set("Add a MIDI song to begin")
            self.analysis_var.set("Open the song folder and copy in a .mid or .midi file.")
        return''',
    '''        if not self.file_var.get():
            title, message = online_ui.empty_selection_message(self)
            self.suitability_var.set(title)
            self.analysis_var.set(message)
        return''',
    "empty song message",
)
text = replace_once(
    text,
    '''        f"{metrics}\\n"
        f"{explanation}"
    )''',
    '''        f"{metrics}\\n"
        f"{explanation}{online_ui.analysis_suffix(self)}"
    )''',
    "online analysis cache suffix",
)
text = replace_once(
    text,
    "    if not self._midi_lookup:\n        self.start_button.configure(state=\"disabled\")",
    "    if not self._midi_lookup and online_ui.is_local_source(self):\n        self.start_button.configure(state=\"disabled\")",
    "local empty library message",
)
path.write_text(text, encoding="utf-8")


# --- app.py ---------------------------------------------------------------
path = Path("app.py")
text = path.read_text(encoding="utf-8")
text = replace_once(text, 'APP_VERSION = "2.5.0"', 'APP_VERSION = "3.0.0"', "app version")
text = replace_once(
    text,
    '            messagebox.showerror(APP_NAME, "Choose a valid MIDI from the library first.")',
    '            messagebox.showerror(APP_NAME, "Choose a valid song first.")',
    "play error wording",
)
path.write_text(text, encoding="utf-8")


# --- modern_launcher.py ---------------------------------------------------
path = Path("modern_launcher.py")
text = path.read_text(encoding="utf-8")
text = replace_once(text, 'app.APP_VERSION = "2.5.0"', 'app.APP_VERSION = "3.0.0"', "launcher version")
path.write_text(text, encoding="utf-8")


# --- version_info.txt -----------------------------------------------------
path = Path("version_info.txt")
text = path.read_text(encoding="utf-8")
text = re.sub(r"filevers=\([^\n]+\)", "filevers=(3, 0, 0, 0)", text, count=1)
text = re.sub(r"prodvers=\([^\n]+\)", "prodvers=(3, 0, 0, 0)", text, count=1)
text = re.sub(r"StringStruct\('FileVersion', '[^']+'\)", "StringStruct('FileVersion', '3.0.0')", text, count=1)
text = re.sub(r"StringStruct\('ProductVersion', '[^']+'\)", "StringStruct('ProductVersion', '3.0.0')", text, count=1)
path.write_text(text, encoding="utf-8")


# --- build_exe.bat --------------------------------------------------------
path = Path("build_exe.bat")
text = path.read_text(encoding="utf-8")
text = text.replace("2.5.0", "3.0.0")
path.write_text(text, encoding="utf-8")


# --- README.md ------------------------------------------------------------
path = Path("README.md")
text = path.read_text(encoding="utf-8")
old_quick = '''## Quick start

1. Choose **Keyboard**, **Guitar**, or **Bass**, then choose the BPSR **Category** you have unlocked beside it.
2. Click **Open folder** and copy your `.mid` / `.midi` files into the song folder. The song list refreshes automatically.
3. Leave **Song speed** at `100%` for the original MIDI tempo, or adjust it.
4. Check **Song check** to see whether the song is ready and how many notes were remapped.
5. Set the **Countdown** if needed.
6. Press **Play in BPSR** and switch back to the game before the countdown ends.

The app stays open during playback. **F10** always stops playback and releases held keys.
'''
new_quick = '''## Quick start

1. Choose **Keyboard**, **Guitar**, or **Bass**, then choose the BPSR **Category** you have unlocked beside it.
2. In **Song**, choose a source:
   - **Local** — play permanent `.mid` / `.midi` files from the app's song folder.
   - **Online Sequencer** — search public Online Sequencer songs, see their BPSR fit/remap counts, and play from temporary cache without saving them permanently.
   - **Bookmarks** — revisit Online Sequencer songs you bookmarked in the app.
3. Leave **Song speed** at `100%` for the original tempo, or adjust it.
4. Check **Song check** for readiness, remapped notes, skipped notes, and filtered/simplified notes.
5. Press **Play in BPSR** and switch back to the game before the countdown ends.

The app stays open during playback. **F10** always stops playback and releases held keys.
'''
text = replace_once(text, old_quick, new_quick, "README quick start")
text = replace_once(
    text,
    "- **Song** — select a MIDI, open the song folder, and change song speed if needed.",
    "- **Song** — switch between Local, Online Sequencer, and Bookmarks; online results show BPSR fit before you save anything permanently.",
    "README interface song",
)
old_managing = '''## Managing songs

**Open folder** opens the MIDI library used by the app. Copy or remove `.mid` / `.midi` files there normally with File Explorer. The app checks the folder automatically and refreshes the song list when it changes, so there is no separate Add MIDI or Reload workflow.

**Restore song speed to default 100%** returns only the song speed to the original MIDI tempo.
'''
new_managing = '''## Managing songs

### Local

**Open folder** opens the permanent MIDI library used by the app. Copy or remove `.mid` / `.midi` files there normally with File Explorer. The app refreshes the list automatically while Local is active.

### Online Sequencer

The Online Sequencer tab searches public sequences directly inside BPSR MIDI Lite. The top results are fetched gradually and analyzed using the **same BPSR planner** as Local MIDI files, so the result list can show **Ready / Busy / Crowded**, playable-note count, and **Remap / Skip / Filter** counts before you save a permanent copy.

Selecting an online result stores a generated standard MIDI only in a bounded temporary cache and makes the normal **Play in BPSR** button work immediately. Temporary cache entries expire automatically. **Save to Local** creates a permanent `.mid` file in the Local library for offline use.

**Bookmark** stores only the Online Sequencer sequence ID/title in BPSR MIDI Lite. A bookmark may still need internet access when its temporary cache has expired; use **Save to Local** when you want a permanent offline file.

You can also paste a direct `onlinesequencer.net/<id>` link or sequence ID into the search box. Online Sequencer is a third-party service and this project is not affiliated with or endorsed by Online Sequencer. If their public search page changes, Local playback remains fully independent.

**Restore song speed to default 100%** returns only the song speed to the original MIDI tempo.
'''
text = replace_once(text, old_managing, new_managing, "README managing songs")
text = replace_once(
    text,
    "The release executable is built with PyInstaller from `modern_launcher.py`. Core MIDI planning lives in `midi_engine.py`; playback scheduling/input cleanup lives in `player.py`; instrument Category policy lives in `profiles.py`; the beginner interface lives in `modern_ui.py`.",
    "The release executable is built with PyInstaller from `modern_launcher.py`. Core MIDI planning lives in `midi_engine.py`; playback scheduling/input cleanup lives in `player.py`; instrument Category policy lives in `profiles.py`; the beginner interface lives in `modern_ui.py`; Online Sequencer networking/protobuf-to-MIDI conversion lives in `online_sequencer.py`, with its UI bridge isolated in `online_ui.py`.",
    "README development modules",
)
path.write_text(text, encoding="utf-8")


# --- CHANGELOG.md ---------------------------------------------------------
path = Path("CHANGELOG.md")
text = path.read_text(encoding="utf-8")
entry = '''# Changelog

## v3.0.0

- Added a built-in **Online Sequencer** browser beside the existing Local song library.
- Added public title search plus direct Online Sequencer URL / sequence-ID lookup.
- Online results are converted to temporary standard MIDI and analyzed by the existing BPSR planner before permanent download, showing Ready/Busy/Crowded and Remap/Skip/Filter counts.
- Added direct online playback from a bounded temporary cache; no permanent MIDI file is required to press Play.
- Added app-local **Bookmarks** and **Save to Local** for permanent/offline MIDI copies.
- Preserved Online Sequencer tempo changes and note lengths while converting the public sequence format; known Online Sequencer drum-kit instruments are written to MIDI channel 10 so the existing percussion filter still works.
- Added conservative network limits, lazy result analysis, automatic cache expiry, and failure isolation so Online Sequencer outages/site changes cannot break Local playback.
- Added parser/conversion tests and kept the existing Piano/Guitar/Bass fitting, no-page invariant, BPSR timing, and keyboard-input backends unchanged.
- Online Sequencer remains a third-party service; the integration uses public sequence/search data and does not require or store Online Sequencer login credentials.

'''
if not text.startswith("# Changelog\n\n"):
    raise RuntimeError("Unexpected CHANGELOG header")
text = entry + text[len("# Changelog\n\n"):]
path.write_text(text, encoding="utf-8")

print("Applied v3.0.0 Online Sequencer UI/version/docs migration")
