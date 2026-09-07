# Studio beta.9 hotfix7 — bundled with Lite v3.5.0

This Studio build is attached to the **BPSR MIDI Lite v3.5.0** GitHub release. It keeps the established beta.9 executable label while advancing the internal Audio → Band pipeline to `0.5.0-beta.9-hotfix7` / `band-accurate-9`.

## Audio → Band quality

- Adds a final rhythm-aware attack guard for Piano/Guitar. A suspicious off-grid singleton note is removed only when the pitch is present but both the separated instrument stem and original mixture show no real local re-attack.
- Adds conservative audio-grounded onset refinement. When a real Piano/Guitar note is transcribed tens of milliseconds early or late, Studio can move it to a stronger nearby attack found in both the instrument stem and original mixture.
- Onset refinement searches only a small ±90 ms neighborhood and never blindly quantizes notes to the beat grid, preserving genuine syncopation and human timing.
- Keeps specialist-supported notes protected and preserves real same-onset chords, chromatic notes with strong source evidence, and consistently humanized phrases.
- Retains the fast-precision default path: normal conversion uses the fast separator and targeted suspicious-region review instead of charging every song for full-song heavyweight diagnostics.

## Cache refresh

The analysis cache contract is now `band-accurate-9`. Existing `band-accurate-8` musical maps are intentionally regenerated once so upgraded users receive the new rhythm/onset validation instead of silently reusing pre-v3.5 results.

## Band Mode / Lite interoperability

- Studio and Lite continue to use the same Band room transport, lineup, MIDI sharing, timing, network-hardening and calibrated drum layers.
- Cross-edition compatibility is based on the shared Band protocol + arrangement contract rather than the visible product version, so a Lite v3.5 host can play with Studio beta.9 clients from the same release.
- Regression coverage explicitly verifies Lite-host/Studio-client roster compatibility and synchronized Start payload compatibility.

## Validation

The v3.5 release candidate is required to pass the normal Lite test/build workflow, Studio test/build workflow, repository hygiene checks, Studio responsive/frozen-worker checks and the existing real-audio smoke path before release assets are published.