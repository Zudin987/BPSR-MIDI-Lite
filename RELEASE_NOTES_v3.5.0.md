# BPSR MIDI Lite / Studio v3.5.0

v3.5.0 promotes the shared Band Mode work and the latest Studio Audio → Band precision fixes into one validated release.

## Lite + Studio Band Mode

- Lite and Studio can host/join the same Band room.
- Cross-edition compatibility uses the shared Band protocol + arrangement contract instead of requiring identical visible product-version strings.
- Keeps synchronized Start, MIDI hash checks, speed checks, clock synchronization, lineup validation, MIDI sharing and network hardening shared between both editions.
- Keeps the calibrated BPSR Drum transport limited to the confirmed-audible pads.

## Studio Audio → Band

- Removes attackless off-rhythm Piano/Guitar retriggers that can survive ordinary pitch validation because a sustained harmonic is still present in the audio.
- Repairs clearly mis-timed Piano/Guitar note-ons to a nearby real audio attack when both the separated stem and original mixture agree.
- Preserves genuine syncopation/human timing; timing repair is audio-grounded and never blind beat quantization.
- Keeps specialist/model-supported notes protected and leaves real chords intact.
- Bumps the Studio analysis cache contract to `band-accurate-9` so old cached musical maps are regenerated once and receive the new cleanup.

## Release validation

The release workflow builds Lite and Studio separately, runs their test suites and packaging checks, verifies Lite contains no Studio-only AI/audio dependencies, verifies Studio contains its required runtimes, and publishes SHA-256 checksum files alongside the Windows downloads.