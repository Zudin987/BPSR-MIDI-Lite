# 🎹 BPSR MIDI Lite

A lightweight MIDI instrument player for **Blue Protocol: Star Resonance**.
Supports Keyboard, Guitar, and Bass.

Created by **MrEz**.

> **Windows 10/11, 64-bit.** Accept the Administrator prompt when opening the app. Administrator permission is required for reliable BPSR input.

## Download

### [⬇ Download BPSR-MIDI-Lite.exe](https://github.com/Zudin987/BPSR-MIDI-Lite/releases/latest/download/BPSR-MIDI-Lite.exe)

No installation, ZIP extraction, Python, or extra dependency is required.
Windows may show a SmartScreen warning because the EXE is not code-signed. Download it only from this repository's Releases page.

## What it does

BPSR MIDI Lite reads `.mid` and `.midi` files and converts their notes into keyboard input for BPSR's in-game instruments.

It is a single-purpose music utility. It does not automate combat, gathering, fishing, dungeons, or other gameplay.

## Main features

- Keyboard, Guitar, and Bass support
- Unlock-based instrument profiles
- Automatic song suitability check
- Automatic folding and remapping of unavailable notes
- Custom profile for advanced tuning and experimental full-range playback
- Guarded delay for `<` and `>` page changes
- MIDI folder and song website shortcuts
- `F10` emergency stop
- Automatic Windows light/dark theme
- Standalone Windows EXE

## Quick start

1. Download and open `BPSR-MIDI-Lite.exe`.
2. Accept the Administrator prompt.
3. Choose your instrument and matching unlock profile.
4. Click **Open MIDI folder** and add your `.mid` or `.midi` files.
5. Click **Refresh** and select a song.
6. Open the matching instrument in BPSR:
   - Keyboard/Guitar: middle page + Default octave
   - Bass: Default mode
7. Click **Play**, then focus BPSR during the countdown.
8. Press `F10` whenever you need to stop.

## Instrument profiles

| Instrument | Tier 1 | Tier 2 | Tier 3 | Custom |
|---|---|---|---|---|
| Keyboard | C3–B4 | C3–B6 | C2–B6 — recommended | Configurable; experimental A0–C8 |
| Guitar | C3–B4 | E2–B4 | E2–D6 | Configurable experimental range |
| Bass | E1–B2 | E1–B3 | — | Manual E1–B2 or E1–B3 |

Fixed profiles avoid the `<` and `>` page keys. Custom full-range playback may use them and adds a guarded wait before the next playable input.

## Choosing a MIDI

The app checks the selected song and labels it as:

- **Good fit** — should translate cleanly
- **Busy** — may sound crowded but can still work
- **Very complex** — likely to sound messy in-game

For better results, use piano, melody-only, acoustic, solo-instrument, easy, or simplified MIDI files. Dense orchestral, full-band, drum-heavy, impossible-piano, and Black MIDI arrangements usually do not translate well to the game's limited instrument range.

## Basic troubleshooting

### Nothing happens in BPSR

- Confirm that the Administrator prompt was accepted.
- Keep the game instrument window open.
- Check that the selected instrument and profile match your in-game unlock.
- Try another keyboard input method from the Playback panel.

### The song sounds strange

- Check the song suitability result.
- Try a simpler version of the MIDI.
- Try a lower fixed profile.
- In Custom, reduce chord detail.

## Notes

- Keep BPSR focused during playback.
- `F10` stops playback and releases all pressed keys.
- Suitability is guidance; the final result depends on the MIDI and the game's instrument behavior.
- Only use MIDI files you have permission to download and use.

## Credits

Created by **MrEz**.

Independent MIDI-only implementation inspired by `Sanheiii/ok-star-resonance`.

## Licence

Licensed under the GNU Affero General Public License v3.0. See [LICENSE](LICENSE).
