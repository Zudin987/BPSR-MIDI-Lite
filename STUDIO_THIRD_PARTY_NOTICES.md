# BPSR MIDI Studio — third-party notices

This file applies to the **Studio** build. The existing Lite build and its notice file remain unchanged.

## Spotify Basic Pitch

Project: `spotify/basic-pitch`

Purpose: automatic music transcription (audio to MIDI).

License: Apache License 2.0.

Studio uses Basic Pitch 0.4.0 with its ONNX model/runtime on Windows.

## ONNX Runtime

Purpose: runs the Basic Pitch ONNX neural-network model.

License: MIT (see the ONNX Runtime package/project license distributed by its maintainers).

## imageio-ffmpeg

Project: `imageio/imageio-ffmpeg`

Purpose: supplies the platform FFmpeg executable used to convert downloaded audio into WAV for transcription.

License for the Python wrapper: BSD 2-Clause. Platform wheels include an FFmpeg executable; FFmpeg itself is distributed under its applicable FFmpeg build licenses. See the imageio-ffmpeg and FFmpeg license information included with/upstream from those projects.

## yt-dlp

Project: `yt-dlp/yt-dlp`

Purpose: YouTube search metadata and public audio retrieval.

Studio does not bundle yt-dlp into the source tree. On first YouTube use it downloads the official current nightly Windows executable from the yt-dlp GitHub release and verifies the SHA-256 published by that release.

The yt-dlp source project is published under the Unlicense. Its packaged release binaries may include components under additional licenses; see yt-dlp's `THIRD_PARTY_LICENSES.txt`.

## Other dependencies

Studio also contains the dependencies pulled by Basic Pitch and the existing BPSR MIDI Lite build. Their upstream licenses remain applicable.
