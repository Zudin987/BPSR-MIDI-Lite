# 🎹 BPSR MIDI Lite / Studio

A Windows MIDI utility for **Blue Protocol: Star Resonance** Keyboard/Piano, Electric Guitar, and Electric Bass.

The project now ships two editions:

- **BPSR MIDI Lite 3.1.0** — lightweight Local MIDI + Online Sequencer player.
- **BPSR MIDI Studio 0.2.0 Experimental Beta** — everything in Lite plus YouTube/audio-to-MIDI preparation and conversion.

Both editions use the same BPSR playback engine: MIDI parsing, instrument-aware fitting, transposition, track/percussion handling, timing compensation, hotkeys, and Windows key injection stay shared.

## Download

Use the latest **GitHub Release**.

### Lite

Run `BPSR-MIDI-Lite.exe` for the smallest download and normal MIDI playback.

### Studio

Run `BPSR-MIDI-Studio-Experimental-Beta.exe` if you also want YouTube/audio conversion.

Both builds are standalone. End users do **not** need Python installed. The executable requests Administrator permission because BPSR does not consistently accept injected input from a lower-privilege process.

## What's new in 3.1

The old long form has been replaced with a dark, responsive **single-window gaming utility**.

- Collapsible **MIDI Library** on the left.
- Central **Live MIDI** waterfall showing the actual prepared BPSR key stream.
- Inline **Song Check** with Ready / Busy / Crowded status and remap/skip/filter counts.
- Collapsible **Settings / session** area instead of detached windows.
- Permanently anchored **Preset, Tempo/Speed, Play, Pause/Resume, Panic Stop, status, and progress** controls.
- Best-effort Windows 11 Mica backdrop with a normal dark fallback.
- Compact-player behavior when the window becomes narrow.
- Safe **Pause/Resume** that releases held notes while paused and resumes without a catch-up burst.
- **F10 Panic Stop** remains available at all times.

The interface is still one application window. No floating playback overlay or secondary settings window is required.

## Quick start

1. Choose **Keyboard**, **Guitar**, or **Bass**.
2. Choose the BPSR **Category** you have unlocked.
3. Choose **Local**, **Online Sequencer**, **Bookmarks**, or **YouTube** in Studio.
4. Leave Tempo / speed at `100%` for the original song speed, or adjust it.
5. Read **Song Check**.
6. Press **Play**, then return to BPSR before the countdown ends.

Use **Pause / Resume** when you want to temporarily stop the song without restarting it. Use **F10 / Panic Stop** when you need every held key released immediately.

## Song sources

### Local

Local is the permanent `.mid` / `.midi` library on your PC.

Click **Open folder** to add or remove songs with File Explorer. The library refreshes automatically and works completely offline.

### Online Sequencer

Type a song title, or paste an Online Sequencer URL / numeric sequence ID, then press **Search**.

The app first tries Online Sequencer's public search normally. If the site requires a browser verification session, **Verify once** opens the real Online Sequencer page so you can complete that check in Firefox and return to the app. No manual cookie, DevTools, URL, or sequence-ID copying is required for normal title search.

When a compatible Firefox Online Sequencer session already exists, the search bridge can reuse the site's cookie together with the installed Firefox user agent. That cookie is not displayed, saved in app settings, or sent to unrelated hosts.

Direct sequence URL / ID loading remains available as a fallback.

Online results show:

- **BPSR fit** — Ready, Busy, Crowded, Too large, or Unavailable.
- **R** — notes remapped to fit the selected instrument/category.
- **S** — skipped notes.
- **F** — filtered/simplified notes.
- **Playable** — final playable-note count.

Selected songs are converted into temporary standard MIDI and passed through the same BPSR planner used for Local songs. Use **Save to Local** when you want a permanent offline MIDI copy.

### Bookmarks

Bookmarks remember Online Sequencer songs without permanently downloading them.

If the temporary cache expires, the app fetches the song again when needed. Use **Save to Local** for a true offline copy.

### YouTube — Studio only

Studio adds a **YouTube** source tab.

Search by title, choose a result, and Studio automatically gets the available audio, builds a cleaner/core MIDI, runs the normal BPSR Song Check, and makes the converted MIDI playable in the same window.

There is **no Studio account, sign-in, or subscription**. Restricted or inaccessible videos are simply skipped.

For the cleanest result, prefer uploads such as:

- instrumental
- piano cover
- guitar cover
- bass cover
- karaoke
- melody-focused cover

Full vocal/full-band mixes are harder to transcribe cleanly because several instruments and voices overlap at once.

Studio keeps downloaded audio temporary by default. Use **Save MIDI to Local** when you want to keep the generated MIDI permanently.

## Live MIDI visualizer

The waterfall is not a decorative approximation. It is built from the already-prepared BPSR `PlannedEvent` stream, so it previews the note/key events the playback engine intends to send after fitting.

The visualizer refreshes every **80 ms**, which is about **12.5 visual updates per second**. Playback itself is not limited to 12.5 Hz: the MIDI scheduler uses high-resolution timing independently of the visual refresh.

The UI status queue updates every 50 ms, while F10 is polled every 60 ms. Those are UI/control polling intervals, not MIDI timing resolution.

## Song Check

Song Check uses simple readiness labels plus conversion numbers:

- **Ready to play** — normal fit for the selected BPSR instrument/category.
- **Playable, but this song is busy** — playable, but dense enough that BPSR may sound less clean.
- **This song may sound crowded** — complex arrangement likely to lose clarity in a game keyboard.
- **Remapped** — played notes whose final pitch differs from the source.
- **Skipped** — notes that cannot be played under the selected profile.
- **Filtered/simplified** — percussion or chord notes intentionally removed by the automatic instrument policy.

A coherent whole-song transpose is reported separately from local fitting, so a clean key shift is not mistaken for random pitch distortion.

## Safe Category ranges

### Keyboard / Piano

| Category | Game progression | Safe playback used by the app |
|---|---|---|
| 1 | Starts with C3–B4 | C3–B4 |
| 2 | Unlocks C5–B6 | C3–B6 |
| 3 | Unlocks A0–B2 | C2–B6 |
| 4 | Unlocks C7–C8 | C2–B6 |

Piano Category 3/4 deliberately stays inside **C2–B6** so normal playback can remain on the middle page.

### Electric Guitar

| Category | Game progression | Safe playback used by the app |
|---|---|---|
| 1 | Starts with C3–B4 | C3–B4 |
| 2 | Unlocks E2–B2 | E2–B4 |
| 3 | Unlocks C5–D6 | E2–D6 |

Guitar can reach its safe range with Default/Low/High octave, so normal profiles do not require page keys.

### Electric Bass

| Category | Game progression | Safe playback used by the app |
|---|---|---|
| 1 | Starts with E1–B2 | E1–B2 |
| 2 | High range unlocked | E1–B3 |

Bass has no Low Octave mode. Category 2 switches to High once at playback start, stays there, and resets afterward.

## Instrument-aware fitting

The planner applies hidden musical priorities automatically:

- **Keyboard / Piano** — fidelity-first pitch/chord preservation.
- **Electric Guitar** — protects the upper melody/chord voice when fitting choices are otherwise comparable.
- **Electric Bass** — keeps the low line and uses contour-aware octave choices to reduce unnatural register jumps.

Normal profiles never use `<` / `>` page switching. Outer notes are fitted into the safe range instead.

## Raw MIDI — no remap

`Raw MIDI — no remap` keeps original in-range pitches and full chords.

Out-of-range notes are skipped instead of remapped. Raw mode also keeps the BPSR-safe short-note/retrigger correction and percussion handling, and it never uses `<` / `>` page switching.

## Tempo / speed

`100%` means the original MIDI/sequence tempo.

The supported range is **25%–200%**. Speed is independent from the selected instrument Category.

## Keyboard connection

The recommended input method is **Win32 scan code**.

Other compatibility backends remain available because different Windows/game setups can accept injected input differently:

- Win32 scan code — recommended
- Pynput compatibility
- Win32 virtual key
- Legacy `keybd_event`

If scan code works, leave it unchanged.

## Pause and Panic Stop

**Pause** releases currently held BPSR note keys and freezes the playback timeline.

**Resume** restores the required held-key state and shifts the timeline by the paused duration, preventing a burst of overdue notes.

**F10 / Panic Stop** immediately stops playback and releases held keys/instrument state.

## Lite vs Studio

| Feature | Lite | Studio |
|---|:---:|:---:|
| Local MIDI | ✅ | ✅ |
| Online Sequencer search | ✅ | ✅ |
| Online bookmarks | ✅ | ✅ |
| Save MIDI locally | ✅ | ✅ |
| Live MIDI waterfall | ✅ | ✅ |
| Pause / Resume | ✅ | ✅ |
| YouTube search | — | ✅ |
| Audio → MIDI transcription | — | ✅ |
| Bundled AI/audio runtime | — | ✅ |
| Smallest download | ✅ | — |

Studio is intentionally heavier because it bundles the transcription/audio runtime. Lite remains the better choice when you already have MIDI files.

## Online and third-party notes

Online Sequencer and YouTube are third-party services. This project is not affiliated with or endorsed by them.

Online features can need maintenance when those sites change. Local MIDI playback is intentionally isolated so a website outage or extraction change does not break the core player.

Studio's YouTube source is intended for publicly accessible material the user is permitted to process. The app does not provide a login/DRM bypass workflow.

See `THIRD_PARTY_NOTICES.md` and `STUDIO_THIRD_PARTY_NOTICES.md` for bundled dependency attribution.

## Development

Lite entry point: `modern_launcher.py`

Studio entry point: `studio_launcher.py`

Important modules:

- `midi_engine.py` — MIDI extraction, fitting, transposition, BPSR planning and timing
- `profiles.py` — user-facing instrument/Category policies
- `player.py` — playback scheduler, pause/resume and cleanup
- `win_input.py` — Windows input backends
- `gaming_ui_2026.py` — responsive single-window shell and Live MIDI visualizer
- `gaming_runtime_2026.py` — 2026 runtime integration layer
- `online_sequencer.py` — Online Sequencer sequence client/cache/conversion
- `online_search_bridge.py` — in-app title search and browser-session compatibility bridge
- `online_ui.py` — Online Sequencer/bookmark workflow
- `studio_youtube.py` — Studio YouTube search/audio acquisition
- `studio_core_transcription.py` — Studio audio-to-MIDI transcription pipeline

Run tests:

```text
python -m pytest -q
```

Build Lite:

```text
pyinstaller --noconfirm --clean BPSR-MIDI-Lite.spec
```

Build Studio:

```text
pyinstaller --noconfirm --clean BPSR-MIDI-Studio.spec
```

## License

GNU AGPL-3.0. Created by **MrEz**.
