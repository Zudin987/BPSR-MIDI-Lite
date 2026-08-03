# BPSR MIDI Lite v1.1.0 — User Guide

## First setup

1. Download `BPSR-MIDI-Lite.exe` from the latest GitHub Release.
2. Put the EXE in any convenient folder.
3. Run it normally. It no longer requests Administrator access automatically.
4. Click **Open Folder**.
5. Copy `.mid` or `.midi` files into the opened `MIDI` folder.
6. Click **Reload**.

## Choose the instrument first

### Keyboard

- Tier 1: C3–B4
- Tier 2: C3–B6
- Tier 3: C2–B6

Before Start, use the middle keyboard page and Default octave.

### Guitar

- Tier 1: C3–B4
- Tier 2: E2–B4
- Tier 3: E2–D6

Before Start, use the middle guitar page and Default octave. The app changes Low/High Octave when required.

### Bass

- Tier 1: E1–B2
- Tier 2: E1–B3

Before Start, open Bass in Default mode. Tier 2 automatically presses Shift for the High Octave layout. Bass has no Low Octave Ctrl mode.

## Song suitability

The preview shows one of these ratings:

- **Good fit:** the MIDI should translate cleanly.
- **Busy:** the MIDI may sound crowded.
- **Very complex:** a simpler version is strongly recommended.

The app also explains the main reasons, such as fast note density, large chords, many remapped notes, many tracks, drums, or frequent page switching.

Prefer simple piano, melody, acoustic, or solo-instrument arrangements. Dense orchestral, full-band, percussion-heavy, or multi-instrument files can still sound strange because the game has fewer playable keys and simultaneous-note limits.

## Playing

1. Select a MIDI from the song list.
2. Wait for the automatic preview to say Ready.
3. Open the selected instrument in BPSR.
4. Click Start.
5. Focus BPSR before the countdown ends.
6. Press F10 to stop at any time.

## Standard mode and Administrator mode

Run the app normally first. Standard mode should work when BPSR is also running normally.

When **Test input** works in Notepad but BPSR receives nothing, return to the app and click **Restart as Administrator**. Windows will show its normal UAC prompt, then the elevated copy will open.

Do not use Administrator mode unless it is needed.

## Copy diagnostics

Click **Copy diagnostics** before asking for help. Paste the copied report into Discord, GitHub, or a message to the tester. It contains useful settings and the last error but does not expose the full local MIDI path.

## Find Songs Online

The button opens Online Sequencer in your browser. Download a MIDI manually, copy it into the app MIDI folder, then click Reload.

## Custom profile

Custom reveals advanced controls for speed, note length, mapping and chord detail. Keyboard and Guitar also expose an experimental full range that may use `<` / `>` page switching. Bass Custom is limited to its known E1–B2 and E1–B3 layouts.

## Troubleshooting

- No input anywhere: use **Test input (3s)** with Notepad, then try another input method.
- Notepad works but BPSR does not: click **Restart as Administrator**.
- Wrong notes: confirm the selected instrument and unlock profile match the game.
- Bass Tier 2 sounds wrong: start from Bass Default mode; do not manually enable Shift first.
- New songs missing: place them in the MIDI folder and click Reload.
- Song sounds messy: look for a Good fit or simpler piano/solo MIDI.
- App looks too bright/dark: it follows the Windows app theme automatically.
