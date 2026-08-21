# 🎹 BPSR MIDI Lite / Studio

A simple Windows MIDI utility for **Blue Protocol: Star Resonance** instruments.

It supports:

- 🎹 Keyboard / Piano
- 🎸 Electric Guitar
- 🎸 Electric Bass

> ## TL;DR
>
> **BPSR MIDI Lite** plays local MIDI files and Online Sequencer songs in BPSR.
>
> **BPSR MIDI Studio** does everything Lite does and can also turn compatible YouTube/audio songs into MIDI.
>
> Download the latest GitHub Release, choose your instrument and song, then press **Play**.
>
> **No Python installation is required.**

## What this app does

BPSR MIDI prepares a song for the instrument range available in BPSR and sends the required keyboard input while the song plays.

Both editions include:

- Local `.mid` / `.midi` playback
- Online Sequencer search and playback
- Keyboard/Piano, Guitar and Bass support
- Automatic note fitting for BPSR
- Song Check before playing
- Live MIDI waterfall
- Adjustable speed
- Pause / Resume
- **F10 Panic Stop**
- Online bookmarks
- Save online songs as local MIDI

**Studio** additionally includes:

- YouTube song search
- Audio → MIDI conversion
- Save converted MIDI locally

The app does **not modify BPSR game files** and does not ask for your BPSR account password.

## Download

Use the latest **GitHub Release**.

| Edition | Best for |
|---|---|
| **BPSR MIDI Lite 3.1.0** | You already have MIDI files or want Online Sequencer |
| **BPSR MIDI Studio 0.2.0 Experimental Beta** | You also want YouTube/audio → MIDI |

### Lite

Run `BPSR-MIDI-Lite.exe`.

This is the smaller version.

### Studio

Run `BPSR-MIDI-Studio-Experimental-Beta.exe`.

Studio is larger because it contains the audio/AI tools needed for conversion.

Both versions are standalone Windows applications. **Python is not required.**

## 🚀 Quick Start — 1, 2, 3

### 1. Open the app

Run the Lite or Studio EXE.

Windows may ask for **Administrator permission**. BPSR can reject keyboard input sent from a lower-privilege application, so the player runs elevated for compatibility.

### 2. Pick your instrument and song

Choose:

**Instrument → Category → Song**

Example:

`Keyboard → Category 3 → Local song`

Leave **Speed at 100%** if you want the song's normal speed.

### 3. Press Play

Check the **Song Check** result, then press **Play**.

Return to BPSR before the countdown finishes.

> **Emergency stop:** press **F10** at any time to stop playback and release held keys.

## Song Sources

### 📁 Local

Use this for MIDI files already on your PC.

1. Open the **Local** tab.
2. Press **Open folder**.
3. Put your `.mid` or `.midi` files there.
4. Choose a song and press **Play**.

Local playback works completely offline.

### 🌐 Online Sequencer

You can:

- Search by song name
- Paste an Online Sequencer link
- Paste a numeric sequence ID

The app first tries a normal public search.

Sometimes Online Sequencer asks for browser verification. If that happens:

1. Click **Verify once**.
2. Complete the check in Firefox.
3. Return to BPSR MIDI.
4. Search again.

When that fallback is needed, the app can read existing `onlinesequencer.net` cookies from the local Firefox profile and send them only back to `onlinesequencer.net` together with the matching Firefox user agent. Cookie values are not shown in the app, saved in app settings, or sent to unrelated hosts.

The app does not ask for your Online Sequencer username or password.

Direct sequence URL / ID loading remains available as a fallback.

### ⭐ Bookmarks

Bookmarks remember an Online Sequencer song without keeping a permanent MIDI copy.

If you want the song available offline, use **Save to Local** instead.

### ▶️ YouTube — Studio only

Studio can search YouTube and convert compatible audio into MIDI automatically.

For cleaner results, prefer uploads such as:

- Piano covers
- Guitar covers
- Bass covers
- Instrumental versions
- Karaoke versions
- Melody-focused covers

A full song containing vocals, drums and many instruments at once is harder to convert cleanly.

Studio does not use your Google/YouTube login or browser cookies. Restricted or inaccessible videos are skipped.

Downloaded audio is temporary. Use **Save MIDI to Local** if you want to keep the resulting MIDI.

## Song Check

Before playing, the app checks how well the song fits your selected BPSR instrument.

### ✅ Ready to play

The song should fit normally.

### 🟡 Playable, but busy

The song works, but some sections may contain many notes at once.

### 🟠 Crowded

The arrangement is complex enough that it may lose some clarity inside BPSR.

You may also see:

- **R — Remapped:** notes moved to a playable BPSR pitch
- **S — Skipped:** notes BPSR cannot safely play
- **F — Filtered:** notes automatically simplified or removed
- **Playable:** final number of notes that will be played

You normally do not need to change anything manually.

## Pause and Emergency Stop

### Pause

**Pause** stops the song temporarily and releases currently held note keys.

### Resume

**Resume** continues from the same place without rapidly playing overdue notes.

### F10 / Panic Stop

Press **F10** if anything goes wrong.

It immediately stops playback and releases the keys controlled by BPSR MIDI.

## Lite vs Studio

| Feature | Lite | Studio |
|---|:---:|:---:|
| Local MIDI | ✅ | ✅ |
| Online Sequencer | ✅ | ✅ |
| Bookmarks | ✅ | ✅ |
| Save MIDI locally | ✅ | ✅ |
| Live MIDI waterfall | ✅ | ✅ |
| Song Check | ✅ | ✅ |
| Pause / Resume | ✅ | ✅ |
| F10 Panic Stop | ✅ | ✅ |
| YouTube search | ❌ | ✅ |
| Audio → MIDI | ❌ | ✅ |
| Smallest download | ✅ | ❌ |

**Use Lite unless you specifically need YouTube/audio conversion.**

<details>
<summary><strong>Instrument / Category ranges</strong></summary>

### Keyboard / Piano

| Category | BPSR progression | Range used by the app |
|---|---|---|
| 1 | C3–B4 | C3–B4 |
| 2 | Unlocks C5–B6 | C3–B6 |
| 3 | Unlocks A0–B2 | C2–B6 |
| 4 | Unlocks C7–C8 | C2–B6 |

Categories 3 and 4 deliberately stay inside **C2–B6** during normal playback so the player does not need constant page switching.

### Electric Guitar

| Category | BPSR progression | Range used by the app |
|---|---|---|
| 1 | C3–B4 | C3–B4 |
| 2 | Unlocks E2–B2 | E2–B4 |
| 3 | Unlocks C5–D6 | E2–D6 |

### Electric Bass

| Category | BPSR progression | Range used by the app |
|---|---|---|
| 1 | E1–B2 | E1–B2 |
| 2 | High range unlocked | E1–B3 |

</details>

<details>
<summary><strong>Advanced input settings</strong></summary>

The recommended input method is **Win32 scan code**.

Other compatibility options remain available:

- Win32 scan code — recommended
- Pynput compatibility
- Win32 virtual key
- Legacy `keybd_event`

If the default works, leave it unchanged.

`Raw MIDI — no remap` is also available for users who want original in-range pitches and full chords. Out-of-range notes are skipped instead of remapped.

</details>

## Privacy & Online Features

### Local MIDI

Local songs stay on your PC.

### Online Sequencer

Public Online Sequencer pages and sequence data are contacted only when you use Online Sequencer features.

If **Verify once** is needed, the app may read existing Online Sequencer cookies from the local Firefox profile and send them only back to `onlinesequencer.net`. The values are not displayed, stored in BPSR MIDI settings, or sent to unrelated hosts.

For some directly loaded sequences, the public sequence URL may also be sent to the **Microlink metadata API** to obtain a display-only title/author. MIDI playback does not depend on this lookup.

### Studio / YouTube

Studio uses **yt-dlp** for public YouTube search/audio retrieval.

It does not use your Google/YouTube login or browser cookies.

Temporary audio is removed after conversion. Generated MIDI is cached for a limited time unless you explicitly save it.

## Safety Notes

BPSR MIDI:

- Does not modify BPSR game files
- Does not ask for your BPSR password
- Does not record arbitrary keyboard typing
- Uses keyboard input only to play the selected BPSR instrument
- Uses F10 as the global Panic Stop hotkey

Online features can stop working temporarily when third-party websites change. **Local MIDI playback remains independent.**

Use only MIDI/audio/content that you are permitted to use or process.

This is an **unofficial fan-made utility**. It is not affiliated with or endorsed by Blue Protocol: Star Resonance, Online Sequencer, YouTube, or their respective owners/operators.

## For Developers

Lite entry point: `modern_launcher.py`

Studio entry point: `studio_launcher.py`

Important modules:

- `midi_engine.py` — MIDI preparation and note fitting
- `profiles.py` — instrument/category rules
- `player.py` — playback and timing
- `win_input.py` — Windows keyboard input
- `gaming_ui_2026.py` — main interface and Live MIDI view
- `online_sequencer.py` — sequence download/cache/conversion
- `online_search_bridge.py` — Online Sequencer title search
- `studio_youtube.py` — Studio YouTube support
- `studio_core_transcription.py` — audio → MIDI processing

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

See `CHANGELOG.md`, `THIRD_PARTY_NOTICES.md`, `STUDIO.md`, and `STUDIO_THIRD_PARTY_NOTICES.md` for additional technical and licensing information.

## License

**GNU AGPL-3.0**

Created by **MrEz**.
