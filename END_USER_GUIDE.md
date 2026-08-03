# End-user guide

## MIDI library folder

1. Run `BPSR-MIDI-Lite.exe`.
2. Click **Open Folder**. The app creates and opens a `MIDI` folder beside the EXE.
3. Copy any `.mid` or `.midi` songs into that folder. Subfolders are supported.
4. Return to the app and click **Reload**.
5. Choose a song from the dropdown.

Use **Choose Folder…** to select a different permanent library. The folder and last song are saved automatically. If the folder dialog seems missing while the game is open, v0.4.2 forces it in front of the app.


This guide is for people who only want to play MIDI files. They do not need to install Python.

## Install

### Portable ZIP

1. Download `BPSR-MIDI-Lite-Windows-x64.zip` from the repository's Releases page.
2. Right-click the ZIP and select **Extract All**.
3. Open the extracted folder.
4. Run `BPSR-MIDI-Lite.exe`.

### Direct EXE

Download `BPSR-MIDI-Lite.exe` and run it directly. No installer is used.

## First playback

1. Open BPSR and enter the piano interface.
2. Manually set the keyboard to the middle page and Default octave state.
3. In MIDI Lite, choose the unlock tier that matches your character:
   - Tier 1: C3–B4
   - Tier 2: C3–B6
   - Tier 3: A0–B6
   - Tier 4: A0–C8
4. Choose **Stable** mode for the first test.
5. Choose **Octave fold**.
6. Click **Open Folder**, copy your `.mid` or `.midi` files there, and click **Reload**.
7. Choose a song from the dropdown.
8. Press **Analyze** and check the played range and page-key count.
9. Press **Start** and switch to the game during the countdown.
10. Press **F10** at any time to stop.

## Which mode should I use?

- **Stable:** smoothest and safest; no `<` / `>`.
- **Full range solo:** preserves more unlocked notes and may use page switching.
- **Ensemble-safe:** keeps the timeline; unsafe page changes are remapped or skipped.

## Windows warning

A new unsigned EXE may show **Windows protected your PC** or **Unknown publisher**. Only run a copy obtained from the project's own GitHub Release, and compare its SHA-256 hash with `SHA256SUMS.txt` when possible. Do not bypass warnings for copies received from unknown mirrors or private messages.

## Input does not reach the game

- Click the game window during the countdown.
- Make sure the piano interface is active.
- Start from the middle page + Default octave state.
- Prefer running both the game and MIDI Lite normally, without Administrator mode.
- If the game itself is forced to run as Administrator, Windows may block input from a lower-privilege app. Changing the game back to normal privilege is the safer fix.

## Song sounds crowded

Try:

```text
Mode: Stable
Chord limit: Bass + top 2 notes
Ignore percussion: On
Speed: 80–90%
Note length: 140–170%
```

## Song sounds cut off

Raise **Note length** gradually. Keep repeated-note protection enabled through the app's default release gaps.

## Full-range song pauses too much

Lower **Page-switch delay** in small steps, such as 220 ms to 200 ms. If notes rush or occur before the page finishes changing, raise it again.


## First keyboard-input test

1. Launch the EXE and accept the Windows Administrator prompt.
2. Click **Test input (3s)**.
3. During the countdown, focus Notepad or open/focus the in-game piano.
4. The app sends `A S D F`.
5. If Notepad receives the letters but the game does not, verify that the piano interface is active and that no chat box is focused.
6. If the app says Administrator access is `No`, close it and use **Run as administrator**.

