# 🎹 BPSR MIDI Lite

A small Windows app that turns normal MIDI files into playable input for **Blue Protocol: Star Resonance** instruments.

Supports **Keyboard, Guitar, and Bass**.

Created by **MrEz**.

> **Windows 10/11, 64-bit.** Accept the Administrator prompt when the app opens. BPSR input is more reliable with Administrator permission.

## Distribution

Prebuilt Windows binaries, when published, are attached only to GitHub Releases. This source repository and README intentionally do not contain direct executable or archive download links.

## What it does

BPSR MIDI Lite reads a `.mid` or `.midi` song and automatically adapts it to the selected BPSR instrument.

The important music behavior is automatic:

- notes outside the playable range are fitted into the selected range
- chords are simplified only when the selected instrument profile needs it
- note length and repeated notes are handled for reliable in-game playback
- MIDI sustain-pedal events can be preserved in Advanced setup
- Keyboard/Guitar experimental full range can use automatic page changes
- page changes are scheduled with protected timing so `<` / `>` input does not simply fire on top of the next note
- playback always returns the instrument to its normal state when it finishes or is stopped

The app is only for MIDI instrument playback. It does not automate combat, gathering, fishing, dungeons, or other gameplay systems.

## Quick start

1. Open **BPSR MIDI Lite**.
2. Choose **Keyboard**, **Guitar**, or **Bass**.
3. Choose **First unlock**, **Second unlock**, or **Fully unlocked** as shown for that instrument.
4. Click **Add MIDI…** and select a song.
5. Leave **Song speed** at **100%** for the original MIDI tempo, or adjust it if you want the song slower/faster.
6. Open the matching instrument in BPSR.
7. Click **Play in BPSR** and click back into BPSR during the countdown.

That is the normal workflow. There is no manual Refresh step and you do not need to understand note ranges, page timing, input methods, or note-remapping settings.

Press **F10** at any time to stop playback and release held keys.

## Unlock choices

Keyboard and Guitar show **First unlock**, **Second unlock**, and **Fully unlocked (Recommended)**. Bass shows **First unlock** and **Fully unlocked (Recommended)**.

The exact note ranges are intentionally hidden from the normal interface. The app already knows the correct range for each choice. **Advanced setup…** keeps the experimental full-range workflow available for users who specifically need it.

**Song speed is independent from the unlock choice.** Switching between unlock tiers or instruments keeps the speed you selected instead of resetting it.

## Song check

After you select a song, the app checks it automatically and shows one simple result:

- **Ready to play**
- **Playable, but this song is busy**
- **This song may sound crowded**

Dense orchestral, full-band, drum-heavy, impossible-piano, and Black MIDI arrangements can still sound crowded because BPSR instruments have fewer playable inputs than a full MIDI arrangement.

## Settings

There is no separate Settings window. Click **More settings** and the extra controls expand inside the main app window. Click **Hide settings** to collapse them again.

The same-window settings area contains countdown, minimize-after-Play, song-library tools, Advanced song fitting when **Advanced setup…** is selected, and a collapsible **Troubleshooting** area for keyboard input methods, input testing, and support information.

**Song speed stays on the normal Song section** because it is useful for every unlock tier.

## Technical core

The planner keeps the MIDI's original tempo and authored note lengths by default. Only unusually short notes are extended to a small 70 ms input-safe hold, and repeated use of the same game key gets a brief release window so BPSR can retrigger it cleanly. This avoids slowing or stretching an entire song just to compensate for keyboard-input behavior.

The existing planner/player architecture remains responsible for:

- MIDI timing
- instrument-specific playable ranges
- octave/remapping logic
- chord handling
- sustain
- repeated-note cleanup
- modifier changes
- guarded page switching and timing compensation

## Building

The Windows release is built with PyInstaller from `BPSR-MIDI-Lite.spec`.

The GitHub Actions workflow runs the test suite and builds the standalone EXE for pull requests. A release is only published when a version is supplied in a manual workflow run.

## License

Licensed under the **GNU Affero General Public License v3.0**. See `LICENSE`.

Independent MIDI-only implementation inspired by `Sanheiii/ok-star-resonance`.