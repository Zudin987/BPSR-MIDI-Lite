# BPSR MIDI Lite / Studio

Windows MIDI player for **Blue Protocol: Star Resonance** instruments, with solo and Band Mode playback. Studio adds experimental audio transcription and four-part band arrangements.

[Download latest release](https://github.com/Zudin987/BPSR-MIDI-Lite/releases/latest) · [Project website](https://zudin987.github.io/projects/bpsr-midi/) · [Report an issue](https://github.com/Zudin987/BPSR-MIDI-Lite/issues)

## Choose an edition

| Edition | Use it for | Release executable |
| --- | --- | --- |
| **Lite** | Local MIDI, Online Sequencer and Band Mode; smaller download | `BPSR-MIDI-Lite.exe` |
| **Studio · experimental beta** | Lite playback plus audio-to-MIDI and Audio → Band | `BPSR-MIDI-Studio-Experimental-Beta.exe` |

Both release builds run on **64-bit Windows** without a separate Python installation. Studio needs additional disk space and first-use downloads for its model runtimes. See the [Audio → Band guide](STUDIO_BAND_ACCURATE.md) for requirements and setup.

## Play a song

1. Download your edition from Releases and open the EXE.
2. Open BPSR's instrument screen. Match the app's **Instrument** and unlocked **Category** to the game.
3. Choose a local MIDI or an Online Sequencer song.
4. Review **Song Check** for remapped or skipped notes.
5. Press **Play** and return to BPSR before the countdown ends.

**Press F10 at any time to stop playback and release held keys.**

Playback sends instrument key presses to BPSR; it does not modify game files. Keep the correct game window and instrument screen active during playback.

## Studio: audio to a band

Open **Audio → Band** and choose a local MP3, WAV, FLAC, M4A or OGG file, or use the online song search. Local file input is always available. Review the Piano, Guitar, Bass and Drums parts before exporting or loading them into the player.

Audio transcription is experimental. Dense mixes can still produce wrong or missing notes, and conversion can take time. Only process audio you are permitted to access and use.

[Audio → Band setup, workflow and limitations](STUDIO_BAND_ACCURATE.md) · [YouTube transcription workflow](STUDIO.md)

## Troubleshooting

- **Wrong or missing notes:** confirm your instrument/category and review Song Check. The game's playable range is limited.
- **Playback goes to the wrong window:** stop with F10 and return to BPSR's instrument screen before restarting.
- **Studio setup or conversion fails:** open **Details** in the conversion workspace and include that error, your edition and app version in an issue. First-time model setup needs internet access.

Unofficial community tool, not affiliated with BPSR's developers or publishers.

[Changelog](CHANGELOG.md) · [Studio changelog](STUDIO_CHANGELOG.md) · [License](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md) · [Studio dependencies and credits](STUDIO_THIRD_PARTY_NOTICES.md)
