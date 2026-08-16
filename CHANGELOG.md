# Changelog

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

- Restored the mandatory Windows Administrator manifest after real BPSR testing showed that standard-permission input was not reliable.
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
