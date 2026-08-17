# 🎹 BPSR MIDI Lite

A lightweight Windows MIDI player for **Blue Protocol: Star Resonance** Keyboard/Piano, Electric Guitar, and Electric Bass.

BPSR MIDI Lite converts normal MIDI notes into the game's keyboard controls, automatically fits notes to the selected unlock Category, switches Ctrl/Shift octave modes when needed, and keeps playback inside the safe no-page range so normal profiles never press `<` or `>`.

## Download

Use the latest **GitHub Release** and run `BPSR-MIDI-Lite.exe`. The executable requests Administrator permission because BPSR input is not consistently accepted from a lower-privilege process.

No Python installation is required for the release build.

## Quick start

1. Choose **Keyboard**, **Guitar**, or **Bass**.
2. Choose the BPSR **Category** you have unlocked.
3. Click **Add MIDI…** and select one or more `.mid` / `.midi` files.
4. Leave **Song speed** at `100%` for the original MIDI tempo, or adjust it.
5. Check **Song check** to see whether the song is ready and how many notes were remapped.
6. Set the **Countdown** if needed.
7. Press **Play in BPSR** and switch back to the game before the countdown ends.

The app stays open during playback. **F10** always stops playback and releases held keys.

## Interface

The app is intentionally one scrollable page so every control remains reachable on smaller displays or short windows.

- **Instrument** — choose the game instrument and your unlocked Category.
- **Song** — add/select a MIDI and optionally change playback speed.
- **Song check** — shows readiness, playable-note count, remapped notes, skipped notes, and filtered/simplified notes.
- **Play** — countdown, Play, Stop, progress, and current status.
- **Help & recovery** — restore recommended settings or expand Troubleshooting when keyboard injection is not working.

There is no Advanced fitting screen. Mapping, chord handling, short-note compensation, octave timing, and other technical behavior are automatic per Category.

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

## Troubleshooting

Expand **Troubleshooting** only when BPSR does not react to playback.

1. Run **Test keyboard input**.
2. Confirm the app is running with Administrator permission.
3. If needed, try another **Keyboard connection** method.
4. Use **Copy support info** when reporting a problem.
5. **Restore recommended settings** returns the app to the normal profile, 100% song speed, 3-second countdown, and recommended input backend.

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
