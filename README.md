# BPSR MIDI Lite v0.5.0

**Created by MrEz.**

A small Windows MIDI keyboard player made only for **Blue Protocol: Star Resonance** piano playback.

The finished EXE is portable. Ordinary users do **not** need Python, pip, Git, or an installer.

## New in v0.5.0: simple profiles

The app now opens in a beginner-friendly profile system:

| Profile | In-game unlock | Fixed behavior |
|---|---|---|
| Tier 1 | C3–B4 | Stable, no modifiers/pages, auto-transpose, bass + melody |
| Tier 2 | C3–B6 | Stable, Default + Shift, no page keys, balanced chords |
| Tier 3 | A0–B6 | Full-range solo, smart left/middle-page switching, all notes |
| Tier 4 | A0–C8 | Full-range solo, all pages, all notes |
| Custom | User-selected | Unlocks every advanced setting |

Tier profiles lock their playback settings. A Tier 1 user therefore cannot accidentally select Full range solo or another incompatible setup.

In **Custom**, Full range solo is automatically hidden for Tier 1 and Tier 2 because those tiers do not have side-page range to unlock.

## Cleaner interface

- MIDI preview updates automatically when the song, profile, or Custom setting changes.
- The redundant **Analyze** button was removed.
- The MIDI library uses one fixed `MIDI` folder beside the EXE.
- Only **Open Folder** and **Reload** are shown.
- Advanced music controls are hidden unless the user selects **Custom**.
- The preview uses plain language and warns when page switching is unusually frequent.

## MIDI library

1. Run `BPSR-MIDI-Lite.exe`.
2. Click **Open Folder**.
3. Copy `.mid` or `.midi` files into the opened `MIDI` folder.
4. Return to the app and click **Reload**.
5. Select a song from the dropdown.

Subfolders are supported and the last selected song is remembered.

## Before playback

1. Open the in-game piano.
2. Select the **middle keyboard page**.
3. Set the octave state to **Default**.
4. Select the profile matching the character's unlocked notes.
5. Press **Start** and focus the game during the countdown.
6. Press **F10** at any time for an emergency stop.

## Input test

The EXE requests Administrator access because Windows can block input sent to an elevated game.

Use **Test input (3s)** first. Focus Notepad or the game piano during the countdown. It should send `A S D F`.

Available input methods:

- Win32 scan code — recommended
- Pynput compatibility
- Win32 virtual key
- Legacy `keybd_event`

## Custom settings

Custom is intended for users who understand the trade-offs:

- **Playback style:** Stable, Full range solo, or Ensemble-safe.
- **Unlocked range:** Tier 1 through Tier 4.
- **Fit unavailable notes:** octave fold, nearest note, auto-transpose, or skip.
- **Chord detail:** all notes through melody-only simplification.
- **Speed / note length / minimum note:** musical timing controls.
- **Page delay / Ctrl-Shift lead:** input timing calibration.
- Optional sustain-pedal playback and percussion filtering.

## Build locally on Windows

Builder requirements only:

- 64-bit Python 3.12 with the `py` launcher
- Internet access during the first build

Double-click:

```text
build_exe.bat
```

The script runs the tests, builds the standalone EXE, and creates a portable ZIP in `release\`.

## Build through GitHub without installing Python

Upload the source to GitHub and run the included **Build Windows EXE** workflow. GitHub builds the Windows EXE for you.

Detailed instructions:

- [FIRST_TIME_GITHUB_GUIDE.md](FIRST_TIME_GITHUB_GUIDE.md)
- [END_USER_GUIDE.md](END_USER_GUIDE.md)

## Limitations

- A chord wider than one keyboard state cannot always be reproduced literally at one instant.
- Full-range page changes take real time in the game. Dense page-to-page passages may require timing compensation or remapping.
- Very dense orchestral MIDIs may sound better with a simplified chord setting in Custom.
- The project is unsigned, so Windows SmartScreen may initially show an unknown-publisher warning.
- Use keyboard automation responsibly and follow the game's rules.

## Licence and credit

Created by **MrEz**.

Independent MIDI-only implementation inspired by the keyboard behavior studied from `Sanheiii/ok-star-resonance`.

Distributed under **GNU AGPL-3.0**. Source code is included.
