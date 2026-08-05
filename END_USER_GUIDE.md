# BPSR MIDI Lite — User Guide

## Before you start

- Use Windows 10 or Windows 11, 64-bit.
- Accept the Administrator prompt when opening the app.
- Download MIDI files only from sources you trust and have permission to use.

## Play a song

1. Choose **Keyboard**, **Guitar**, or **Bass**.
2. Choose the profile matching your in-game unlock.
3. Click **Open MIDI folder** and add `.mid` or `.midi` files.
4. Click **Refresh** and select a song.
5. Open the matching instrument in BPSR:
   - Keyboard/Guitar: middle page + Default octave
   - Bass: Default mode
6. Click **Play**.
7. Focus BPSR before the countdown ends.

Press `F10` at any time to stop playback and release all keys.

## Profiles

Fixed profiles are recommended because they use safe note ranges and avoid the `<` and `>` page keys.

Custom is for advanced tuning. Full-range Custom modes may change pages, so the app waits briefly before playing the following note. Later notes are shifted by the same amount instead of rushing to catch up.

## Song check

The selected MIDI is rated automatically:

- **Good fit** — should translate cleanly
- **Busy** — may sound crowded
- **Very complex** — likely to sound messy in-game

Simple piano, melody, acoustic, and solo-instrument MIDI files usually work best.

## Playback settings

- **Countdown** gives you time to focus BPSR before playback begins.
- **Minimize app after Play** hides the app after starting.
- **Keyboard input** controls how Windows sends keys to the game. Keep the recommended scan-code method unless it does not work on your system.
- **Restore defaults** resets the normal app and Custom-profile settings.

## Themes

Use the dropdown below the version badge to switch themes immediately:

- Light
- Dark
- Dracula
- Nord
- Catppuccin Mocha
- Solarized Dark
- Tokyo Night

The selected theme is saved automatically and restored the next time the app opens.

## Custom profile

### Notes tab

- **Playback mode** selects safe-range or experimental full-range playback.
- **Unlocked range** matches your in-game instrument unlock.
- **Chord detail** limits simultaneous notes when a MIDI is too dense.
- **Fit unavailable notes** controls how notes outside the game range are handled.
- **Ignore drum channel** removes MIDI percussion.
- **Use MIDI sustain pedal** follows sustain events stored in the MIDI.

### Timing tab

- **Page-change wait** gives BPSR time to finish changing pages.
- **Ctrl / Shift lead** sends octave controls slightly before their notes.
- **Speed** changes overall playback speed.
- **Note length** changes how long notes are held.
- **Minimum note** prevents extremely short taps.

## Common problems

### Nothing happens

- Confirm the app was opened with Administrator permission.
- Keep the in-game instrument open.
- Make sure the selected instrument and profile match your unlock.
- Try another **Keyboard input** method.

### The song sounds crowded or strange

- Try a simpler MIDI.
- Use a fixed profile.
- Reduce **Chord detail** in Custom.
- Avoid full-band, orchestral, drum-heavy, impossible-piano, and Black MIDI files.

## Important notes

- Keep BPSR focused during playback.
- Press `F10` for an emergency stop.
- The song check is guidance, not a guarantee.
- The game may still limit or delay extremely dense input.
