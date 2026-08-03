# BPSR MIDI Lite v0.4.2

A small Windows MIDI keyboard player made only for **Blue Protocol: Star Resonance** piano playback.


## Important: Administrator access

The Windows EXE requests Administrator access at launch. This is intentional: BPSR or its launcher may run elevated, and Windows prevents a lower-privilege process from injecting keyboard input into an elevated game.

Before testing a MIDI, use **Test input (3s)**. Focus Notepad or the in-game piano during the countdown. The app sends `A S D F`. If the test works in Notepad but not in BPSR, ensure the game piano is open and the game window is focused.


## New in v0.4.2: saved MIDI library

- The app creates a `MIDI` folder beside the EXE on first launch.
- Put any `.mid` or `.midi` file in that folder, including inside subfolders.
- Click **Reload** and choose the song from the dropdown.
- **Open Folder** opens the active library directly in File Explorer.
- **Choose Folder…** lets you use another folder, and the choice is remembered.
- The last selected song and all playback settings are also remembered.

It reads ordinary `.mid` and `.midi` files directly and sends the matching keyboard input to the game. End users do **not** need Python after you build the EXE.

## Unlock-tier presets

Choose the exact progress of the player using the app:

| Preset | Unlocked notes | Player behavior |
|---|---:|---|
| Tier 1 — Beginner | C3–B4 | Default keyboard state only; no Ctrl, Shift, `<`, or `>` |
| Tier 2 | C3–B6 | Default + Shift; no `<` or `>` |
| Tier 3 | A0–B6 | Uses the left and middle pages when the selected mode allows pages; never uses the unnecessary right page |
| Tier 4 — Full unlock | A0–C8 | All available pages and octave states |

Any loaded MIDI is automatically fitted to the selected tier using the chosen mapping method. You no longer need to manually convert each song first.

## Playback modes

### Stable

- Never presses `<` or `>`.
- Best default for smooth playback.
- Uses the safe middle-page subset available at the selected tier:
  - Tier 1: C3–B4
  - Tier 2: C3–B6
  - Tier 3/4: C2–B6
- Out-of-range notes are folded, clamped, transposed, or skipped according to the selected mapping method.

### Full range solo

- Preserves more of the original MIDI inside the selected unlock tier.
- Tier 1 and Tier 2 still use no page keys.
- Tier 3 can use only the left and middle pages.
- Tier 4 can use all pages.
- Page changes are scheduled during gaps where possible.
- When a page animation cannot fit, the solo timeline is extended instead of rushing overdue notes.

### Ensemble-safe

- Keeps the source timeline.
- Changes page only when an existing gap is long enough.
- Unsafe notes are remapped or skipped instead of delaying the whole performance.

## Mapping methods

- **Octave fold:** recommended; preserves note names.
- **Nearest playable note:** clamps outliers to the nearest available note.
- **Auto-transpose then fold:** searches for a song-wide transpose before local folding.
- **Skip out-of-range notes:** preserves timing by dropping impossible notes.

## Other features

- Default 85% playback speed.
- Default 150% note duration.
- Repeated-note retrigger protection.
- Chord simplification for dense or orchestral MIDI files.
- Optional sustain-pedal playback.
- Percussion-channel filtering.
- F10 emergency stop.
- MIDI analysis before playback.
- Automatic return to middle page + Default state after playback.
- No screen recognition, account login, network connection, or game-file modification.

## Before playback

1. Open the in-game piano.
2. Select the **middle keyboard page**.
3. Set the octave state to **Default**.
4. Open BPSR MIDI Lite.
5. Click **Open Folder**, copy your MIDI files into the library, and click **Reload**.
6. Select the unlock tier matching your character.
7. Choose a song from the dropdown and press **Analyze**.
8. Press **Start**, then switch to the game during the countdown.

## Recommended first settings

```text
Unlock tier: match your character
Mode: Stable
Mapping: Octave fold
Chord limit: All notes
Speed: 85%
Note length: 150%
Minimum note: 120 ms
Ignore percussion: On
```

Use **Full range solo** only when preserving low/high unlocked notes matters more than exact total song duration.

## Downloads and installation

After a Windows EXE is built, ordinary users only need:

```text
BPSR-MIDI-Lite.exe
```

They do not need Python, pip, Git, or an installer. They can also download the portable ZIP, extract it, and run the EXE inside.

See:

- [END_USER_GUIDE.md](END_USER_GUIDE.md)
- [FIRST_TIME_GITHUB_GUIDE.md](FIRST_TIME_GITHUB_GUIDE.md)

## Build locally on Windows

Builder requirements only:

- 64-bit Python 3.12 with the `py` launcher.
- Internet access during the first build so dependencies can be downloaded.

Then double-click:

```text
build_exe.bat
```

The script creates:

```text
dist\BPSR-MIDI-Lite.exe
release\BPSR-MIDI-Lite.exe
release\BPSR-MIDI-Lite-v0.4.2-Windows-x64.zip
release\SHA256SUMS.txt
```

## Build without installing Python

Upload the source project to GitHub and use the included **Build Windows EXE** workflow. GitHub runs the Windows build for you. Detailed browser-only instructions are in [FIRST_TIME_GITHUB_GUIDE.md](FIRST_TIME_GITHUB_GUIDE.md).

## Command-line analysis

```text
python app.py --dry-run song.mid --unlock-tier tier1 --mode stable
python app.py --dry-run song.mid --unlock-tier tier2 --mode full
python app.py --dry-run song.mid --unlock-tier tier3 --mode ensemble
python app.py --dry-run song.mid --unlock-tier tier4 --mode full --page-delay 250
```

## Limitations

- A chord wider than one current keyboard state cannot be played literally at one instant.
- Full-range page changes take real time inside the game. Dense page-to-page passages may require compensation, remapping, or skipped notes.
- Very dense orchestral MIDI files may need chord limiting or melody-only mode.
- This project is unsigned. Windows SmartScreen may initially show an unknown-publisher warning for newly built releases.
- Keyboard automation may be restricted by game rules. Use responsibly and at your own risk.

## Licence

Independent MIDI-only implementation inspired by the keyboard behavior studied from `Sanheiii/ok-star-resonance`.

Distributed under **GNU AGPL-3.0**. Source code is included.

## v0.4.3 input troubleshooting

v0.4.3 fixes a Win32 structure-size bug that prevented v0.4.2 from sending
input even to Notepad on 64-bit Windows.

Use **Test input (3s)** with Notepad first. Start with **Win32 scan code**. If
Notepad works but BPSR does not, try **Pynput compatibility**, then **Win32
virtual key**. Run the app as Administrator when BPSR is elevated.
