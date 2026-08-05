BPSR MIDI Lite page-switch timing patch

Upload these files to the same paths in the repository:

1. player.py -> replace the root player.py
2. tests/test_player.py -> add this test file inside the tests folder

What changes:
- Every < or > page press starts a 50 ms runtime safety guard.
- The next note, Ctrl/Shift change, or pedal input waits until the page is ready.
- Only missing delay is added. An existing MIDI gap is reused when it is already long enough.
- Any added delay shifts all later events, so the song does not rush to catch up.
- Note-off events remain immediate to prevent stuck or overlong notes.
- Shift/Ctrl/page/pedal taps no longer sleep inside the MIDI scheduler.
- Playback status updates are throttled to reduce UI overhead.
- No MIDI notes are intentionally skipped.

The existing Custom profile Page delay setting is still respected by the planner.
This patch adds a final 50 ms runtime minimum only when events are too close together.
