# BPSR MIDI Lite v1.2.0

This release modernizes the interface and improves playback timing while keeping the existing instrument profiles and MIDI behaviour familiar.

## Main changes

- New rounded two-column interface with clearer setup, song, playback, and song-check sections.
- Added **by MrEz** to the header.
- Added a manual theme selector that remembers your choice.
- Includes Light, Dark, Dracula, Nord, Catppuccin Mocha, Solarized Dark, and Tokyo Night.
- Reorganized Custom controls into Notes and Timing tabs.
- Simplified labels and removed the visible Test input and Copy diagnostics tools.

## Timing improvements

- Control-key taps no longer sleep inside the MIDI scheduling thread.
- Progress text is updated less often to reduce unnecessary playback work.
- Experimental `<` and `>` page changes now guarantee a short safety gap before the next playable input.
- When extra page-switch time is needed, later events move with it instead of rushing afterward.
- MIDI notes are not intentionally skipped by this guard.

## Compatibility

- Windows 10 or Windows 11, 64-bit.
- Administrator permission is still required for reliable BPSR input.
- Existing Keyboard, Guitar, Bass, fixed profiles, Custom settings, song checks, and F10 emergency stop remain available.
