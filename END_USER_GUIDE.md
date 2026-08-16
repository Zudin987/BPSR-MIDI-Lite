# BPSR MIDI Lite — Beginner Guide

## Normal use

You only need four things on the main screen:

1. **Instrument** — choose Keyboard, Guitar, or Bass.
2. **Unlocked range** — choose the highest range you actually have unlocked in BPSR.
3. **Song** — click **Add MIDI…** once and choose a `.mid` or `.midi` file.
4. **Play** — open the matching BPSR instrument and click **Play in BPSR**.

During the countdown, click back into BPSR. Keep BPSR focused while the song is playing.

Press **F10** at any time to stop. The app releases held keys and returns the instrument to its normal state.

## Which unlocked range should I choose?

Use the highest option that matches what you have unlocked in the game.

### Keyboard

- Basic — C3 to B4
- Expanded — C3 to B6
- Full safe range — C2 to B6 (Recommended when unlocked)

### Guitar

- Basic — C3 to B4
- Expanded — E2 to B4
- Full safe range — E2 to D6 (Recommended when unlocked)

### Bass

- Basic — E1 to B2
- Full range — E1 to B3 (Recommended when unlocked)

The normal profiles automatically fit notes into the selected range. You do not need to set note-remapping rules yourself.

## Adding songs

Click **Add MIDI…** and choose one or more MIDI files.

The app copies them into its song library, refreshes the list, selects the newest added song, and checks it automatically. You do not need to manually copy files into a folder or press Refresh.

Use **Open folder** only if you want to manage the library yourself.

## Song check

The app shows a simple result before playback:

- **Ready to play** — the song should fit reasonably well.
- **Playable, but this song is busy** — it can work, but some parts may sound crowded.
- **This song may sound crowded** — the MIDI is much denser than a BPSR instrument can reproduce cleanly.

Simple piano, melody, acoustic, and solo-instrument MIDI arrangements usually work best.

## Where did all the old settings go?

They are still available, but they no longer block the normal workflow.

Open **Settings** for:

- countdown length
- minimize-after-Play
- Advanced song fitting
- troubleshooting

Inside **Troubleshooting** you can change the keyboard input method, test keyboard input, or copy support information.

## Advanced setup

Choose **Advanced setup…** only if you know why you need it.

This keeps the existing custom controls for song speed, note length, chord detail, sustain, mapping behavior, and experimental full-range playback.

For Keyboard and Guitar, the experimental full range can use automatic page changes. The app schedules those changes with the configured wait time and protects the following notes from being sent too early.

## If playback does not work

1. Make sure BPSR MIDI Lite was opened with Administrator permission.
2. Open the correct BPSR instrument before pressing Play.
3. During the countdown, click back into BPSR.
4. Open **Settings → Troubleshooting → Test keyboard input**.
5. If needed, try another Keyboard connection option.
6. Use **Copy support info** when reporting a problem.

## Safety stop

**F10** is always the emergency stop during playback. It stops the song, releases held keys, resets octave state, and returns page position to the normal middle page when required.
