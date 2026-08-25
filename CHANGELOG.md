# Changelog

## v3.1.2

- Defaulted fresh installs and unspecific legacy settings to Category 1 instead of silently assuming the highest Piano, Guitar, or Bass unlock.
- Made Stable planning reject under-led Ctrl/Shift changes and prefer safe local octave fitting during rapid register alternation.
- Merged physically impossible same-key repeats, reported dropped/merged retriggers honestly, and measured peak simultaneously held keys instead of only exact-onset chords.
- Applied chord limits to lightly humanized attacks within a conservative 15 ms onset window, including monophonic Bass fitting.
- Added hard no-page checks in the UI and player so a future planner regression cannot start normal playback with `<` / `>` events.
- Added a foreground-process guard that auto-pauses and releases held keys when BPSR loses focus, then resumes on the same game process.
- Made the 30 FPS visualizer use a continuous pause-aware playhead, indexed visible-note rendering, cached grid lines, and a lower idle refresh rate without changing MIDI scheduling.
- Added adversarial regressions for rapid octave changes, close retriggers, humanized Bass chords, held-key polyphony, page blocking, visualizer time, and focus safety.

## v3.0.5

- Added automatic real-title and author lookup after a direct Online Sequencer link/ID is loaded, without opening a visible browser.
- Propagated the resolved title into the Online result row, bookmarks, temporary metadata, and **Save to Local** filename while retaining the sequence ID suffix for traceability.
- Upgraded existing generic `Sequence #ID` cache entries and bookmarks in place, without downloading or reconverting the notes again.
- Kept metadata lookup strictly optional: service failures, limits, and malformed responses fall back to `Sequence #ID` while playback, BPSR analysis, and Local MIDI continue normally.
- Added response-size, text-cleaning, URL-scope, cache-upgrade, bookmark-persistence, filename, and failure-isolation regressions.

## v3.0.4

- Added one explicit **Find online MIDI ID** button beneath **Load link / ID**; it opens only Online Sequencer's public sequence list.
- Kept typed titles and **Load link / ID** from opening a browser automatically, avoiding the redundant three-launcher behavior removed in v3.0.3.
- Made the Song-source notebook resize to the selected tab so Local no longer reserves the empty height needed by the Online results table.
- Kept Online Sequencer and Bookmarks tall enough for their result tables, and preserved dark-mode styling, direct-ID playback, BPSR analysis, bookmarks, Save to Local, and Local MIDI behavior.
- Added browser-target, single-launcher, and active-tab height regressions.

## v3.0.3

- Removed the three redundant browser-opening paths from the Online Sequencer and Bookmarks tabs.
- Replaced **Check link / ID** plus **Find in browser** with one honest **Load link / ID** action that never opens a browser.
- A typed title now stays inside BPSR MIDI Lite and clearly explains that Online Sequencer does not publish an app-accessible title-search API.
- Kept direct link/ID playback, automatic BPSR fit analysis, temporary cache, bookmarks, Save to Local, Local MIDI isolation, and dark-mode table/notebook colors unchanged.
- Removed the older hidden/legacy **Find Songs Online** browser action as well, so the application has no Online Sequencer browser launcher.
- Added regressions for the one-action UI, no-browser behavior, direct link/ID resolution, Cloudflare data rejection, and dark mode.

## v3.0.2

- Replaced blocked in-app HTML search scraping with a browser-assisted search flow after Online Sequencer put its search/pages behind a Cloudflare browser challenge.
- **Find in browser** opens the real Online Sequencer title search; after choosing a song, paste its link or numeric sequence ID and use **Check link / ID**.
- Direct link/ID loading now uses only Online Sequencer's public binary sequence-data endpoint, with an honest app user agent and no fake browser headers, cookie warm-up, or repeated 403 retry.
- Kept temporary playback, BPSR fit analysis, bookmarks, Save to Local, cache limits, and Local MIDI isolation unchanged.
- Expanded accepted links to include public sequence URLs plus Online Sequencer editor/data URLs containing an `id` query parameter.
- Added regressions for the Cloudflare handoff, single-request sequence-data behavior, browser opening, direct-ID resolution without HTML access, and exact dark-mode notebook/table colors.

## v3.0.1

- Fixed Online Sequencer searches that could return **HTTP 403** on normal desktop/residential connections by using browser-compatible public-request headers, an isolated cookie session, and one safe retry after a homepage warm-up.
- Added a graceful 403 fallback message that keeps Local MIDI unaffected.
- Fixed dark mode for the Online Sequencer/Bookmarks tabs, result table body, selected rows, and table headings.
- **Open on Online Sequencer** now works even with no selected result: it opens the current typed search in the default browser, or the Online Sequencer browser when the search box is empty.
- Added regression tests for browser headers/403 retry, browser-search fallback, and dark-theme widget coverage.

## v3.0.0

- Added a built-in **Online Sequencer** browser alongside the existing Local MIDI library.
- Added public title search plus direct Online Sequencer URL / numeric sequence-ID lookup.
- Online results are converted to temporary standard MIDI and analyzed by the same BPSR planner as Local songs, showing Ready/Busy/Crowded plus Remap/Skip/Filter and playable-note counts before permanent saving.
- Added direct online playback from a bounded temporary cache; a permanent MIDI download is not required before pressing Play.
- Added app-local **Bookmarks** and **Save to Local** for permanent/offline MIDI copies.
- Preserved Online Sequencer note timing/length and tempo markers during conversion; known drum-kit instruments are written to MIDI channel 10 so the existing percussion filter still applies.
- Added conservative network byte/note limits, lazy result analysis, automatic cache expiry, and failure isolation so Online Sequencer outages/site changes do not break Local playback.
- Kept Piano/Guitar/Bass fitting, no-page safety, Raw MIDI behavior, BPSR note timing, and keyboard-input backends unchanged.
- Added parser, conversion, cache-save, generated-MIDI planner, and v3 UI contract tests.

## v2.5.0

- Added instrument-aware hidden fitting policies based on the confirmed in-game Piano, Guitar, and Bass layouts.
- Kept Keyboard/Piano's established fidelity-first mapping unchanged.
- Guitar now uses melody-aware tie-breaking: total remap count still wins first, then the upper melody/chord voice is protected when equally-good fitting choices exist.
- Bass now uses contour-aware octave selection after its lowest-note chord reduction, reducing unnatural register ping-pong and direction reversals.
- Confirmed Bass Category 2 uses one E1–B3 High Octave layout; playback switches High once and stays there instead of bouncing between Default/High.
- Added regression tests for Guitar upper-voice preservation, unchanged Keyboard behavior, single-switch Bass Category 2 playback, and descending Bass contour preservation.
- Kept safe no-page ranges, Raw MIDI behavior, key injection, BPSR timing, and the UI unchanged.

## v2.4.2

- Fixed Guitar/Bass higher Categories using a less stable per-note octave-folding strategy than their lower Categories.
- Guitar Categories 1–3 and Bass Categories 1–2 now use the same stable whole-song fitting strategy before any unavoidable local octave adjustment.
- Kept Keyboard profile behavior unchanged because its current Category progression is already stable in testing.
- Added a true **Remapped** count that includes whole-song transposition as well as local pitch fitting.
- Song Check now explains whole-song semitone shifts separately so a coherent transposition is not confused with unstable per-note folding.
- Kept suitability focused on local distortion/removal rather than penalizing a coherent whole-song key shift as if it were crowding.
- Added Guitar/Bass progression regressions ensuring larger unlock ranges do not increase local pitch-fold distortion on representative melodies.

## v2.4.1

- Removed **Test keyboard input** and **Copy support info**, including the unused diagnostics/test-input implementation.
- Made **Keyboard connection** permanently visible under **Help & recovery** and kept all four input backends available.
- Kept **Help & recovery** to two user choices only: restore recommended settings and keyboard connection.
- Replaced **Add MIDI…** with **Open folder** and added automatic MIDI-library refresh when files are copied or removed.
- Renamed the speed reset action to **Restore song speed to default 100%**.
- Placed **What are you playing?** and **Which category have you unlocked?** side-by-side in the Instrument section.
- Kept the scrollable v2.4 layout, Song Check remap counts, safe instrument mappings, MIDI engine, and playback timing unchanged.

## v2.4.0

- Rebuilt the interface as one vertically scrollable page so all controls remain reachable on smaller displays and short windows.
- Removed **More settings** entirely; there is no secondary settings layer or popup.
- Removed all **Open folder / Open songs folder** buttons from the user interface.
- Moved **Countdown** directly into the Play section.
- Moved **Restore recommended settings** and collapsible **Troubleshooting** directly onto the main page under **Help & recovery**.
- Restored useful conversion detail in **Song check** with explicit **Remapped**, **Skipped**, and **Filtered/simplified** note counts.
- Kept the beginner flow focused on Instrument → Category → Song → Song check → Play while leaving technical fitting automatic.
- Added scroll-aware dark/light theme handling and mouse-wheel scrolling without forcing the app window to grow when Troubleshooting is expanded.
- Consolidated user documentation into a rewritten README and removed stale duplicate release-note/user-guide/screenshot files from the source tree.
- Simplified portable ZIP contents; the app creates its MIDI library itself when needed.

## v2.3.0

- Replaced Advanced setup with explicit BPSR Category choices plus **Raw MIDI — no remap**.
- Piano Category 4 still plays only inside **C2–B6**, so selectable profiles never require `<` / `>`.
- Guitar is capped to **E2–D6** and Bass to **E1–B3** for safe no-page playback.
- Raw MIDI preserves pitches and full chords; physically unavailable pitches are skipped instead of remapped.
- Removed playback-style, mapping, chord, page-delay, note-length, sustain, and percussion controls from the UI; safe defaults are automatic.
- Removed Minimize-after-Play and automatic minimizing. The app stays open while the user returns to BPSR.
- Song speed remains the normal user-facing musical control.
- Play is blocked if a selectable profile ever unexpectedly generates a page-key event.

## v2.2.0

- Removed the separate Settings window. **More settings** now expands and collapses inside the main app window.
- Added an always-visible **Song speed** control for every unlock tier, with **100% = original MIDI speed** and a one-click reset to 100%.
- Song speed is now independent from First unlock, Second unlock, Fully unlocked, and Advanced setup; changing instrument/profile no longer silently resets the chosen speed.
- Added a dedicated `song_speed_percent` preference so old profile-managed 85% configuration cannot unexpectedly return after upgrading.
- Kept advanced note fitting hidden unless **Advanced setup…** is selected, while countdown, minimization, library tools, and troubleshooting remain available from the same-window settings area.
- Kept Troubleshooting collapsible inside the same window instead of opening another dialog.
- Added regression coverage for preserving song speed across profile changes.

## v2.1.0

- Restored normal MIDI tempo to **100%** for every beginner profile instead of slowing all songs to 85%.
- Restored authored note lengths to **100%** instead of stretching every note to 135–150%.
- Added a focused **70 ms minimum key hold** so very short MIDI taps are still visible to BPSR without rewriting normal notes.
- Reduced repeated-key release separation to **16 ms** and only applies early release when the same pitch or physical game key must retrigger.
- Fixed legitimate held notes being cut short just because an unrelated note started. Polyphony and legato now survive conversion.
- Capped malformed dangling notes at 500 ms instead of potentially holding a key until the end of the file.
- Kept page-switch timing, octave/modifier lead, sustain behavior, range mapping, chord handling, and the high-resolution playback scheduler unchanged.
- Added regression tests for short-note recognition, polyphonic note holds, malformed dangling notes, and beginner-profile timing defaults.

## v2.0.0

- Rebuilt the main interface around four beginner actions: **Instrument → Unlocked range → Song → Play**.
- Added **Add MIDI…** so users can choose files normally; the app copies them into the song library, refreshes the list, selects the new song, and checks it automatically.
- Removed manual Refresh, theme selection, input-method selection, timing controls, diagnostics, and other technical choices from the main screen.
- Moved countdown, minimization, Advanced song fitting, keyboard-input testing, and support diagnostics into **Settings** and **Troubleshooting**.
- Rewrote unlock-profile names and descriptions in plain language while keeping the established planner settings unchanged.
- Replaced detailed MIDI statistics on the main screen with simple readiness messages such as **Ready to play**, **Playable, but this song is busy**, and **This song may sound crowded**.
- Disabled Play until the selected MIDI has been successfully planned.
- Kept F10 as the always-available emergency stop.
- Preserved the established MIDI engine, instrument ranges, note folding/remapping, chord handling, sustain behavior, note-duration handling, modifier switching, guarded `<` / `>` page switching, and timing compensation.
- Rewrote README and end-user documentation for the new no-manual-needed workflow.

## v1.2.0

- Redesigned the app with a cleaner rounded two-column interface.
- Added **by MrEz** to the main header.
- Added a manual theme selector below the version badge.
- Added seven saved themes: Light, Dark, Dracula, Nord, Catppuccin Mocha, Solarized Dark, and Tokyo Night.
- Reorganized advanced Custom settings into **Notes** and **Timing** tabs.
- Simplified labels, instructions, and status text.
- Removed the visible **Test input** and **Copy diagnostics** controls.
- Prevented control-key taps and frequent UI status updates from blocking MIDI timing.
- Added a guarded wait after `<` or `>` page changes and shifts later events by the same delay instead of rushing.
- Relaxed a flaky Windows CI timing assertion while keeping page-guard coverage.
- Updated the README, user guide, screenshot, release notes, and Windows version metadata.

## v1.1.1

- Restored the mandatory Administrator manifest after real BPSR testing showed that standard-permission input was not reliable.
- Removed the in-app Administrator restart button and optional elevation helper.
- Kept the song suitability rating and **Copy diagnostics** feature from v1.1.0.
- Updated setup, troubleshooting, release, and validation documentation.

## v1.1.0

- Removed the mandatory Administrator manifest and UAC prompt.
- The app now starts in Standard mode and provides an optional **Restart as Administrator** button.
- Added automatic song suitability ratings: **Good fit**, **Busy**, and **Very complex**.
- Suitability explains density, chord size, remapping/removal ratio, tracks, percussion, and page-switch pressure.
- Added **Copy diagnostics** for tester-friendly bug reports.
- Added source complexity metrics to MIDI analysis.
- Updated documentation and Windows version metadata.

## v1.0.0

- First public-ready release of BPSR MIDI Lite.
- Supports Keyboard, Guitar, and Bass with instrument-specific unlock profiles.
- All fixed profiles avoid `<` / `>` page switching.
- Added a visible reminder to prefer simple piano, melody, or solo-instrument MIDI files.
- Clarified that dense orchestral, full-band, percussion-heavy, and multi-instrument arrangements may sound crowded or strange in-game.
- Keeps MIDI library, automatic preview, input testing, F10 emergency stop, standalone EXE packaging, and automatic Windows light/dark theme.

## v0.6.0

- Added an Instrument selector before Profile.
- Added Guitar support:
  - Tier 1 C3–B4
  - Tier 2 E2–B4
  - Tier 3 E2–D6
  - Custom experimental full range
- Added Bass support using the in-game layouts shown by the user:
  - Tier 1 E1–B2 Default layout
  - Tier 2 E1–B3 High Octave (Shift) layout
  - No Low Octave Ctrl mode
- Bass chord simplification now keeps the lowest notes rather than melody notes.
- Each instrument remembers its own selected profile and Custom settings.
- Reverted the Online Sequencer downloader/search integration.
- `Find Songs Online` now only opens the public Online Sequencer sequences page in the browser.
- Fixed profile previews and instructions to mention the selected instrument.
- Kept Windows automatic light/dark theme support.

## v0.5.2

- Added the earlier Online Sequencer integration, later removed in v0.6.0 in favor of a simple browser link.
