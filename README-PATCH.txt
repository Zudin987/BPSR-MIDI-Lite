BPSR MIDI Lite — Stable playback restore

WHY THIS PATCH EXISTS
The previous page-guard update changed all control taps (page, Ctrl, Shift,
and sustain) to asynchronous key presses and added a second runtime timeline
shift. The MIDI planner already reserves the configured page-change delay.
Those broad runtime changes can make otherwise normal playback feel different.

THIS PATCH
- Restores the established complete key tap behavior for Ctrl, Shift, page,
  and sustain controls.
- Removes the additional runtime page guard and cumulative timeline shifting.
- Continues relying on the existing MIDI planner's configurable page delay
  (220 ms by default).
- Keeps the harmless 10-times-per-second UI progress throttling.
- Does not change modern_ui.py, the theme selector, or any color theme.

UPLOAD/REPLACE
- player.py
- tests/test_player.py

DO NOT REPLACE
- modern_ui.py
- modern_launcher.py
- README.md
- version/theme files

SUGGESTED COMMIT MESSAGE
fix: restore stable MIDI playback timing

RELEASE
- If v1.2.0 has not been published, rebuild v1.2.0 after applying this patch.
- If v1.2.0 is already public, publish the corrected build as v1.2.1.
