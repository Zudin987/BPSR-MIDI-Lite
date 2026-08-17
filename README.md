# 🎹 BPSR MIDI Lite

A small Windows MIDI-to-keyboard player for Blue Protocol: Star Resonance Keyboard, Electric Guitar, and Electric Bass.

## Normal use

1. Choose the instrument.
2. Choose the BPSR **Category** you have unlocked.
3. Add/select a MIDI.
4. Leave **Song speed** at 100% for original tempo, or adjust it.
5. Press **Play in BPSR** and return to the game during the countdown. The app stays open.

F10 always stops playback and releases held keys.

## Safe category ranges

### Piano / Keyboard
- Category 1: starts C3–B4.
- Category 2: unlocks C5–B6; cumulative safe playback C3–B6.
- Category 3: unlocks A0–B2; the app uses C2–B6.
- Category 4: unlocks C7–C8; the app still uses C2–B6.

The C2–B6 cap is intentional so Piano only needs Default/Low/High octave on the middle page and never `<` or `>`.

### Electric Guitar
- Category 1: C3–B4.
- Category 2: unlocks E2–B2; cumulative safe playback E2–B4.
- Category 3: unlocks C5–D6; complete safe playback E2–D6.

### Electric Bass
- Category 1: E1–B2.
- Category 2: complete safe playback E1–B3 using Default/High Octave. Bass has no Low Octave mode.

## Raw MIDI — no remap

Raw MIDI is the last choice for every instrument. It does not transpose or octave-fold pitches and does not simplify large chords. If a pitch is outside the physical safe range, it is skipped because there is no playable no-page key for it. Raw mode still keeps the BPSR-safe short-note/retrigger timing and ignores the drum channel for pitched instruments.

## Octave toggles

Ctrl/Shift are treated as toggles. Pressing the active octave again returns to Default. High and Low can switch directly to each other without a forced Default step.

## More settings

More settings contains only countdown, song-folder/reset helpers, and Troubleshooting/input tools. There is no Advanced fitting panel and no Minimize-after-Play option.

## License

GNU AGPL-3.0. Created by MrEz.
