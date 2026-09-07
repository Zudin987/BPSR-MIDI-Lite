# Studio beta.9 hotfix8 — bundled with Lite v3.5.1

This Studio build is attached to the **BPSR MIDI Lite v3.5.1** GitHub release. It keeps the established beta.9 executable label while advancing the internal Studio build to `0.5.0-beta.9-hotfix8`. The analysis cache contract remains `band-accurate-9` because this hotfix changes final BPSR arrangement behavior rather than stem separation or transcription.

## BPSR in-game clarity

- Adds a final BPSR-audibility arrangement layer after normal musical reduction and physical key mapping. The goal is to optimize for what the real BPSR instruments sound like, not just what looks correct in a desktop MIDI preview.
- Collapses duplicated ambiguous `other` accompaniment so the same musical event is not reinforced by multiple Band players at effectively full digital-key volume.
- When Piano and Guitar are both plausible owners for ambiguous accompaniment, the backing material prefers the part opposite the main melody owner when possible, separating foreground and accompaniment.
- Protects `MAIN_MELODY`, `MELODY`, `RIFF`, and `BASS` from density-only removal. Sparse passages are intentionally left unchanged.

## Lower-density accompaniment

- Piano begins dynamic chord thinning at roughly 5.5 local attacks/second: busy accompaniment is capped around three notes, and very busy passages around two notes.
- Guitar uses a two-note busy-section cap from roughly 5.5 local attacks/second.
- Expendable `DECORATION` notes can be removed before useful Harmony/Rhythm material once accompaniment becomes moderately busy.
- Very dense, soft Harmony/Decoration-only attacks may be skipped entirely when repeated too closely; the allowed spacing becomes stricter as local attack pressure rises.
- Accompaniment tails are shortened during busy passages (approximately 240 ms at 5.5+ attacks/s, 180 ms at 7.5+, and 140 ms at 9+) so held notes do not pile up under later BPSR key presses.
- Retained notes continue to prioritize musical role, transcription confidence, chord identity, and non-duplicated pitch classes; MIDI velocity is treated only as a weak hint because it cannot be trusted as an in-game mixing control.

## Existing v3.5 precision improvements retained

- Keeps the rhythm-aware Piano/Guitar attack guard that removes attackless off-rhythm retriggers only when the instrument stem and original mixture lack a real local re-attack.
- Keeps conservative audio-grounded onset refinement within a small ±90 ms neighborhood, preserving genuine syncopation and human timing rather than blindly beat-quantizing notes.
- Keeps specialist-supported notes, real chords, strongly supported chromatic notes, and the fast-precision default path.

## Cache and rearrangement

The analysis cache remains `band-accurate-9`. Existing v3.5 Studio musical maps do **not** need another expensive AI pass: saved MasterSong/arrangement data can be rearranged with the new in-game clarity layer and receive the density changes directly.

## Band Mode / Lite interoperability

Studio and Lite continue to share the same Band protocol, room transport, lineup, MIDI sharing, synchronized Start, clock/speed/hash checks, network hardening, and calibrated Drum transport. Compatibility remains based on the shared Band protocol + arrangement contract instead of the visible Lite/Studio product version.

## Validation

The v3.5.1 release candidate must pass the normal Lite test/build workflow, Studio test/build workflow, repository hygiene checks, Studio responsive/frozen-worker validation, and the existing real-audio smoke path before release assets are published.