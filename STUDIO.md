# BPSR MIDI Studio (Experimental Beta)

BPSR MIDI Studio is the heavier experimental companion build of **BPSR MIDI Lite**.

Studio reuses the same BPSR MIDI planner/player, then adds a YouTube-to-MIDI workflow for users who do not want to manually download audio or MIDI files. Lite keeps the AI/YouTube stack out of its build; the Local MIDI browser is the shared UI feature.

## Download and run

Studio is distributed as one self-contained EXE named **`BPSR-MIDI-Studio-Experimental-Beta.exe`** on the **same GitHub release page as BPSR MIDI Lite**. No Studio ZIP or `_internal` folder is required.

Because the AI/audio runtime is large, Studio is much bigger than Lite and a one-file Studio launch is slower: PyInstaller extracts its bundled runtime to a temporary Windows folder each time the app starts. The user does not need to manage that folder.

## What Studio adds

1. Choose your BPSR instrument and unlocked Category as usual.
2. Open the **YouTube** song tab.
3. Search for a song or video title.
4. Studio shows the top **3** YouTube results.
5. Click one result.
6. A moving progress bar stays active while Studio is working.
7. Studio automatically:
   - gets the public audio with yt-dlp,
   - converts it to temporary WAV with FFmpeg,
   - transcribes the audio with Spotify Basic Pitch,
   - reduces the dense AI transcription into a cleaner melody + optional bass core,
   - deletes the temporary audio,
   - sends the generated MIDI through the normal BPSR Song Check/planner.
8. Press **Play in BPSR** when Song Check finishes.
9. Use **Save MIDI to Local** if you want to keep the generated MIDI permanently.

For cleaner transcription, prefer YouTube uploads that are **instrumental, piano, guitar, bass, karaoke, melody covers, or otherwise have one clear lead instrument**. Full vocal/full-band mixes are much harder for audio-to-MIDI models.

No YouTube, Google, Spotify, or other account sign-in is requested or stored.

## Cleaner core transcription

Studio does not send every Basic Pitch note directly into BPSR anymore. Full mixes often create duplicated harmonics, tiny notes, and several competing voices, which sounds busy and hides the song.

The experimental cleanup now:

- uses more conservative Basic Pitch thresholds;
- ignores very short/noisy note fragments;
- groups notes that start almost together;
- follows one continuous mid/high lead melody instead of chasing isolated harmonics;
- optionally keeps one clearly separated bass note when it is strong enough;
- limits each onset to at most those two useful voices; and
- quantizes tiny timing jitter before the existing BPSR instrument/category fitting runs.

This is designed to make converted songs sound more like a simple playable MIDI rather than a raw spectral transcription. It is still experimental: choosing an instrumental or melody-focused upload remains the biggest quality improvement.

## Local songs

Both Lite and Studio use the same Local song browser:

1. **Open folder** opens the normal MIDI folder.
2. The search bar plus **Search** filters saved `.mid` / `.midi` filenames.
3. An empty search shows the naturally sorted library.
4. Five songs are visible at a time and the list scrolls for the rest.
5. Click a song in the list to run Song Check and play it.

## First YouTube search

Current yt-dlp needs an external JavaScript runtime for full YouTube support. Studio handles this automatically instead of asking the user to install development tools.

On first YouTube search, Studio downloads and SHA-256 verifies:

- the current official **yt-dlp nightly Windows executable** from the yt-dlp GitHub release; and
- the current official **Deno Windows x64 runtime** from the Deno GitHub release.

The official yt-dlp executable already includes its EJS challenge scripts. Studio passes its private Deno path to yt-dlp, so the user does not need Deno, Node.js, Python, browser cookies, or a YouTube account installed/configured separately.

Studio refreshes yt-dlp periodically and Deno less frequently. If an update check fails but a working local copy already exists, Studio keeps using that copy.

FFmpeg and the Basic Pitch model/runtime are embedded in the single Studio EXE.

## Temporary files

- Downloaded YouTube audio is temporary and is deleted after transcription.
- Generated MIDI is cached temporarily so clicking the same result again does not repeat the AI conversion immediately.
- The core-transcription update uses a new cache version, so older crowded Studio conversions are regenerated once.
- Old Studio cache files are removed automatically.
- **Save MIDI to Local** copies the converted MIDI to the normal Local MIDI folder.

## Limits

Studio is meant for normal songs. Videos over 15 minutes are rejected.

Automatic music transcription is imperfect. The cleanup can reduce clutter, but it cannot recover musical information that the transcription model never detected correctly. Full commercial mixes remain more difficult than clean instrumental recordings.

The experimental beta deliberately avoids advanced AI sliders. Search, click, wait for the progress bar, check, play.

## Account policy

Studio does **not** support importing browser cookies or asking for YouTube account credentials. If a specific upload is age-restricted, private, region-restricted, or blocked from anonymous yt-dlp access, Studio asks you to choose another public upload.

## Use responsibly

Only process audio you are permitted to access and use. BPSR MIDI Studio does not host or redistribute YouTube audio.
