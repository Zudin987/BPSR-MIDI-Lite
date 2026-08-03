# BPSR MIDI Lite v0.5.0 — End-user guide

Created by **MrEz**.

## Install

No installation is required. Extract the portable ZIP and run:

```text
BPSR-MIDI-Lite.exe
```

Accept the Administrator prompt. Python is not required.

## Add songs

1. Click **Open Folder**.
2. Copy `.mid` or `.midi` files into the opened `MIDI` folder.
3. Click **Reload**.
4. Select the song from the dropdown.

The preview updates automatically; there is no Analyze button.

## Choose a profile

- **Tier 1 — C3–B4:** for a new character. Simple and page-free.
- **Tier 2 — C3–B6:** Default + Shift, still no page switching.
- **Tier 3 — A0–B6:** smart full-range playback using left/middle pages.
- **Tier 4 — A0–C8:** complete unlocked range.
- **Custom:** exposes advanced playback and MIDI-fitting settings.

Tier profiles are locked to prevent incompatible choices.

## Play

1. Open the BPSR piano.
2. Set the **middle page + Default octave**.
3. Press **Start**.
4. Focus the game during the countdown.
5. Press **F10** to stop.

## Check input

Click **Test input (3s)** and focus Notepad. It should type `asdf`.

Start with **Win32 scan code**. Try another input method only when the recommended method does not work with the game.

## Song preview

The preview shows:

- played note count and duration
- original and played pitch ranges
- how many notes were remapped, skipped, or simplified
- predicted `<` / `>` page-key presses
- Ctrl/Shift changes and timing compensation

A warning appears when a song needs unusually frequent page switching.
