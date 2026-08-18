# 🎹 BPSR MIDI Lite

A lightweight Windows MIDI player for **Blue Protocol: Star Resonance** Keyboard/Piano, Electric Guitar, and Electric Bass.

BPSR MIDI Lite turns MIDI notes into BPSR keyboard input, automatically fits songs to the Category you have unlocked, uses instrument-aware remapping, and keeps normal playback inside the safe no-page range so it never needs `<` or `>`.

Version 3 adds an optional **Online Sequencer** library: paste a public song link or ID into the app, see how well it fits your current BPSR instrument/category, play it from temporary cache, bookmark it, or save a permanent MIDI copy for offline use.

## Download

Use the latest **GitHub Release** and run `BPSR-MIDI-Lite.exe`.

The release build is standalone; users do **not** need Python installed. The executable requests Administrator permission because BPSR does not consistently accept injected input from a lower-privilege process.

## Quick start

1. Choose **Keyboard**, **Guitar**, or **Bass**.
2. Choose the BPSR **Category** you have unlocked.
3. Choose a song source:
   - **Local** — permanent `.mid` / `.midi` files on your PC.
   - **Online Sequencer** — paste a public song link/ID and play it from temporary cache.
   - **Bookmarks** — revisit online songs you bookmarked earlier.
4. Leave **Song speed** at `100%` for the original tempo, or change it.
5. Read **Song check** to see readiness and how much fitting was needed.
6. Press **Play in BPSR** and return to the game before the countdown ends.

The app stays open during playback. **F10** always stops playback and releases held keys.

## Song sources

### Local

Local is the normal permanent song library. Click **Open folder** and copy/remove `.mid` or `.midi` files with File Explorer. The list refreshes automatically.

Local playback is completely independent from Online Sequencer and continues to work offline.

### Online Sequencer

Online Sequencer puts its HTML/title-search page behind a browser challenge and does not publish an app-accessible search API. BPSR MIDI Lite therefore does not scrape the page or bypass the challenge.

To load a song, paste its full Online Sequencer link or numeric sequence ID and click **Load link / ID**. Pressing Enter does the same thing.

While the song is prepared, the app looks up its public title and author through Microlink's metadata API. The real title is then used in the result row, bookmark, and **Save to Local** filename; the Online Sequencer ID remains in the filename as `[OS ID]`. This lookup is cached and never opens a visible browser. If metadata is unavailable or its free-service limit is reached, the app simply keeps `Sequence #ID` and still downloads, checks, and plays the notes normally.

If you need to find an ID, click **Find online MIDI ID**. This one explicit browser action opens Online Sequencer's public sequence list. Choose a song there, copy its link or numeric ID, then return to BPSR MIDI Lite. Typing a title such as `Taylor` still does not open anything automatically.

The selected song is checked using the **same BPSR planner used for Local MIDI files**. The result list shows:

- **BPSR fit** — Ready, Busy, Crowded, Too large, or Unavailable
- **R** — notes remapped to fit your selected instrument/category
- **S** — skipped notes
- **F** — filtered/simplified notes
- **Playable** — final playable-note count

Selecting an online song converts the public sequence data into a temporary standard MIDI file, then sends that temporary MIDI through the existing BPSR planner. Nothing has to be permanently downloaded before you press **Play in BPSR**.

The temporary cache is bounded and old entries are deleted automatically. It behaves like a playback cache, **not** like your permanent Local library.

Use **Save to Local** when you want a permanent `.mid` copy for offline use.

### Bookmarks

**Bookmark** stores the Online Sequencer sequence ID/title in BPSR MIDI Lite so you can find it again quickly.

A bookmark is not an offline download. If its temporary cache has expired, the app fetches it again when needed. Use **Save to Local** for a permanent offline copy.

### Online service note

Online Sequencer and Microlink are third-party services. BPSR MIDI Lite is not affiliated with or endorsed by either service. After you paste a link/ID, the app sends that public Online Sequencer URL to Microlink only to retrieve its public title/author, then gets the notes from Online Sequencer's public binary sequence-data endpoint. It opens Online Sequencer only when you click **Find online MIDI ID**, and it does not ask for or store Online Sequencer login credentials.

If title lookup fails, the app retains the numeric sequence name. If Online Sequencer changes its public sequence-data format or blocks that endpoint, the online feature may need an update; **Local MIDI playback remains unaffected**.

## Song check

Song Check uses simple readiness labels plus conversion numbers:

- **Ready to play** — normal fit for the selected BPSR instrument/category.
- **Playable, but this song is busy** — playable, but dense enough that BPSR may sound less clean.
- **This song may sound crowded** — complex arrangement likely to lose clarity in a game keyboard.
- **Remapped** — played notes whose final pitch differs from the source.
- **Skipped** — notes that cannot be played under the selected profile.
- **Filtered/simplified** — percussion or chord notes intentionally removed by the automatic instrument policy.

A coherent whole-song transpose is reported separately from local octave fitting so a clean key shift is not mistaken for unstable remapping.

## Safe Category ranges

### Keyboard / Piano

| Category | Game progression | Safe playback used by the app |
|---|---|---|
| 1 | Starts with C3–B4 | C3–B4 |
| 2 | Unlocks C5–B6 | C3–B6 |
| 3 | Unlocks A0–B2 | C2–B6 |
| 4 | Unlocks C7–C8 | C2–B6 |

Piano Category 3/4 deliberately stays inside **C2–B6** so playback can use only Default/Low/High octave on the middle page.

### Electric Guitar

| Category | Game progression | Safe playback used by the app |
|---|---|---|
| 1 | Starts with C3–B4 | C3–B4 |
| 2 | Unlocks E2–B2 | E2–B4 |
| 3 | Unlocks C5–D6 | E2–D6 |

Guitar can reach its complete safe range using Default/Low/High octave, so page keys are unnecessary.

### Electric Bass

| Category | Game progression | Safe playback used by the app |
|---|---|---|
| 1 | Starts with E1–B2 | E1–B2 |
| 2 | High range unlocked | E1–B3 |

Bass has no Low Octave mode. Category 1 uses Default E1–B2. Category 2 uses the single High E1–B3 layout: the player switches High once at the start, stays there for the song, and resets afterward.

## Instrument-aware fitting

The app uses one planner with hidden musical priorities tailored to each BPSR instrument:

- **Keyboard / Piano** — fidelity-first; preserve the original pitches/chords as much as possible.
- **Electric Guitar** — still minimizes total remapping first, then uses conservative upper-melody/chord-voice tie-breaking when choices are otherwise comparable.
- **Electric Bass** — keeps the low line and uses contour-aware octave fitting to reduce register ping-pong, large unnatural jumps, and direction reversals.

There is no Advanced fitting screen. These policies are automatic.

## Raw MIDI — no remap

`Raw MIDI — no remap` is the final Category option for each instrument.

Raw mode:

- keeps original in-range pitches
- keeps full chords
- does not transpose or octave-remap pitches
- still applies the small BPSR-safe short-note/retrigger correction
- ignores MIDI percussion for the pitched BPSR instruments
- skips physically unavailable pitches instead of remapping them
- never uses `<` or `>`

## Song speed

`100%` means the original MIDI/sequence tempo. Song speed is available for every Category and remains independent from the selected unlock level.

**Restore song speed to default 100%** resets only the song speed.

## Keyboard connection

The recommended input method is **Win32 scan code**. Four methods remain available because different Windows/game setups can accept injected input differently:

- **Win32 scan code (recommended)** — Windows `SendInput` with keyboard scan codes.
- **Pynput compatibility** — bundled pynput keyboard controller.
- **Win32 virtual key** — Windows `SendInput` with virtual-key values.
- **Legacy keybd_event** — older Windows input fallback.

If scan code works, leave it unchanged.

## Restore recommended settings

Restore returns the current instrument to its recommended Category, song speed to `100%`, countdown to `3` seconds, and keyboard connection to **Win32 scan code**.

## Development

The release executable is built with PyInstaller from `modern_launcher.py`.

Main modules:

- `midi_engine.py` — MIDI extraction, instrument-aware fitting, BPSR state planning and timing
- `profiles.py` — user-facing instrument/Category policies
- `player.py` — playback scheduler and cleanup
- `win_input.py` — Windows input backends
- `modern_ui.py` — stable beginner-first scrollable interface
- `online_sequencer.py` — Online Sequencer direct-link/public-data client, safe parser, temporary cache and MIDI conversion
- `online_ui.py` — online search/bookmark background workflow and result UI
- `online_integration.py` — thin layer that inserts the online library without replacing the stable modern UI

Run tests:

```text
python -m pytest -q
```

Build the Windows executable:

```text
pyinstaller --noconfirm --clean BPSR-MIDI-Lite.spec
```

## License

GNU AGPL-3.0. Created by **MrEz**. See `THIRD_PARTY_NOTICES.md` for bundled dependency attribution.
