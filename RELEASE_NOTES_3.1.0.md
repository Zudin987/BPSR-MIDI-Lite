# BPSR MIDI Lite v3.1.0 + Studio 0.2.0 Experimental Beta

## 2026 single-window gaming utility UI

- Rebuilt the presentation layer as one responsive desktop window while keeping the existing MIDI planner, profile fitting, BPSR key mapping, input backends, hotkeys, and no-page safety rules intact.
- Added a three-pane Bento layout: collapsible song/source library, central live MIDI waterfall + Song Check, and collapsible session/router settings.
- Added an anchored bottom control dock with BPSR instrument/category preset, 25–200% tempo/speed control, playback progress, Play, Pause/Resume, and Panic Stop (F10).
- Added a reactive five-second note waterfall generated directly from the prepared BPSR playback events, plus active virtual-key indicators and a lightweight activity meter.
- Added an inline track/channel routing summary based on source track count, percussion handling, and planned chord density.
- Added best-effort Windows 11 dark Mica backdrop; the UI remains fully functional when Mica is unavailable.
- Compact mode automatically collapses side panels while the playback controls remain visible.
- Playback errors are surfaced inline instead of opening a secondary application dialog.

## Online Sequencer title search — Lite and Studio

- Restored in-app title search without requiring users to find a song online and copy its link/ID first.
- Search first tries Online Sequencer's public search page normally.
- If Cloudflare expects an existing browser session, the Windows app can reuse the user's Firefox Online Sequencer cookies with the matching installed Firefox user-agent. Cookies are never displayed, copied into app settings, or sent anywhere except `onlinesequencer.net`.
- If Online Sequencer still asks for a browser challenge, **Verify once** opens only the real Online Sequencer search page. Complete the verification, return to BPSR MIDI, and press Search again — no cookie/link/ID copying is required.
- Direct sequence URLs and numeric IDs remain supported as a fallback.
- Local MIDI remains isolated and continues working if Online Sequencer is unavailable.

## Playback

- Added true Pause/Resume to the anchored player. Active BPSR note keys are released while paused and restored on resume; the playback clock shifts by the pause duration so notes do not burst to catch up.
- F10 remains the global Panic Stop and always releases held input/state.

## Studio

- Studio keeps the same single-window shell and Online Sequencer search as Lite.
- Existing experimental YouTube search → audio → core transcription → MIDI → BPSR fit workflow remains available.
- Studio remains clearly labeled **Experimental Beta** and continues to ship as a separate heavier single EXE.
