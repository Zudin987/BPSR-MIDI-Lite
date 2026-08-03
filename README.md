# BPSR MIDI Lite v1.0.0

A small Windows MIDI keyboard player for **Blue Protocol: Star Resonance**, created by **MrEz**.

The app reads ordinary `.mid` / `.midi` files and sends the matching keyboard input to the selected in-game instrument. The compiled EXE contains Python and its required libraries, so end users do not install Python.

## Supported instruments

### Keyboard

| Profile | Playable range | Behavior |
|---|---:|---|
| Tier 1 | C3–B4 | Default only |
| Tier 2 | C3–B6 | Default + Shift |
| Tier 3 | C2–B6 | Ctrl + Default + Shift; recommended |
| Custom | Configurable | Experimental A0–C8 full range may use `<` / `>` |

### Guitar

| Profile | Playable range | Behavior |
|---|---:|---|
| Tier 1 | C3–B4 | Default only |
| Tier 2 | E2–B4 | Low Octave (Ctrl) + Default |
| Tier 3 | E2–D6 | Low Octave + Default + High Octave |
| Custom | Configurable | Experimental full range may use `<` / `>` |

### Bass

| Profile | Playable range | Behavior |
|---|---:|---|
| Tier 1 | E1–B2 | Bass Default layout |
| Tier 2 | E1–B3 | Bass High Octave (Shift) layout |
| Custom | E1–B2 or E1–B3 | Manual mapping, speed and chord settings |

Bass has no Low Octave (Ctrl) mode. In Bass Tier 2, the app enables Shift at playback start and resets it afterward.

All fixed profiles remain on the middle page and produce **zero `<` / `>` presses**.

## Main features

- Keyboard, Guitar and Bass profiles
- MIDI folder library with Open Folder and Reload
- `Find Songs Online` opens the Online Sequencer search page in the default browser
- Automatic MIDI preview whenever the song, instrument or profile changes
- Automatic octave folding / transposition for unavailable notes
- Configurable chord simplification in Custom
- 150% note length by default for Keyboard and Guitar
- Bass-oriented lowest-note chord handling
- Four Windows input backends
- F10 emergency stop
- Automatic Windows light/dark theme
- Standalone Windows EXE through PyInstaller

## Basic use

1. Run `BPSR-MIDI-Lite.exe` and accept the Administrator prompt.
2. Choose **Keyboard**, **Guitar**, or **Bass**.
3. Choose the tier matching your in-game unlock.
4. Click **Open Folder** and place MIDI files inside the `MIDI` folder.
5. Click **Reload** and choose a song.
6. Open the matching instrument in BPSR in its normal starting mode:
   - Keyboard/Guitar: middle page + Default octave
   - Bass: Default mode
7. Press **Start**, focus the game during the countdown, and keep the game focused.
8. Press **F10** to stop.

## Find songs online

The button only opens:

`https://onlinesequencer.net/sequences`

Search and download there manually, move the MIDI into the app's `MIDI` folder, then press Reload. The app does not scrape or download from the website.

### Choose suitable MIDI files

Prefer **simple piano, melody, acoustic, or solo-instrument arrangements**. Very dense orchestral, full-band, drum-heavy, or multi-instrument MIDI files may sound crowded or strange after being fitted to the game's limited keys and chord handling. Simpler arrangements usually give the best result.

## Public Windows download

Open the latest GitHub Release and download:

`BPSR-MIDI-Lite.exe`

No ZIP extraction, Python installation, or setup wizard is required. Run the EXE, accept the Administrator prompt, then click **Open Folder** to access the automatically created MIDI folder.

Requirements: **Windows 10 or Windows 11, 64-bit**.

## Credits and licence

Created by **MrEz**. Independent MIDI-only implementation inspired by `Sanheiii/ok-star-resonance`.

Licensed under **AGPL-3.0**.
