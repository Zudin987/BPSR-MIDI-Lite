# 🎹 BPSR MIDI Lite

A small Windows app that turns normal MIDI files into playable input for **Blue Protocol: Star Resonance** instruments.

Supports **Keyboard, Guitar, and Bass**.

Created by **MrEz**.

> **Windows 10/11, 64-bit.** Accept the Administrator prompt when the app opens. BPSR input is more reliable with Administrator permission.

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
3. Choose the range you have unlocked.
4. Click **Add MIDI…** and select a song.
5. Open the matching instrument in BPSR.
6. Click **Play in BPSR**.
7. Click back into BPSR during the countdown.

That is the normal workflow. There is no manual Refresh step and you do not need to understand MIDI ranges, page timing, input methods, or note-remapping settings.

Press **F10** at any time to stop playback and release held keys.

## Unlock choices

### Keyboard

- **Basic — C3 to B4**
- **Expanded — C3 to B6**
- **Full safe range — C2 to B6 (Recommended)**

### Guitar

- **Basic — C3 to B4**
- **Expanded — E2 to B4**
- **Full safe range — E2 to D6 (Recommended)**

### Bass

- **Basic — E1 to B2**
- **Full range — E1 to B3 (Recommended)**

Normal profiles avoid Keyboard/Guitar page changes. **Advanced setup…** keeps the experimental A0–C8 workflow available for users who specifically want it.

## Song check

After you select a song, the app checks it automatically and shows one simple result:

- **Ready to play**
- **Playable, but this song is busy**
- **This song may sound crowded**

Dense orchestral, full-band, drum-heavy, impossible-piano, and Black MIDI arrangements can still sound crowded because BPSR instruments have fewer playable inputs than a full MIDI arrangement.

## Settings

The main screen intentionally hides settings that most people should not touch.

Open **Settings** if you want to change the countdown, minimization behavior, Advanced song fitting, or troubleshooting tools. Keyboard input methods and support diagnostics are hidden inside **Troubleshooting**.

## Technical core

The v2 interface is a redesign of the user flow, not a replacement of the MIDI engine. The existing planner/player architecture remains responsible for:

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

The GitHub Actions workflow can run the test suite, build the standalone EXE, and optionally publish a release when a version is supplied manually.

## License

Licensed under the **GNU Affero General Public License v3.0**. See `LICENSE`.

Independent MIDI-only implementation inspired by `Sanheiii/ok-star-resonance`.
