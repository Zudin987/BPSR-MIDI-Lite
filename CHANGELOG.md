# Changelog

## v0.5.1

- Simplified the fixed profile list to Tier 1, Tier 2, Tier 3, and Custom.
- Changed Tier 3 from A0–B6 to the safe C2–B6 middle-page range.
- Tier 3 now guarantees zero `<` / `>` page presses using Ctrl / Default / Shift only.
- Removed Tier 4 from the normal profile list.
- Kept A0–C8 as a Custom-only full-range option for users who want to test page switching.
- Full range solo is now hidden for Custom Tier 1, Tier 2, and Tier 3.
- Added automatic Windows light/dark theme detection.
- Added live theme refresh while the app remains open.
- Added dark title-bar support where Windows permits it.
- Added profile and theme regression tests.

## v0.5.0

- Added beginner-friendly fixed profiles and a Custom profile.
- Fixed Tier profiles lock all musical playback settings.
- Hid advanced settings unless Custom is selected.
- Removed the redundant Analyze button; previews update automatically.
- Simplified MIDI library controls to Open Folder and Reload.
- Added visible `by MrEz` authorship and updated Windows metadata.

## v0.4.3

- Fixed the 64-bit Win32 `INPUT` structure used by `SendInput`.
- Added selectable Win32/Pynput input methods and ABI regression tests.

## v0.4.1

- Added persistent MIDI library folder.
