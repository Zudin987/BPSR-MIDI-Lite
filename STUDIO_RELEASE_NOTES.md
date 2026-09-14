# Studio beta.9 hotfix9 - bundled with Lite v3.5.2

This Studio build is attached to the **BPSR MIDI Lite v3.5.2** GitHub release. The visible Studio product remains beta.9 while the internal build advances to `0.5.0-beta.9-hotfix9` and the analysis cache contract advances to `band-accurate-10` because drum transcription itself changed.

## Audio-to-Band Drum overhaul

- Normal Auto/CUDA conversions now prefer DrumSep six-kit transcription even when the optional Cross-check switch is off.
- DrumSep separates kick, snare, toms, hi-hat, ride and crash before onset detection instead of relying on the previous coarse three-role fallback.
- The isolated hi-hat stem is now checked for post-attack decay so sustained hits can become `OPEN_HAT` while short attacks remain `CLOSED_HAT`.
- CPU conversion and DrumSep failures remain non-blocking, but the fallback is upgraded from kick/snare/closed-hat only to multi-band detection for kick, snare, tom, closed/open hat, ride and crash.
- New drum events continue through the calibrated BPSR drum-pad map introduced by the previous hotfixes.

## Drum playback fixes retained

- Keeps the calibrated audible BPSR pad mapping instead of obsolete provisional/silent pad assignments.
- Keeps literal short drum timing: 24 ms press, 8 ms release gap, Raw articulation, zero chord stagger and a 5 ms attack cluster.
- Dense 50-60 ms hi-hat/retrigger patterns are preserved instead of being merged by Piano timing rules.

## Cache behavior

The analysis cache is now `band-accurate-10`. Existing `band-accurate-9` Audio-to-Band results should be reconverted when accurate drums matter, because the new build changes the drum transcription stage itself rather than only rearranging an existing musical map.

## Existing v3.5 precision improvements retained

- Keeps the final BPSR-audibility arrangement layer, accompaniment density controls, rhythm-aware Piano/Guitar attack guard and conservative onset refinement.
- Keeps specialist-supported notes, real chords, strongly supported chromatic notes and the fast-precision default path.
- Studio and Lite continue to share the same Band protocol, room transport, lineup, MIDI sharing, synchronized Start, clock/speed/hash checks and network hardening.

## Validation

The v3.5.2 candidate passed the Lite test/build workflow, Studio test/build workflow, repository hygiene, Studio responsive/frozen-worker validation, clean first-use real model inference, and HQ separation/original-timeline smoke checks before release. Release-trigger metadata was refreshed after synchronizing the remaining 3.5.2 regression assertions.
