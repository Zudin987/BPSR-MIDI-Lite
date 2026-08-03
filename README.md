# BPSR MIDI Lite v0.5.2

**Created by MrEz.**

A small Windows MIDI keyboard player made only for **Blue Protocol: Star Resonance** piano playback.

The finished EXE is portable. Ordinary users do **not** need Python, pip, Git, or an installer.

## Simple profiles

| Profile | In-game unlock | Fixed behavior |
|---|---|---|
| Tier 1 | C3–B4 | Beginner preset, no modifiers or page keys, auto-transpose, bass + melody |
| Tier 2 | C3–B6 | Default + Shift, no page keys, balanced chords |
| Tier 3 | C2–B6 | Ctrl + Default + Shift, all notes, guaranteed no `<` / `>` presses |
| Custom | User-selected | Unlocks every advanced setting, including experimental A0–C8 page switching |

Tier 1–3 lock their music settings so new users cannot accidentally choose an incompatible mode.

**Tier 3 C2–B6 is the recommended normal profile.** The entire range is available on the middle keyboard page using Ctrl / Default / Shift, so the app never needs `<` or `>`.

Use **Custom → Full range A0–C8** only when you deliberately want to test low/high page switching.

## Windows light and dark theme

The interface follows the Windows app-theme setting automatically:

- Windows light mode → light app
- Windows dark mode → dark app
- Changing the Windows theme while the app is open is detected automatically

There is no separate theme setting to maintain.

## MIDI library

1. Run `BPSR-MIDI-Lite.exe`.
2. Click **Open Folder**.
3. Copy `.mid` or `.midi` files into the opened `MIDI` folder.
4. Return to the app and click **Reload**.
5. Select a song from the dropdown.

Subfolders are supported and the last selected song is remembered. The song preview updates automatically.

## Find songs online

Click **Find Songs** to open the optional Online Sequencer browser:

1. Search a song name.
2. Double-click a result to preview its public sequence page.
3. Select a result and click **Download selected MIDI**.
4. The app converts that public sequence into a standard MIDI and saves it under `MIDI\Online Sequencer`.
5. The new song is reloaded and selected automatically.

You can also paste an Online Sequencer URL or numeric sequence ID directly. The integration makes one request at a time and does not bulk-download sequences. It depends on Online Sequencer's public website and the protobuf endpoint used by its official open-source SequencePlayer project, so a future website change may temporarily break search or import. Use only public sequences and respect their creators' rights and the site's rules.

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
- **Unlocked range:** Tier 1, Tier 2, Tier 3 C2–B6, or Full range A0–C8.
- **Fit unavailable notes:** octave fold, nearest note, auto-transpose, or skip.
- **Chord detail:** all notes through melody-only simplification.
- **Speed / note length / minimum note:** musical timing controls.
- **Page delay / Ctrl-Shift lead:** input timing calibration.
- Optional sustain-pedal playback and percussion filtering.

Full range solo is only available with Custom A0–C8. Tier 1–3 remain page-free even inside Custom.

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
- Custom A0–C8 page changes take real time in the game. Dense page-to-page passages may require timing compensation or remapping.
- Very dense orchestral MIDIs may sound better with a simplified chord setting in Custom.
- Online Sequencer search/import requires an internet connection and may stop working if the third-party site changes.
- Imported Online Sequencer automation is limited to BPM changes; instrument effects and pitch bends are not reproduced in the MIDI.
- The project is unsigned, so Windows SmartScreen may initially show an unknown-publisher warning.
- Use keyboard automation responsibly and follow the game's rules.

## Licence and credit

Created by **MrEz**.

Independent MIDI-only implementation inspired by the keyboard behavior studied from `Sanheiii/ok-star-resonance`.

Distributed under **GNU AGPL-3.0**. Source code is included.
