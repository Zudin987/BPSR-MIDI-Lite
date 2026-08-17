# BPSR MIDI Lite — Beginner Guide

## Normal use

You only need four things on the main screen:

1. **Instrument** — choose Keyboard, Guitar, or Bass.
2. **How much you unlocked** — choose First unlock, Second unlock, or Fully unlocked when available.
3. **Song** — click **Add MIDI…** once and choose a `.mid` or `.midi` file. Leave **Song speed** at 100% for the original tempo, or change it when you want slower/faster playback.
4. **Play** — open the matching BPSR instrument and click **Play in BPSR**.

During the countdown, click back into BPSR. Keep BPSR focused while the song is playing.

Press **F10** at any time to stop. The app releases held keys and returns the instrument to its normal state.

## Which unlock should I choose?

Use the highest choice that matches your progress in the game.

- Keyboard: **First unlock**, **Second unlock**, or **Fully unlocked (Recommended)**.
- Guitar: **First unlock**, **Second unlock**, or **Fully unlocked (Recommended)**.
- Bass: **First unlock** or **Fully unlocked (Recommended)**.

The app already knows the exact playable notes for each choice and automatically fits the song to them. You do not need to understand the note ranges yourself.

Your **Song speed is separate from the unlock choice**. If you set a song to 80%, changing from First unlock to Fully unlocked will keep it at 80%.

## Adding songs

Click **Add MIDI…** and choose one or more MIDI files.

The app copies them into its song library, refreshes the list, selects the newest added song, and checks it automatically. You do not need to manually copy files into a folder or press Refresh.

Use **Open folder** only if you want to manage the library yourself.

## Song speed

**100%** means the original MIDI tempo.

- Below 100% plays the song slower.
- Above 100% plays the song faster.
- **Reset to 100%** returns to the original tempo.

Song speed is available for every normal unlock tier and Advanced setup. It is remembered separately from the selected instrument/profile.

## Song check

The app shows a simple result before playback:

- **Ready to play** — the song should fit reasonably well.
- **Playable, but this song is busy** — it can work, but some parts may sound crowded.
- **This song may sound crowded** — the song is much denser than a BPSR instrument can reproduce cleanly.

Simple piano, melody, acoustic, and solo-instrument arrangements usually work best.

## Where are the other settings?

Click **More settings**. The extra controls expand inside the same app window; no second Settings window opens.

The same-window area contains:

- countdown length
- minimize-after-Play
- song-library/reset tools
- Advanced song fitting when **Advanced setup…** is selected
- a collapsible **Troubleshooting** section

Click **Hide settings** when you are done.

Inside **Troubleshooting** you can change the keyboard input method, test keyboard input, or copy support information.

## Advanced setup

Choose **Advanced setup…** only if you know why you need it.

This keeps the custom controls for note length, minimum note time, chord detail, sustain, mapping behavior, and experimental full-range playback. **Song speed stays on the normal Song section instead of being hidden here.**

For Keyboard and Guitar, the experimental full range can use automatic page changes. The app schedules those changes with the configured wait time and protects the following notes from being sent too early.

## If playback does not work

1. Make sure BPSR MIDI Lite was opened with Administrator permission.
2. Open the correct BPSR instrument before pressing Play.
3. During the countdown, click back into BPSR.
4. Click **More settings → Troubleshooting → Test keyboard input**.
5. If needed, try another Keyboard connection option.
6. Use **Copy support info** when reporting a problem.

## Safety stop

**F10** is always the emergency stop during playback. It stops the song, releases held keys, resets the instrument mode, and returns it to the normal starting page when required.