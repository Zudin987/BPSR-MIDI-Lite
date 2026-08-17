# v2.1 backend timing audit

## Why change the old defaults

The old beginner profiles ran songs at 85% speed and stretched note durations to 135–150%. That solved short-input concerns by changing the whole composition, including notes that were already long enough.

The duration post-processor also cut a note when any later note began. That prevented synthetic overlap but also cut legitimate polyphony and legato from valid MIDI files.

## v2.1 policy

- MIDI tempo is musical data: preserve it at 100% unless the user explicitly changes Advanced speed.
- MIDI note-off timing is musical data: preserve it at 100% unless the user explicitly changes Advanced note length.
- BPSR input reliability is an input constraint: only very short notes receive a 70 ms minimum hold.
- Retriggering is a physical-key constraint: only a later use of the same pitch or physical key can force an earlier Note Off, with a 16 ms target release window.
- Malformed files are bounded: a missing Note Off is capped at 500 ms instead of holding until file end.

Page-change timing (220 ms), modifier lead (55 ms), sustain behavior, mapping, chord policies, and scheduler precision are intentionally unchanged because this audit found no evidence that those established values need broader alteration.
