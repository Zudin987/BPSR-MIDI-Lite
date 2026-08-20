# BPSR MIDI Studio changelog

## 0.1.0-beta

- Added a separate Studio build target without changing the Lite launcher/spec.
- Added in-app YouTube title search with the top 3 results.
- Clicking a result automatically retrieves public audio, transcribes it to MIDI, and hands it to the existing BPSR Song Check/player.
- Added temporary audio cleanup and generated-MIDI cache.
- Added Save MIDI to keep a conversion in the normal Local library.
- Added periodically refreshed, SHA-256-verified yt-dlp nightly helper download.
- Added bundled FFmpeg support through imageio-ffmpeg.
- Added Spotify Basic Pitch 0.4.0 ONNX transcription in the Studio build.
- No account login/cookies are requested or stored.
