# Changelog

## v0.5.0

- Added five UI profiles: Tier 1, Tier 2, Tier 3, Tier 4, and Custom.
- Fixed Tier profiles lock all musical playback settings.
- Tier 1 and Tier 2 no longer expose Full range solo.
- Added sensible automatic mapping and chord presets for every unlock tier.
- Hid advanced settings unless Custom is selected.
- Removed the redundant Analyze button; previews update automatically.
- Removed Choose Folder; the app now uses its fixed portable MIDI library.
- Kept only Open Folder and Reload for library management.
- Reworked the song preview into clearer, beginner-friendly language.
- Added visible `by MrEz` authorship and updated Windows metadata.
- Added profile regression tests.

## v0.4.3

- Fixed the 64-bit Win32 `INPUT` structure used by `SendInput`.
- Added selectable Win32/Pynput input methods and ABI regression tests.

## v0.4.2

- Added Administrator manifest and input test.

## v0.4.1

- Added persistent MIDI library folder.
