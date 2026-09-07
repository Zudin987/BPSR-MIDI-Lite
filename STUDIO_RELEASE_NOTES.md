# Studio beta.9 hotfix5

This release refreshes the **BPSR MIDI Studio beta.9** assets attached to Lite release `v3.4.0`.

## Audio → Band precision-review upgrade

- Keeps the hotfix4 final audio-grounded Piano/Guitar validation and adds three optional **review-only** specialists aimed at the remaining random/wrong notes.
- Adds a dedicated six-fold HCQT+Mel **GuitarSet specialist reviewer**. It scores only guitar notes Basic Pitch already proposed; it cannot create or delete notes by itself.
- Adds **YourMT3+** as CUDA-only independent evidence on a small number of uncertain regions. Its MIDI is reference evidence for fusion, not a replacement transcription.
- Adds **MVSep Mega 53 Stems** as a high-VRAM ownership judge for ambiguous Piano/Guitar notes. It runs only on uncertain regions and only with at least 14 GB detected NVIDIA VRAM.
- Mega53 is used to answer questions such as “does this pitch belong to piano or guitar?”; its 53 stems never replace the main Demucs/BS-RoFormer song stems.
- The precision reviewers remain independent of MR-MT3: if MR-MT3 itself fails, YourMT3+/Mega53 can still review the same uncertain windows when their runtimes are available.
- Strong specialist agreement protects credible notes from later conservative guards; specialist conflicts reduce confidence so existing fusion/audio checks can remove weak hallucinations.
- Bumps the analysis cache contract to `band-accurate-7`, so prior hotfix4 analysis is not reused.

## Runtime and safety policy

- Guitar reviewer supports CPU/CUDA in its own isolated runtime; the one-click recommended path installs it only for CUDA extra-quality analysis.
- YourMT3+ is never silently retried as a CPU workload.
- Mega53 is never installed/run below the 14 GB VRAM gate, avoiding hidden out-of-memory attempts.
- All three additions are non-blocking quality reviewers: if one cannot install or run, normal specialist/fusion processing continues.
- YourMT3+ upstream GPL-3.0 source is downloaded at runtime instead of being vendored into the Studio executable. Its hosted checkpoint repository declares Apache-2.0.
- Guitar-Transcription and its published weight repository are MIT-licensed. Mega53 uses the MIT-licensed `ZFTurbo/Music-Source-Separation-Training` source and checksum-pinned v1.0.21 release assets.

## Release polish

- Studio internal pipeline version: `0.5.0-beta.9-hotfix5`.
- Windows executable metadata intentionally remains on the beta.9 release label (`0.5.0-band-accurate-beta.9`) to stay consistent with the existing launcher/release contract.
- Existing beta.9 asset names remain unchanged so the v3.4.0 release workflow can replace them in place.

## Validation

The change includes focused unit coverage proving that the guitar and Mega53 reviewers only reweight/annotate existing notes and that the new runtimes are isolated and cache-invalidating. Standard repository/Windows Studio CI remains the release gate; heavyweight external model inference is intentionally not performed in ordinary CI.
