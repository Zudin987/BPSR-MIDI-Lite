# 🎹 BPSR MIDI Lite / Studio

A Windows MIDI utility for **Blue Protocol: Star Resonance** instruments: Keyboard/Piano, Electric Guitar, and Electric Bass.

**Website:** https://zudin987.github.io/projects/bpsr-midi/

| Edition | Use it when |
|---|---|
| **Lite** | You already have MIDI files or want Online Sequencer playback. |
| **Studio** | You also want compatible YouTube/audio → MIDI conversion. |

Both are standalone Windows builds; **Python is not required** for normal use.

## Quick start

1. Download the latest GitHub Release and open the Lite or Studio EXE.
2. Choose **Instrument → Category → Song** and leave Speed at **100%** unless you want a different tempo.
3. Check **Song Check**, press **Play**, and return to BPSR before the countdown ends.

Fresh installs start at **Category 1**. Select a higher Category only when that instrument range is actually unlocked on your BPSR character; saved choices are remembered.

> **Emergency stop:** press **F10** at any time to stop playback and release held keys.

## Features

Both editions include:

- Local `.mid` / `.midi` playback.
- Online Sequencer search, URL/ID loading, bookmarks, and Save to Local.
- Automatic note fitting for BPSR instrument ranges.
- Song Check, live MIDI waterfall, adjustable speed, Pause/Resume, and F10 Panic Stop.

Studio additionally provides YouTube search and audio → MIDI conversion.

The app does **not modify BPSR game files** and does not ask for your BPSR account password.

## Song sources

### Local MIDI

Open the **Local** tab, put MIDI files in the local song folder, choose one, and press **Play**. Local playback works offline.

### Online Sequencer

Search by song name or paste an Online Sequencer URL/ID. If Online Sequencer requires browser verification, click **Verify once**, complete the check in Firefox, then return and search again.

When that fallback is required, the app may read existing `onlinesequencer.net` cookies from the local Firefox profile and send them only back to `onlinesequencer.net` with the matching Firefox user agent. Cookie values are not displayed or saved in BPSR MIDI settings.

Bookmarks keep a reference to an online song; use **Save to Local** if you want an offline MIDI copy.

### YouTube / audio — Studio only

Studio can search public YouTube content and convert compatible audio into MIDI. Cleaner sources such as piano/guitar/bass covers, instrumentals, karaoke tracks, or melody-focused recordings usually convert better than dense full mixes.

Studio does not use your Google/YouTube login or browser cookies. Downloaded audio is temporary; save the generated MIDI explicitly if you want to keep it.

## Song Check

Song Check reports whether the selected MIDI is ready, busy, or crowded and shows remapped, skipped, filtered, close-repeat, peak-held-key, and finally playable-note information. Normally you do not need to adjust anything manually.

The recommended input method is **Win32 scan code**. Leave it unchanged if playback works correctly.

## Privacy and safety

- Local MIDI files stay on your PC.
- Online features contact their relevant public services only when used.
- BPSR MIDI does not record arbitrary keyboard typing.
- Keyboard input is used to play the selected BPSR instrument.
- The app locks playback to the foreground process seen when the countdown ends. If another app takes focus, held keys are released and the song waits until the same BPSR process is foreground again.
- F10 is the global Panic Stop hotkey.

Third-party websites can change and temporarily break online features; local MIDI playback remains independent.

Use only MIDI/audio/content that you are permitted to use or process. This is an unofficial fan-made utility and is not affiliated with BPSR, Online Sequencer, YouTube, or their owners/operators.

## Development

Lite entry point: `modern_launcher.py`  
Studio entry point: `studio_launcher.py`

Run tests:

```text
python -m pytest -q
```

Build Lite:

```text
pyinstaller --noconfirm --clean BPSR-MIDI-Lite.spec
```

Build Studio:

```text
pyinstaller --noconfirm --clean BPSR-MIDI-Studio.spec
```

See [CHANGELOG.md](CHANGELOG.md), [STUDIO.md](STUDIO.md), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and [STUDIO_THIRD_PARTY_NOTICES.md](STUDIO_THIRD_PARTY_NOTICES.md) for additional details.

## License

**GNU AGPL-3.0** — created by **MrEz**.
