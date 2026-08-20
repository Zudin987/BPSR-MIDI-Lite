# BPSR MIDI Studio (beta)

BPSR MIDI Studio is the heavier companion build of **BPSR MIDI Lite**.

**Lite is intentionally unchanged.** Studio reuses the same BPSR MIDI planner/player, then adds a YouTube-to-MIDI workflow for users who do not want to manually download audio or MIDI files.

## What Studio adds

1. Choose your BPSR instrument and unlocked Category as usual.
2. Open the **YouTube** song tab.
3. Search for a song or video title.
4. Studio shows the top **3** YouTube results.
5. Click one result.
6. Studio automatically:
   - gets the public audio with yt-dlp,
   - converts it to temporary WAV with FFmpeg,
   - transcribes the audio to MIDI with Spotify Basic Pitch,
   - deletes the temporary audio,
   - sends the generated MIDI through the normal BPSR Song Check/planner.
7. Press **Play in BPSR** when Song Check finishes.
8. Use **Save MIDI** only if you want to keep the generated MIDI in your Local library.

No YouTube, Google, Spotify, or other account sign-in is requested or stored.

## First YouTube search

Current yt-dlp needs an external JavaScript runtime for full YouTube support. Studio handles this automatically instead of asking the user to install development tools.

On first YouTube search, Studio downloads and SHA-256 verifies:

- the current official **yt-dlp nightly Windows executable** from the yt-dlp GitHub release; and
- the current official **Deno Windows x64 runtime** from the Deno GitHub release.

The official yt-dlp executable already includes its EJS challenge scripts. Studio passes its private Deno path to yt-dlp, so the user does not need Deno, Node.js, Python, browser cookies, or a YouTube account installed/configured separately.

Studio refreshes yt-dlp periodically and Deno less frequently. If an update check fails but a working local copy already exists, Studio keeps using that copy.

FFmpeg and the Basic Pitch model/runtime are included in the Studio portable build.

## Temporary files

- Downloaded YouTube audio is temporary and is deleted after transcription.
- Generated MIDI is cached temporarily so clicking the same result again does not repeat the AI conversion immediately.
- Old Studio cache files are removed automatically.
- **Save MIDI** copies the converted MIDI to the normal Local MIDI folder.

## Limits

Studio is meant for normal songs. Videos over 15 minutes are rejected.

Automatic music transcription is imperfect. Basic Pitch performs best on recordings with one clear instrument; full commercial mixes with vocals, drums, synths, bass, and effects can produce crowded MIDI. BPSR MIDI Lite's normal Piano/Guitar/Bass fitting still runs afterward, but it cannot reconstruct musical information that the transcription model guessed incorrectly.

The first Studio beta deliberately avoids advanced AI sliders. Search, click, check, play.

## Account policy

Studio does **not** support importing browser cookies or asking for YouTube account credentials. If a specific upload is age-restricted, private, region-restricted, or blocked from anonymous yt-dlp access, Studio asks you to choose another public upload.

## Use responsibly

Only process audio you are permitted to access and use. BPSR MIDI Studio does not host or redistribute YouTube audio.
