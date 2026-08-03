# Changelog

## v0.4.3

- Fixed the Win32 `INPUT` structure used by `SendInput`.
  - v0.4.2 defined the union with only `KEYBDINPUT`, producing a 32-byte
    structure on 64-bit Windows.
  - Windows requires the complete 40-byte `INPUT` structure, whose union also
    contains `MOUSEINPUT` and `HARDWAREINPUT`.
- Added selectable input methods:
  - Win32 scan code
  - Pynput compatibility
  - Win32 virtual key
  - Legacy `keybd_event`
- The Notepad input test now reports the selected method and ABI size.
- Added regression tests for the Win32 structure layout.

## v0.4.2

- Added Administrator manifest and input test.

## v0.4.1

- Added persistent MIDI library folder.
