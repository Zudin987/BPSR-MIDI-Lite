# BPSR MIDI Studio — third-party notices

This file applies to the **Studio** build. The Lite build and `THIRD_PARTY_NOTICES.md` remain applicable where relevant.

## Spotify Basic Pitch

Project: `spotify/basic-pitch`

Purpose: automatic music transcription (audio to MIDI).

License: Apache License 2.0.

Studio uses Basic Pitch 0.4.0 with its ONNX model/runtime on Windows.

## ONNX Runtime

Purpose: runs the Basic Pitch ONNX neural-network model.

License: MIT (see the ONNX Runtime package/project license distributed by its maintainers).

## torchcrepe

Project: `maxrmorrison/torchcrepe`

Purpose: independent pitch and periodicity evidence for vocal and bass stems.

License: MIT.

Studio installs pinned `torchcrepe==0.0.24` into the isolated separator runtime
on first use. Its model assets are not bundled into the Lite application.

## imageio-ffmpeg / FFmpeg

Project: `imageio/imageio-ffmpeg`

Purpose: supplies the platform FFmpeg executable used to prepare audio for transcription and is reused by the isolated spotDL runtime.

License for the Python wrapper: BSD 2-Clause.

Platform wheels include an FFmpeg executable. FFmpeg itself is distributed under the license terms applicable to the exact bundled build. The Studio release process records `ffmpeg -version` and `ffmpeg -buildconf` output in `FFMPEG_BUILD_INFO.txt` so the redistributed build can be identified and audited.

See the imageio-ffmpeg and FFmpeg upstream projects for the license texts and source/compliance information applicable to that build.

## SoundCard

Project: `bastibe/SoundCard`

Purpose: optional Windows WASAPI loopback recording used by Studio's local input-to-game-audio timing diagnostic.

License: BSD 3-Clause.

Studio uses SoundCard 0.4.6. The latency diagnostic records the user's normal Windows output mix only while the user explicitly runs the test. It does not inspect BPSR memory or network traffic.

## spotDL

Project: `spotDL/spotify-downloader`

Purpose: Studio's optional song-search/download source for Audio → Band. spotDL uses Spotify metadata to identify tracks and matches/downloads audio from YouTube / YouTube Music.

License: MIT.

Studio does **not** bundle spotDL into the main EXE. On first spotDL search, Studio creates an isolated managed Python 3.11 runtime and installs the pinned `spotdl==4.5.2` package there. The runtime is separate from Lite and from every AI/transcription environment.

spotDL's own project documentation states that users are responsible for ensuring downloads are authorized and that it does not support unauthorized downloading of copyrighted material. Studio therefore shows an explicit rights confirmation before the selected spotDL result is downloaded and analyzed.

## yt-dlp

Project: `yt-dlp/yt-dlp`

Purpose: YouTube search/retrieval in existing Studio features and the YouTube audio backend used transitively by spotDL.

Studio does not bundle a second yt-dlp copy into the source tree. Existing direct YouTube tooling manages its own verified executable, while the isolated spotDL runtime receives the yt-dlp Python dependency required by the pinned spotDL package.

The yt-dlp source project is published under the Unlicense. Its packaged release binaries may include components under additional licenses; see yt-dlp's `THIRD_PARTY_LICENSES.txt`.

## Deno

Project: `denoland/deno`

Purpose: JavaScript runtime recommended by current spotDL/yt-dlp releases for YouTube challenge support.

When Studio first installs the isolated spotDL runtime it also attempts spotDL's official `--download-deno` setup. Failure to install Deno does not disable spotDL completely, but Studio warns that a small number of YouTube matches may fail without it.

See the Deno project for its current MIT license and notices.

## Other dependencies

Studio Audio → Band uses the MIT-licensed tkinterdnd2 wrapper with its included
TkDND notices. Optional AI engines run in separately installed environments;
see [the model and checkpoint license notes](STUDIO_BAND_ACCURATE.md#third-party-modellicense-notes).
The built-in spectral drum/beat fallback is project code.

The development-only real-audio quality gate uses `mir_eval` 0.8.2 (ISC
license) to write a repeatable synthetic-note benchmark. It is not imported by
the Studio application or included in the Lite build.

Transkun 2.0.1 depends on the MIT-licensed NCLS package. On Windows, Studio's
isolated Python 3.11 runtime constrains this dependency to `ncls==0.0.68` and
requires its published binary wheel; NCLS is downloaded at first use and is not
bundled into the Studio EXE or the Lite application.

Studio also contains dependencies pulled by Basic Pitch and the existing BPSR MIDI Lite build. Their upstream licenses remain applicable.

## Online music source behavior

The Audio → Band search UI now exposes **spotDL only**. Apple Music, MassiveMusic/7digital and Bandcamp resolver controls are no longer part of the Studio search flow. Manual local MP3/WAV/FLAC/M4A/OGG input remains permanently available and requires no spotDL setup.

The spotDL search path uses Spotify metadata for track identity and then asks spotDL to match audio from YouTube / YouTube Music. Studio does not download Spotify audio streams. The selected full audio file is checked for type/signature, size and SHA-256 before it enters the Audio → Band pipeline, then is kept in Studio's verified acquisition cache.

Each upstream service's current terms and the user's local law/rights still apply independently.
