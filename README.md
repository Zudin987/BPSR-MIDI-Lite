# BPSR MIDI Lite v1.1.1

A small Windows MIDI instrument player for **Blue Protocol: Star Resonance**, created by **MrEz**.

The app reads ordinary `.mid` / `.midi` files and sends the matching keyboard input to the selected in-game instrument. The standalone EXE already contains Python and its required libraries.

## Download

Open the latest GitHub Release and download:

`BPSR-MIDI-Lite.exe`

No ZIP extraction, Python installation, or setup wizard is required.

Requirements: **Windows 10 or Windows 11, 64-bit**.

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
- `Find Songs Online` opens the Online Sequencer search page
- Automatic song preview and **Good fit / Busy / Very complex** suitability rating
- Clear reasons when a MIDI is dense, chord-heavy, heavily remapped, or track-heavy
- Automatic octave folding / transposition for unavailable notes
- Configurable chord simplification in Custom
- Mandatory Administrator launch so BPSR reliably receives keyboard input
- **Copy diagnostics** button for easy bug reports
- Four Windows input backends
- F10 emergency stop
- Automatic Windows light/dark theme
- Standalone Windows EXE through PyInstaller

## Basic use

1. Run `BPSR-MIDI-Lite.exe` and accept the Windows Administrator prompt.
2. Choose **Keyboard**, **Guitar**, or **Bass**.
3. Choose the tier matching your in-game unlock.
4. Click **Open Folder** and place MIDI files inside the `MIDI` folder.
5. Click **Reload** and choose a song.
6. Check the automatic suitability rating.
7. Open the matching instrument in BPSR in its normal starting mode:
   - Keyboard/Guitar: middle page + Default octave
   - Bass: Default mode
8. Press **Start**, focus the game during the countdown, and keep the game focused.
9. Press **F10** to stop.

Administrator access is required because BPSR did not reliably accept simulated input from a standard-permission process during real testing.

## Song suitability

The rating is a practical estimate based on note speed, chord size, how many notes must be remapped or removed, MIDI track count, percussion content, and page-switch pressure.

- **Good fit:** should translate cleanly.
- **Busy:** may sound crowded but can still be worth trying.
- **Very complex:** likely to sound messy; find a simpler piano, melody, acoustic, or solo-instrument version.

The rating is guidance, not a guarantee. Listening in-game is still the final test.

## Find songs online

The button opens:

`https://onlinesequencer.net/sequences`

Download there manually, move the MIDI into the app's `MIDI` folder, then press Reload. The app does not scrape or download from the website.

## Troubleshooting and diagnostics

Use **Test input (3s)** with Notepad first. When reporting a problem, click **Copy diagnostics** and paste the report together with a short explanation of what happened. The report includes the app version, Windows version, instrument/profile, input method, MIDI analysis, last input-test result, and last error. It does not include the full MIDI folder path.

## Credits and licence

Created by **MrEz**. Independent MIDI-only implementation inspired by `Sanheiii/ok-star-resonance`.

Licensed under **AGPL-3.0**.
