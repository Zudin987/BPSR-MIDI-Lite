# Studio beta.9 hotfix3

This release refreshes the **BPSR MIDI Studio beta.9** assets attached to Lite release `v3.4.0`.

## Audio → Band quality fix

- Rejects unsupported isolated piano/guitar/other notes that disagree with strong local rhythm and harmonic context.
- Preserves repeated riffs, supported notes, wide chords and normal sixteenth-note syncopation.
- Runs the final pitch/rhythm sanity guard after beta.9 fusion, repeated-motif marking and instrument-presence filtering, before BPSR octave/key fitting.
- Records pitch-guard rejection reasons in provenance for later diagnosis.
- Bumps the analysis cache contract to `band-accurate-5` so older bad-note results are not reused.

## Release polish

- Studio internal version: `0.5.0-beta.9-hotfix3`.
- Windows Studio executable metadata now reports `0.5.0-band-accurate-beta.9-hotfix3`.
- No new heavyweight model/runtime dependency was added by this hotfix.

## Validation

PR #37 passed the Windows Lite build/tests, Windows Studio build/tests, frozen-worker/runtime checks, repository hygiene, standard real-audio smoke and HQ real-audio smoke before release. The final metadata-only polish does not alter the transcription pipeline.
