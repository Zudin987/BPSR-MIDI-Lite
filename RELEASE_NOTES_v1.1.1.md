# BPSR MIDI Lite v1.1.1

This patch restores mandatory Administrator access after real in-game testing.

## What changed

- The EXE now requests Windows Administrator permission whenever it starts.
- Removed the in-app Administrator restart button because elevation is mandatory.
- Removed the optional elevation/restart code.
- Kept automatic **Good fit / Busy / Very complex** song suitability ratings.
- Kept **Copy diagnostics** for easy tester reports.

## Why

The standard-permission v1.1.0 build could send input to normal applications, but BPSR did not reliably receive it. Requiring Administrator access provides the reliable behavior expected from the app.

## Testing

1. Start the EXE and accept the UAC prompt.
2. Test input in Notepad.
3. Test Keyboard, Guitar, and Bass in BPSR.
4. Confirm **Copy diagnostics** still works.
5. Confirm a simple and complex MIDI receive sensible suitability ratings.

Requirements: Windows 10/11 64-bit.
