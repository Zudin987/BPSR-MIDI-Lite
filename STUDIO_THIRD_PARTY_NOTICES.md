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

## imageio-ffmpeg / FFmpeg

Project: `imageio/imageio-ffmpeg`

Purpose: supplies the platform FFmpeg executable used to convert downloaded audio into WAV for transcription.

License for the Python wrapper: BSD 2-Clause.

Platform wheels include an FFmpeg executable. FFmpeg itself is distributed under the license terms applicable to the exact bundled build. The Studio release process records `ffmpeg -version` and `ffmpeg -buildconf` output in `FFMPEG_BUILD_INFO.txt` so the redistributed build can be identified and audited.

See the imageio-ffmpeg and FFmpeg upstream projects for the license texts and source/compliance information applicable to that build.

## SoundCard

Project: `bastibe/SoundCard`

Purpose: optional Windows WASAPI loopback recording used by Studio's local input-to-game-audio timing diagnostic.

License: BSD 3-Clause.

Studio uses SoundCard 0.4.6. The latency diagnostic records the user's normal Windows output mix only while the user explicitly runs the test. It does not inspect BPSR memory or network traffic.

## yt-dlp

Project: `yt-dlp/yt-dlp`

Purpose: YouTube search metadata and public audio retrieval.

Studio does not bundle yt-dlp into the source tree. On first YouTube use it downloads the official current nightly Windows executable from the yt-dlp GitHub release and verifies the SHA-256 published by that release.

The official executable contains yt-dlp's EJS challenge scripts. The yt-dlp source project is published under the Unlicense. Its packaged release binaries may include components under additional licenses; see yt-dlp's `THIRD_PARTY_LICENSES.txt`.

## Deno

Project: `denoland/deno`

Purpose: JavaScript runtime used by yt-dlp's current YouTube challenge support.

Studio downloads the official Windows x64 Deno runtime from the Deno GitHub release on first YouTube use and verifies the release SHA-256 before extraction. See the Deno project for its current MIT license and notices.

## Other dependencies

Studio also contains dependencies pulled by Basic Pitch and the existing BPSR MIDI Lite build. Their upstream licenses remain applicable.
