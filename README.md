# 🎹 BPSR MIDI Lite

A lightweight Windows MIDI player for **Blue Protocol: Star Resonance** Keyboard/Piano, Electric Guitar, and Electric Bass.

BPSR MIDI Lite converts normal MIDI notes into the game's keyboard controls, automatically fits notes to the selected unlock Category, switches Ctrl/Shift octave modes when needed, and keeps playback inside the safe no-page range so normal profiles never press `<` or `>`.

## Download

Use the latest **GitHub Release** and run `BPSR-MIDI-Lite.exe`. The executable requests Administrator permission because BPSR input is not consistently accepted from a lower-privilege process.

No Python installation is required for the release build.

## Quick start

1. Choose **Keyboard**, **Guitar**, or **Bass**, then choose the BPSR **Category** you have unlocked beside it.
2. Click **Open folder** and copy your `.mid` / `.midi` files into the song folder. The song list refreshes automatically.
3. Leave **Song speed** at `100%` for the original MIDI tempo, or adjust it.
4. Check **Song check** to see whether the song is ready and how many notes were remapped.
5. Set the **Countdown** if needed.
6. Press **Play in BPSR** and switch back to the game before the countdown ends.

The app stays open during playback. **F10** always stops playback and releases held keys.

## Interface

The app is one scrollable page so every control remains reachable on smaller displays or short windows.

- **Instrument** — instrument and unlocked Category are shown side-by-side.
- **Song** — select a MIDI, open the song folder, and change song speed if needed.
- **Song check** — shows readiness, playable-note count, remapped notes, skipped notes, and filtered/simplified notes.
- **Play** — countdown, Play, Stop, progress, and current status.
- **Help & recovery** — only two controls: restore recommended settings and choose the keyboard connection method.

There is no Advanced fitting screen. Mapping, chord handling, short-note compensation, octave timing, and other MIDI behavior are automatic per Category.

## Keyboard connection

The default is **Win32 scan code (recommended)**. All four input methods remain available because different Windows/game setups can behave differently:

- **Win32 scan code (recommended)** — direct Windows `SendInput` using keyboard scan codes.
- **Pynput compatibility** — uses the bundled pynput keyboard controller.
- **Win32 virtual key** — direct Windows `SendInput` using virtual-key values.
- **Legacy keybd_event** — older Windows keyboard injection fallback.

If the recommended method works, leave it unchanged.

## Managing songs

**Open folder** opens the MIDI library used by the app. Copy or remove `.mid` / `.midi` files there normally with File Explorer. The app checks the folder automatically and refreshes the song list when it changes, so there is no separate Add MIDI or Reload workflow.

**Restore song speed to default 100%** returns only the song speed to the original MIDI tempo.

## Safe Category ranges

### Keyboard / Piano

| Category | Game progression | Safe playback used by the app |
|---|---|---|
| 1 | Starts with C3–B4 | C3–B4 |
| 2 | Unlocks C5–B6 | C3–B6 |
| 3 | Unlocks A0–B2 | C2–B6 |
| 4 | Unlocks C7–C8 | C2–B6 |

Category 3 and 4 deliberately remain inside **C2–B6**. This lets the player use only Default/Low/High octave on the middle page and avoids `<` / `>` page switching.

### Electric Guitar

| Category | Game progression | Safe playback used by the app |
|---|---|---|
| 1 | Starts with C3–B4 | C3–B4 |
| 2 | Unlocks E2–B2 | E2–B4 |
| 3 | Unlocks C5–D6 | E2–D6 |

The complete Guitar range can be reached with Default/Low/High octave switching, so page keys are unnecessary.

### Electric Bass

| Category | Game progression | Safe playback used by the app |
|---|---|---|
| 1 | Starts with E1–B2 | E1–B2 |
| 2 | High range unlocked | E1–B3 |

Bass has no Low Octave mode; the player switches between Default and High only.

## Raw MIDI — no remap

`Raw MIDI — no remap` is the final profile for every instrument.

Raw mode:

- keeps original in-range MIDI pitches
- keeps full chords
- does not octave-fold or transpose pitches
- still uses the small BPSR-safe short-note/retrigger timing correction
- ignores the MIDI drum channel for pitched instruments
- skips pitches outside the instrument's safe no-page range instead of remapping them
- never uses `<` or `>`

A physically unavailable pitch must be skipped in Raw mode because the app cannot both preserve the original pitch and avoid page switching.

## Song check

Song Check gives a simple readiness result and useful conversion numbers:

- **Remapped** — notes moved into the selected Category's playable range
- **Skipped** — notes that cannot be played under the selected profile, especially in Raw mode
- **Filtered/simplified** — notes removed by instrument/chord/percussion rules

A high remap count is not automatically bad, but a simpler arrangement usually sounds more natural in BPSR than a dense orchestral or full-band MIDI.

## Octave switching

Ctrl and Shift are treated as toggles, matching BPSR behavior:

- pressing the active octave control again returns to Default
- High can switch directly to Low
- Low can switch directly to High
- no forced intermediate Default step is inserted

## Restore recommended settings

Restore returns the current instrument to its recommended Category, song speed to `100%`, countdown to `3` seconds, and keyboard connection to **Win32 scan code**.

## Development

The release executable is built with PyInstaller from `modern_launcher.py`. Core MIDI planning lives in `midi_engine.py`; playback scheduling/input cleanup lives in `player.py`; instrument Category policy lives in `profiles.py`; the beginner interface lives in `modern_ui.py`.

Run the test suite with:

```text
python -m pytest -q
```

Build the Windows executable with:

```text
pyinstaller --noconfirm --clean BPSR-MIDI-Lite.spec
```

## License

GNU AGPL-3.0. Created by **MrEz**. See `THIRD_PARTY_NOTICES.md` for attribution details.
