# BPSR MIDI Lite v2.3.0

This release aligns the app with the actual BPSR instrument category progression and removes configuration that users should not need to understand.

- Keyboard: Category 1–4 plus Raw MIDI. Category 4 still plays only within C2–B6 so the app never needs `<` / `>`.
- Electric Guitar: Category 1–3 plus Raw MIDI, capped to the safe E2–D6 no-page range.
- Electric Bass: Category 1–2 plus Raw MIDI, capped to E1–B3 with Default/High Octave only.
- Raw MIDI keeps original pitches and full chords; physically unavailable pitches are skipped instead of remapped.
- Removed Advanced song fitting controls from the user interface.
- Removed Minimize-after-Play; the app remains open while the user returns to BPSR.
- Song speed remains available to every category.
- Added a hard UI fail-safe that disables Play if a selectable profile ever generates a page-key event.
- Preserved the v2.1 input-safe short-note/retrigger timing and the existing Ctrl/Shift toggle scheduler.
