# Changelog

## v2.3.0

- Replaced Advanced setup with explicit BPSR Category choices plus **Raw MIDI — no remap**.
- Piano Category 4 still plays only inside **C2–B6**, so selectable profiles never require `<` / `>`.
- Guitar is capped to **E2–D6** and Bass to **E1–B3** for safe no-page playback.
- Raw MIDI preserves pitches and full chords; physically unavailable pitches are skipped instead of remapped.
- Removed playback-style, mapping, chord, page-delay, note-length, sustain, and percussion controls from the UI; safe defaults are automatic.
- Removed Minimize-after-Play and automatic minimizing. The app stays open while the user returns to BPSR.
- Song speed remains the normal user-facing musical control.
- Play is blocked if a selectable profile ever unexpectedly generates a page-key event.

## v2.2.0

- Removed the separate Settings window. **More settings** now expands and collapses inside the main app window.
- Added an always-visible **Song speed** control for every unlock tier, with **100% = original MIDI speed** and a one-click reset to 100%.
- Song speed is now independent from First unlock, Second unlock, Fully unlocked, and Advanced setup; changing instrument/profile no longer silently resets the chosen speed.
- Added a dedicated `song_speed_percent` preference so old profile-managed 85% configuration cannot unexpectedly return after upgrading.
- Kept advanced note fitting hidden unless **Advanced setup…** is selected, while countdown, minimization, library tools, and troubleshooting remain available from the same-window settings area.
- Kept Troubleshooting collapsible inside the same window instead of opening another dialog.
- Added regression coverage for preserving song speed across profile changes.

## v2.1.0

- Restored normal MIDI tempo to **100%** for every beginner profile instead of slowing all songs to 85%.
- Restored authored note lengths to **100%** instead of stretching every note to 135–150%.
- Added a focused **70 ms minimum key hold** so very short MIDI taps are still visible to BPSR without rewriting normal notes.
- Reduced repeated-key release separation to **16 ms** and only applies early release when the same pitch or physical game key must retrigger.
- Fixed legitimate held notes being cut short just because an unrelated note started. Polyphony and legato now survive conversion.
- Capped malformed dangling notes at 500 ms instead of potentially holding a key until the end of the file.
- Kept page-switch timing, octave/modifier lead, sustain behavior, range mapping, chord handling, and the high-resolution playback scheduler unchanged.
- Added regression tests for short-note recognition, polyphonic note holds, malformed dangling notes, and beginner-profile timing defaults.

## v2.0.0

- Rebuilt the main interface around four beginner actions: **Instrument → Unlocked range → Song → Play**.
- Added **Add MIDI…** so users can choose files normally; the app copies them into the song library, refreshes the list, selects the new song, and checks it automatically.
- Removed manual Refresh, theme selection, input-method selection, timing controls, diagnostics, and other technical choices from the main screen.
- Moved countdown, minimization, Advanced song fitting, keyboard-input testing, and support diagnostics into **Settings** and **Troubleshooting**.
- Rewrote unlock-profile names and descriptions in plain language while keeping the established planner settings unchanged.
- Replaced detailed MIDI statistics on the main screen with simple readiness messages such as **Ready to play**, **Playable, but this song is busy**, and **This song may sound crowded**.
- Disabled Play until the selected MIDI has been successfully planned.
- Kept F10 as the always-available emergency stop.
- Preserved the established MIDI engine, instrument ranges, note folding/remapping, chord handling, sustain behavior, note-duration handling, modifier switching, guarded `<` / `>` page switching, and timing compensation.
- Rewrote README and end-user documentation for the new no-manual-needed workflow.

## v1.2.0

- Redesigned the app with a cleaner rounded two-column interface.
- Added **by MrEz** to the main header.
- Added a manual theme selector below the version badge.
- Added seven saved themes: Light, Dark, Dracula, Nord, Catppuccin Mocha, Solarized Dark, and Tokyo Night.
- Reorganized advanced Custom settings into **Notes** and **Timing** tabs.
- Simplified labels, instructions, and status text.
- Removed the visible **Test input** and **Copy diagnostics** controls.
- Prevented control-key taps and frequent UI status updates from blocking MIDI timing.
- Added a guarded wait after `<` or `>` page changes and shifts later events by the same delay instead of rushing.
- Relaxed a flaky Windows CI timing assertion while keeping page-guard coverage.
- Updated the README, user guide, screenshot, release notes, and Windows version metadata.

## v1.1.1

- Restored the mandatory Administrator manifest after real BPSR testing showed that standard-permission input was not reliable.
- Removed the in-app Administrator restart button and optional elevation helper.
- Kept the song suitability rating and **Copy diagnostics** feature from v1.1.0.
- Updated setup, troubleshooting, release, and validation documentation.

## v1.1.0

- Removed the mandatory Administrator manifest and UAC prompt.
- The app now starts in Standard mode and provides an optional **Restart as Administrator** button.
- Added automatic song suitability ratings: **Good fit**, **Busy**, and **Very complex**.
- Suitability explains density, chord size, remapping/removal ratio, tracks, percussion, and page-switch pressure.
- Added **Copy diagnostics** for tester-friendly bug reports.
- Added source complexity metrics to MIDI analysis.
- Updated documentation and Windows version metadata.

## v1.0.0

- First public-ready release of BPSR MIDI Lite.
- Supports Keyboard, Guitar, and Bass with instrument-specific unlock profiles.
- All fixed profiles avoid `<` / `>` page switching.
- Added a visible reminder to prefer simple piano, melody, or solo-instrument MIDI files.
- Clarified that dense orchestral, full-band, percussion-heavy, and multi-instrument arrangements may sound crowded or strange in-game.
- Keeps MIDI library, automatic preview, input testing, F10 emergency stop, standalone EXE packaging, and automatic Windows light/dark theme.

## v0.6.0

- Added an Instrument selector before Profile.
- Added Guitar support:
  - Tier 1 C3–B4
  - Tier 2 E2–B4
  - Tier 3 E2–D6
  - Custom experimental full range
- Added Bass support using the in-game layouts shown by the user:
  - Tier 1 E1–B2 Default layout
  - Tier 2 E1–B3 High Octave (Shift) layout
  - No Low Octave Ctrl mode
- Bass chord simplification now keeps the lowest notes rather than melody notes.
- Each instrument remembers its own selected profile and Custom settings.
- Reverted the Online Sequencer downloader/search integration.
- `Find Songs Online` now only opens the public Online Sequencer sequences page in the browser.
- Fixed profile previews and instructions to mention the selected instrument.
- Kept Windows automatic light/dark theme support.

## v0.5.2

- Added the earlier Online Sequencer integration, later removed in v0.6.0 in favor of a simple browser link.