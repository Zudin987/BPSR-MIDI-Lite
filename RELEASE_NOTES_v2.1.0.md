# BPSR MIDI Lite v2.1.0

This release retunes MIDI articulation around BPSR's keyboard-input behavior without rewriting the music.

- Preserve the MIDI's original tempo by default (100%).
- Preserve authored note durations by default (100%).
- Extend only unusually short notes to a 70 ms minimum key hold.
- Give repeated use of the same pitch/game key a brief 16 ms release window so it can retrigger.
- Keep unrelated notes overlapping as authored instead of cutting sustained notes when another note begins.
- Cap malformed dangling notes at 500 ms instead of potentially holding them to the end of the file.
- Keep page switching, modifier timing, sustain, pitch mapping, chord handling, and the playback scheduler unchanged.

The defaults are intentionally conservative: compensate for game input recognition, but do not globally slow or stretch songs.
