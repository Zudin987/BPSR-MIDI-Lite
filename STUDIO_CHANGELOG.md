# BPSR MIDI Studio changelog

## 0.4.0-experimental-beta

- Inherits Lite v3.3.0's adaptive BPSR arranger, role-aware remapping, phrase/density-aware note gates, safer collision handling, chord attack normalization, and verified per-instrument Calibration Lab.
- Adds optional Windows WASAPI loopback measurement for observed input-to-audible-game response p50/p95/jitter. Results are diagnostic only and are never blindly subtracted from MIDI timing.
- Adds SoundCard to the Studio-only runtime and verifies that the WASAPI/audio-latency modules are embedded in the single-file EXE.
- Adds Source → BPSR arrangement diagnostics so users can see remapping/thinning/normalization impact before playback.
- Keeps normal playback Stable/no-page and keeps Custom/Raw timing manual rather than applying adaptive phrase shaping.
- Adds byte-for-byte verification of Studio assets after they are attached to the GitHub release.

## 0.3.0-experimental-beta

- Inherited Lite v3.2.0's BPSR-aware timing overhaul, non-blocking control taps, batched Win32 chord input, retrigger hard-floor protection, active-tail-safe state planning, sustain simulation, scheduler telemetry, and advanced Custom tuning UI.
- Kept YouTube download, Basic Pitch transcription, core arrangement cleanup, FFmpeg/ONNX packaging, and temporary-audio workflow unchanged.

## 0.2.2-experimental-beta

- Inherited Lite 3.1.2's Category-safe defaults, modifier timing protection, retrigger handling, true held-key metrics, hard no-page guard, focus safety, and lower-overhead continuous 30 FPS visualizer.
- Kept YouTube download, Basic Pitch transcription, core arrangement cleanup, FFmpeg/ONNX packaging, and temporary-audio workflow unchanged.

## 0.2.1-experimental-beta

- Updated the shared Live MIDI visualizer to a capped **30 FPS** render loop (about 33 ms per frame) for smoother note movement and faster active-key feedback.
- Playback timing, MIDI conversion, BPSR fitting, YouTube workflow, Local/Online search, and input behavior are unchanged.

## 0.1.2-experimental-beta

- Added a visible moving progress bar while YouTube search/conversion is working, with stage text for download, transcription, cleanup, and BPSR checking.
- Reworked YouTube transcription into a cleaner **core arrangement**: conservative Basic Pitch thresholds, short-noise filtering, onset clustering, melodic continuity, and at most a lead + clearly separated bass voice per onset before the normal BPSR fitter runs.
- Invalidates older Studio transcription cache so previously crowded conversions are regenerated with the new core algorithm.
- Reworked the Local tab into **Open folder → Search → scrollable song list** with five visible rows; empty search shows the naturally sorted library and searching filters it.
- Fixed the Local-tab notebook height on the initial view instead of requiring a tab switch first.
- Studio is now attached to the same Lite GitHub release page as **BPSR MIDI Studio (Experimental Beta)** rather than using a separate Studio release page.

## 0.1.1-beta

- Studio is now distributed as one self-contained `BPSR-MIDI-Studio.exe`; no ZIP extraction or `_internal` folder is required by the user.
- Fixed the YouTube tab sizing bug where first-search results could stay hidden until switching to Bookmarks and back.
- Renamed the YouTube save action to **Save MIDI to Local** so keeping a converted MIDI is explicit.
- Added an in-app reminder that instrumental / piano / guitar / bass YouTube uploads usually transcribe more cleanly than full vocal/full-band mixes.
- Added Local MIDI filename search, shared with Lite.

## 0.1.0-beta

- Added a separate Studio build target without changing the Lite launcher/spec.
- Added in-app YouTube title search with the top 3 results.
- Clicking a result automatically retrieves public audio, transcribes it to MIDI, and hands it to the existing BPSR Song Check/player.
- Added temporary audio cleanup and generated-MIDI cache.
- Added Save MIDI to keep a conversion in the normal Local library.
- Added periodically refreshed, SHA-256-verified yt-dlp nightly helper download.
- Added automatic SHA-256-verified Deno runtime download because current yt-dlp requires an external JavaScript runtime for full YouTube support.
- Added bundled FFmpeg support through imageio-ffmpeg.
- Added Spotify Basic Pitch 0.4.0 ONNX transcription in the Studio build.
- No account login/cookies are requested or stored.
