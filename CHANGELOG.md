# Changelog

## v0.4.2

- Fixed the most likely cause of the game receiving no keyboard input.
- Windows EXE now requests Administrator access through its embedded manifest.
- Added an `A S D F` input test with a three-second countdown.
- Added a visible Administrator-status indicator.
- Corrected the Windows `SendInput` ctypes declarations for 64-bit builds.
- Playback now refuses to start without Administrator access instead of silently doing nothing.

## 0.4.1

- Replaced the single-file Browse field with a saved MIDI library folder.
- Added a MIDI dropdown populated from `.mid` and `.midi` files in the selected folder and its subfolders.
- Added Choose Folder, Open Folder, and Reload buttons.
- The app creates a portable `MIDI` folder beside the EXE on first run, with a Documents fallback when that location is not writable.
- Folder selection and the last selected song are stored in the user's AppData configuration.
- Native folder dialogs are explicitly parented and brought to the front so they do not appear hidden behind the game.
- Added natural filename sorting, including numbered difficulty prefixes.
- Updated GitHub Actions to Node.js 24-based action versions.
- Expanded automated tests from 15 to 17.

## 0.4.0

- Added four explicit unlock-tier presets: C3–B4, C3–B6, A0–B6, and A0–C8.
- Every playback mode now respects the selected character progression.
- Tier 1 uses only Default state; Tier 2 uses Default + Shift without page keys.
- Tier 3 excludes the unnecessary right page, preventing accidental `>` presses before C7/C8 are unlocked.
- Stable mode automatically uses the safe middle-page subset for each tier.
- MIDI analysis now displays the selected unlock tier and effective range for the current mode.
- Added backwards-compatible migration from the old A0–B6/A0–C8 range setting.
- Added a browser-only GitHub upload, build, and release guide for first-time users.
- Expanded GitHub Actions to run tests, build a standalone EXE, package a portable ZIP, generate SHA-256 checksums, and optionally publish a Release.
- Improved the local Windows build script with tests, release packaging, and checksums.
- Added Windows file-version metadata.
- Expanded automated tests from 10 to 15.

## 0.3.0

- Fixed two-page moves: each physical `<` / `>` press is now emitted as a separate scheduled event with the configured animation delay between presses.
- Added explicit tie preference for the current page, then the middle page, instead of allowing candidate enumeration order to choose the left page.
- Added four mapping methods: Octave fold, Nearest playable note, Auto-transpose then fold, and Skip out-of-range notes.
- Added chord limits that preserve bass and melody for dense arrangements.
- Exposed configurable Ctrl/Shift modifier lead time.
- Increased the default page-switch delay from 180 ms to 220 ms.
- Added page-change rate, skipped-note count, and transpose amount to MIDI analysis.
- Added a warning when Full range mode requires very frequent page changes.
- Improved cleanup so multi-step return-to-middle page changes respect the configured delay.
- Expanded automated tests from 4 to 10.

## 0.2.0

- Added Full range solo mode with page-switch scheduling and cumulative timing compensation.
- Added Ensemble-safe mode that refuses unsafe page jumps and folds those notes instead.
- Kept Stable mode as the no-arrow C2–B6 default.
- Added configurable A0–B6 / A0–C8 unlocked range.
- Added configurable page-switch animation delay.
- Added percussion filtering and Melody-only simplification.
- Added page-switch, filtered-note, and timing-compensation analysis.
- Added automatic return to middle page + Default octave after playback.
- Expanded planner tests for all three modes and 150% note duration.
