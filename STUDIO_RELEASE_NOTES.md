# Studio beta.9 hotfix9 — bundled with Lite v3.5.2

This Studio build is attached to the **BPSR MIDI Lite v3.5.2** GitHub release. It keeps the established beta.9 executable label while advancing the internal Studio build to `0.5.0-beta.9-hotfix9`. The analysis cache contract is now `band-accurate-10` because this release changes Audio → Band drum transcription and old three-role drum analyses must be regenerated.

## Full-kit Audio → Band drums

- Replaces the old built-in drum fallback that could identify only kick, snare, and closed hi-hat.
- The normal Audio tab can now estimate kick, snare, tom, closed hi-hat, open hi-hat, ride, and crash without requiring the Advanced musical cross-check.
- Uses independent low-, mid-, and high-frequency onset streams so legitimate simultaneous attacks such as kick + hat or snare + hat can survive as separate drum hits.
- Uses short-time spectral shape, attack strength, high-frequency decay, and spectral centroid evidence to distinguish kick/tom, snare/tom, closed/open hat, ride, and crash families.
- Preserves fast hi-hat/repeated-hit timing with the dedicated drum playback cycle introduced immediately before this release: 24 ms press, 8 ms release, Raw articulation, no piano-style adaptive reshaping, and no chord stagger.
- Keeps calibrated BPSR Drum pad targets, so generated drum roles route only to the verified audible in-game keys.
- ADTOF remains the preferred specialist when its separately installed runtime is available. DrumSep remains optional quality/cross-check evidence; the standard conversion no longer depends on either model to produce a complete semantic kit.

## Cache behavior

The analysis cache is bumped from `band-accurate-9` to `band-accurate-10`. Songs converted before v3.5.2 should be converted again from the Audio tab once so Studio can regenerate the drum transcription with the full-kit detector. Reusing an old Arrangement or old Drum MIDI will preserve the older incomplete transcription and is not a valid v3.5.2 quality test.

## Existing v3.5 precision improvements retained

- Keeps the final BPSR-audibility arrangement layer and lower-density accompaniment protections from hotfix8.
- Keeps the rhythm-aware Piano/Guitar attack guard and conservative audio-grounded onset refinement.
- Keeps specialist-supported notes, real chords, strongly supported chromatic notes, and the fast-precision default path.
- Keeps the calibrated drum transport and the stale-profile migration guard, so old provisional user mappings no longer override the verified BPSR drum pads.

## Band Mode / Lite interoperability

Studio and Lite continue to share the same Band protocol, room transport, lineup, MIDI sharing, synchronized Start, clock/speed/hash checks, network hardening, and calibrated Drum transport. Compatibility remains based on the shared Band protocol + arrangement contract instead of the visible Lite/Studio product version.

## Validation

The v3.5.2 release candidate must pass the normal Lite test/build workflow, Studio test/build workflow, repository hygiene checks, full-kit drum regression tests, Studio responsive/frozen-worker validation, and release-asset verification before publication.