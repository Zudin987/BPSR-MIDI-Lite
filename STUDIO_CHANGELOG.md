# BPSR MIDI Studio changelog

## 0.5.0-band-accurate-beta.4

- Replaces the Audio → Band Apple/MassiveMusic/Bandcamp resolver UI with a single **spotDL** search/download path while keeping manual MP3/WAV/FLAC/M4A/OGG input permanently available.
- Uses Spotify metadata for song identity and spotDL's YouTube / YouTube Music matching for audio; Spotify audio streams are not downloaded.
- Installs pinned `spotdl==4.5.2` into its own managed Python 3.11 runtime on first search instead of bundling it into the Studio EXE or Lite dependencies.
- Reuses Studio's bundled FFmpeg and attempts spotDL's recommended Deno helper setup for better current YouTube compatibility.
- Renames the source actions to **Search spotDL**, **Download & Analyze**, **Open Spotify** and **spotDL info**; the old storefront selector is repurposed as a fixed `spotDL` source indicator.
- Keeps explicit download/analysis rights confirmation, Spotify-URL validation, a 2 GB limit, MP3 signature checks, SHA-256 verification, atomic acquisition caching and shell-free subprocess invocation.
- Adds unit coverage for spotDL result normalization, non-Spotify URL rejection and safe download command construction.

## 0.5.0-band-accurate-beta.3

- Fits the Audio → Band workspace inside the current desktop instead of opening a fixed 980×780 window that can sit behind the Windows taskbar.
- Adds vertical scrolling so conversion, preview and export controls remain reachable at 640×480 window size, while preserving a full-width responsive layout on larger screens.
- Adds a visible resolver-results scrollbar and moves long source status text below its actions so search controls do not collapse on narrow windows.
- Makes Source setup, Advanced, Technical details and Drum mapping dialogs screen-aware and scrollable where needed; Source setup also avoids duplicate windows and adds an explicit Cancel action.
- Renames the manual picker to **Choose local audio…** so its label no longer implies that supported FLAC/M4A/OGG files are excluded.

## 0.5.0-band-accurate-beta.2

- Adds a provider-neutral Music Resolver inside Audio → Band while keeping local MP3/WAV/FLAC/M4A/OGG selection visible and available at all times.
- Uses Apple Music (with a developer token) or Apple's public storefront search for MY/ID-aware song discovery and metadata. Apple previews are never downloaded or sent to the AI pipeline.
- Adds MassiveMusic catalogue search and OAuth-signed purchased-track delivery for commercially licensed partners with an entitled user.
- Adds authenticated Bandcamp OpenSubsonic search/download for music already present in the user's own collection.
- Requires an explicit rights confirmation before provider audio enters analysis, verifies download size/type/signature/SHA-256, caches atomically, and records only non-secret source provenance in `Arrangement.json`.
- Deliberately excludes SoundCloud acquisition because its current API terms prohibit using API content as input to AI source separation; Spotify and streaming rip paths remain unsupported.

## 0.5.0-band-accurate-beta.1

- Adds the Audio → Band tab with local audio import, progress/cancellation, Piano/Guitar/Auto melody ownership, preview, category controls and four-part MIDI export.
- Separates six stems and runs isolated instrument specialists, beat detection and MR-MT3 cross-check before confidence fusion and BPSR arrangement.
- Saves a common musical map and self-contained arrangement manifest; changing melody ownership or categories reuses analysis without repeating AI inference.
- Adds external, explicitly provisional drum mapping, runtime installation/repair, cache integrity checks and recorded fallbacks.
- Adds real-model and frozen-worker Windows smoke checks while keeping AI/audio dependencies out of Lite.
- See [the beta guide](STUDIO_BAND_ACCURATE.md) for setup, limitations and model/license notes.

## 0.4.2-experimental-beta

- Inherits Lite v3.4.0's evidence-driven arranger refinements and responsive product UI.
- Uses the same permanent 400 px MIDI Library, protected main workspace, compact Song Check metrics, responsive text, and overlay Settings drawer as Lite.
- Keeps the Studio YouTube/audio → MIDI pipeline, Basic Pitch/ONNX transcription, bundled FFmpeg, yt-dlp/Deno helpers, and WASAPI diagnostics otherwise unchanged.
- Adds shared CI coverage for `ui_*.py` so UI-only changes validate both Lite and Studio Windows builds before release.

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
