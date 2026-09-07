# Studio beta.9 hotfix4

This release refreshes the **BPSR MIDI Studio beta.9** assets attached to Lite release `v3.4.0`.

## Audio → Band quality fix

- Adds final **audio-grounded Piano/Guitar note validation** for the remaining notes that look musically plausible but are not actually supported by the recording.
- Checks each surviving Piano/Guitar pitch at its real onset against the resolved source stem, the original prepared mixture, and competing stems.
- Rejects clear pitch absence, cross-stem ownership mistakes, weak Basic Pitch guitar activations, weak Transkun piano detections, and likely guitar harmonics without credible local support.
- Borderline notes are down-weighted instead of automatically deleted.
- Runs only after beta.9 fusion, independent-model agreement, repeated-motif marking, instrument-presence filtering, and the existing rhythm/pitch guard, but still before BPSR octave/range mapping.
- The pre-release double-check caught and removed an earlier provider-level placement that could have rejected a real note before Aria/MuScriptor/MR-MT3 evidence existed.
- Repeated motifs are not treated as independent audio proof, so a repeating separator artifact cannot protect itself just by recurring every bar.
- Bumps the analysis cache contract to `band-accurate-6`, so old Piano/Guitar analysis from hotfix3 is not reused.

## Release polish

- Studio internal pipeline version: `0.5.0-beta.9-hotfix4`.
- Windows executable metadata intentionally remains on the beta.9 release label (`0.5.0-band-accurate-beta.9`) to stay consistent with the existing launcher/release contract.
- No new heavyweight model/runtime dependency was added by this hotfix.
- Final audio validation is non-blocking: if its local audio check cannot run, Studio keeps the already-fused transcription and records why the guard was skipped.

## Validation

PR #38 passed the Windows Lite build/tests, Windows Studio build/tests, responsive/UI checks, frozen-worker/runtime checks, repository hygiene, standard real-audio smoke, and HQ real-audio smoke before merge. The release build is rebuilt from `main` and its uploaded assets are verified byte-for-byte by the existing release workflow.
