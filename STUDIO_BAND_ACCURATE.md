# Studio Audio → Band beta

Studio **0.5.0-band-accurate-beta.8** converts a local song or an automatically acquired song into Piano, Guitar, Bass and Drums. This branch builds on the Band Mode v4 development branch (PR #35); it remains a beta for evaluation, not a stable release.

## Use

1. Open Studio's **Audio → Band** tab and its workspace.
2. Either choose/drop a local MP3, WAV, FLAC, M4A or OGG file, or type a song title/artist into the **Auto** search row. Manual local input is permanent and does not require an online downloader.
3. Studio uses spotDL/Spotify metadata as its preferred music search. On first use it creates an isolated Python 3.11 runtime and installs pinned `spotdl==4.5.2`; it also prepares Deno/yt-dlp support.
4. Select the correct track and click **Download & Analyze**. Studio asks for an explicit rights confirmation before acquiring online audio.
5. spotDL first attempts its normal YouTube / YouTube Music match and download. If spotDL search, matching or provider download fails, Studio automatically uses its verified direct yt-dlp + Deno fallback; no second fallback button is required.
6. Leave **Main melody: Auto** and **Stem quality: Auto**, or choose Piano/Guitar explicitly.
7. Local audio uses **Analyze & Convert**. Successfully acquired online audio enters the same Audio → Band pipeline automatically.
8. Review the four parts and warnings. Preview the whole band, solo a part or mute parts.
9. Change melody ownership or instrument categories and apply the arrangement again. This uses the saved musical map and does not rerun audio models.
10. Export the MIDI files and `Arrangement.json` to keep them outside the temporary cache. **Use FullBand in player** opens the existing Song Check/player without starting playback.

The workspace fits itself inside the current desktop. On smaller screens, use the visible scrollbar or mouse wheel to reach preview/export controls; search and summary tables include horizontal scrolling when needed.

The export contains `Song - Piano.mid`, `Song - Guitar.mid`, `Song - Bass.mid`, `Song - Drum.mid`, `Song - Full Band.mid` and `Song - Arrangement.json` (with the actual song name). All parts share the original audio clock, including leading silence. High-confidence beat intervals provide a shared MIDI tempo map. Unknown tempo uses a 120 BPM transport without claiming that it is the detected song tempo.

## Automatic downloader and manual input

The Audio → Band source row uses an automatic two-stage downloader:

| Priority | Source | Studio behavior | Full audio used by AI? |
| --- | --- | --- | --- |
| 1 | spotDL | Spotify metadata identifies the track; spotDL matches YouTube / YouTube Music audio | Yes, after the user confirms they are allowed to download/analyze it |
| 2 | direct yt-dlp fallback | Automatically searches/downloads the best YouTube candidate if spotDL search/matching/provider download fails | Yes, after the same rights confirmation |
| Manual | Local file | User chooses or drops MP3/WAV/FLAC/M4A/OGG | Yes; this always remains available |

Spotify is used for track metadata/identity; Studio does not download Spotify audio streams. Direct fallback candidates are scored using artist/title and, when available, duration similarity. Obvious cover, karaoke, reaction, nightcore, slowed, sped and remix variants are penalized unless the requested Spotify title itself indicates that variant.

The downloaded file is limited to 2 GB, validated as MP3, SHA-256 hashed, atomically committed to the verified acquisition cache and then sent through the normal Audio → Band pipeline. Cached copies are reused only when their recorded size and SHA-256 still match. Fallback provenance and the original spotDL failure are recorded.

## Frozen Windows model-worker isolation

Studio's main one-file EXE is built with Python 3.10, while the heavy separation/transcription engines intentionally run in isolated managed Python 3.11 environments. A frozen one-file application extracts its Python 3.10 extension modules to a temporary `_MEI...` directory while running.

Beta.5 launched the external model worker script directly from that `_MEI` root. Python places the script directory first on `sys.path`, so the managed Python 3.11 interpreter could accidentally import a Python 3.10 extension from the frozen application's extraction directory (for example `_socket.pyd`). Windows then reports `Module use of python310.dll conflicts with this version of Python` and stem separation cannot start.

Beta.6 fixes this boundary by staging the external model worker and the `studio_band` Python source files into a content-addressed **source-only** bundle under Studio's persistent runtime directory before Python 3.11 starts. No `.pyd` or DLL from the PyInstaller extraction directory is copied into that bundle. Existing installed separator/piano/beat/MT3/HQ runtimes remain valid and are reused; this fix does not require reinstalling a ready model runtime.

Windows CI now creates an actual managed Python 3.11 environment and invokes the external provider protocol through the frozen Python 3.10 Studio EXE. This directly covers the cross-version boundary that failed in beta.5, in addition to the existing model and frozen Basic Pitch checks.

## Analysis and recovery

Before first analysis, Studio prepares every missing preferred runtime in a separate **First-time setup** phase. Downloaded components are cached for later songs. A setup/install/import failure ends the job immediately; it is never treated as a normal model-quality fallback. The persistent progress area shows the active stage, weighted overall percentage and elapsed time. Exact transferred bytes are shown only for downloads that expose a real content length; inference stages remain at their completed-phase boundary until the model returns.

Subprocess exit, missing worker response and dead background-job conditions restore the controls and stop the progress bar. A concise reason stays in the main window, while captured stdout/stderr and progress history remain under **Details**. Two minutes without observable child-process output produces a health-check warning but does not kill valid long-running inference.

| Stage | Preferred implementation | Recovery |
| --- | --- | --- |
| Audio preparation | Bundled FFmpeg; stereo 44.1 kHz floating-point WAV | Clear error for unreadable audio |
| Standard separation | Demucs `htdemucs_6s` | CPU retry after a CUDA failure; repair runtime if unavailable |
| HQ separation | BS-RoFormer vocals/instrumental, then Demucs instrumental stems | Standard six-stem separation |
| Beat/downbeat | Beat This! `final0` | Low-confidence spectral tempo estimate; no invented downbeats |
| Vocal melody | Basic Pitch ONNX plus monophonic cleanup | Report transcription failure |
| Piano | Transkun V2 | Basic Pitch with a piano register |
| Guitar / bass / other | Separately tuned Basic Pitch ONNX | Report transcription failure |
| Musical cross-check | MR-MT3 | Continue without cross-check and record the failure |
| Drums | Optional user-installed ADTOF PyTorch | MR-MT3 kit events validated against dedicated spectral onsets; spectral kick/snare/hat detection when MR-MT3 is unavailable |

Auto uses HQ only when its runtime/model directory already exists and the machine reports at least 6 GB NVIDIA VRAM and 16 GB RAM. Explicit HQ can install the additional backend. Each worker tests an actual CUDA kernel and otherwise uses CPU. CPU conversion can be much slower than the song duration. Current input limits are 2 GB and 30 minutes. Six aligned stems are required; an unseparated mix is never represented as six isolated instruments.

The common musical map records source, role, pitch or drum semantics, onset, duration, velocity, confidence and provenance. Cross-check evidence adjusts confidence; it does not append every detected note. Missing cross-check notes are weak negative evidence, not a veto. Repeated riffs, melody continuity, harmonics, register, shared beat proximity and sustained polyphony inform cleanup and arrangement. Small timing corrections are bounded; grace notes, swing and intentional offsets are retained rather than hard-quantized.

Confidence values are **heuristic evidence scores**, not calibrated probabilities. Basic Pitch activation amplitude, MIDI-only engine priors and source-quality priors are identified in the manifest. Demucs stem RMS is measured; source purity is left unknown. Synthetic CI verifies execution, alignment and export, not transcription accuracy on arbitrary commercial songs.

## BPSR arrangement and drums

Auto chooses one main-melody owner for the song using register, octave fitting, phrase density, riff load and accompaniment pressure. Explicit Piano/Guitar ownership wins. Vocal melody has priority over accompaniment; actual piano chords remain available when Guitar owns melody. The existing Band v4 phrase classifier handles ambiguous material, and the existing BPSR range, contour and sustained-note state planner fit the resulting pitched parts.

Drums are semantic events, never pitched Basic Pitch notes. The external [`profiles/bpsr_drums.json`](profiles/bpsr_drums.json) constrains them to the verified 24 pads, MIDI 60–83 (C4–B5), with no octave/page modifiers. **The pad range is verified; kick/snare/hat/tom/cymbal assignments are provisional.** Use **Advanced → Drum mapping** after in-game calibration. Preview converts these semantics to General MIDI sounds; exported Drums use the BPSR pad map.

## Runtime, cache and packaging

The Studio GUI imports no Torch, Demucs, Transkun, Beat This!, MT3 or RoFormer. Heavy engines run sequentially in separate managed Python 3.11 environments; Demucs's older Torch cannot conflict with the other engines or Basic Pitch. The pinned uv bootstrap archive is checked against its SHA-256 before use.

On Windows, Transkun 2.0.1's unpinned `ncls` dependency is resolved through a generated uv constraint containing `ncls==0.0.68`, the release that provides a CPython 3.11 x64 Windows wheel. Studio also passes `--only-binary ncls`; if that compatible wheel ever becomes unavailable, setup fails clearly instead of trying to compile C code or asking the user to install MSVC. `transkun`, `ncls` and their exact versions are verified before the piano runtime receives a ready manifest.

spotDL follows the same isolation principle but uses its own small runtime. On first search Studio uses the existing pinned/verified uv bootstrap to create `runtime/spotdl`, installs `spotdl==4.5.2`, records the resolved package freeze, and attempts spotDL's Deno helper. Studio passes its bundled FFmpeg explicitly to spotDL. No system Python or Spotify login is required for the normal automatic search path.

The default per-user location is `%LOCALAPPDATA%/BPSR-MIDI-Studio/band-accurate` (or `BPSR_STUDIO_BAND_HOME` when set). Jobs keep prepared audio, stems, raw analysis, the master map, manifests and exports. Stage keys include audio SHA-256, engine/model identity, installed package manifest and settings; output hashes detect incomplete or corrupted cache entries. Atomic writes and job locks permit retry after failure. Cancellation kills the worker process tree and retains completed stages.

Idle jobs expire after 14 days or when the 20 GB job cache budget is exceeded; active jobs and exported copies are kept. Model downloads are managed separately and are not silently evicted. Acquired online audio uses the separate verified `acquired-audio` cache under the same root and follows the same cleanup policy.

`Arrangement.json` is self-contained: reopening and changing ownership works without source audio, cached stems or model runtimes. Errors expose stage details and recorded fallbacks. Advanced offers install/repair controls for the transcription/separation engines; spotDL repairs itself automatically if its managed runtime is missing or replaced.

## Third-party model/license notes

| Component | Upstream / packaging decision |
| --- | --- |
| spotDL | [spotDL, MIT](https://github.com/spotDL/spotify-downloader); pinned `4.5.2`, installed into an isolated runtime on first use |
| yt-dlp | Existing Studio YouTube helper; direct fallback uses the SHA-256-verified helper and Deno support |
| Basic Pitch | [Spotify, Apache-2.0](https://github.com/spotify/basic-pitch); existing Studio ONNX engine |
| Demucs | [Meta, MIT code](https://github.com/facebookresearch/demucs); separate package and model download |
| Transkun V2 | [Yujia Yan, MIT](https://github.com/Yujia-Yan/Transkun); separate runtime, pretrained files supplied by its package |
| Beat This! | [CPJKU, MIT](https://github.com/CPJKU/beat_this); separate checkpoint download |
| MR-MT3 | [Official implementation, MIT](https://github.com/gudgud96/MR-MT3); [mt3-infer wrapper](https://github.com/openmirlab/mt3-infer) selects `mr_mt3` explicitly |
| BS-RoFormer | [audio-separator, MIT wrapper](https://github.com/nomadkaraoke/python-audio-separator); fixed vocal checkpoint downloaded separately |
| ADTOF | [Original project, CC BY-NC-SA 4.0](https://github.com/MZehren/ADTOF); [PyTorch port](https://github.com/xavriley/ADTOF-pytorch) has no declared repository license; never bundled or automatically installed |
| uv | [Astral, MIT / Apache-2.0](https://github.com/astral-sh/uv); separately downloaded runtime manager |
| tkinterdnd2 | [MIT wrapper and included TkDND notices](https://github.com/pmgagne/tkinterdnd2); Studio-only file drop support |

Code licenses do not establish redistribution rights for every model weight or for music content. No optional AI weights are committed to this repository. Users who have an appropriate ADTOF installation may provide it in `runtime/drums` with `adtof_pytorch.transcribe_to_midi`; Studio detects this optional environment.

See `STUDIO_THIRD_PARTY_NOTICES.md` for runtime/tool notices including spotDL, yt-dlp, Deno and FFmpeg.

## Development checks

Run `python -m pytest -q` for regression tests. The Studio build workflow executes the real Tk workspace smoke at 640×480, validates failure/cancellation/re-arrangement, builds the single EXE, verifies the frozen Basic Pitch worker, then creates managed Python 3.11 and verifies the external source-only model worker can load the provider registry without importing the frozen Python 3.10 payload. The separate Windows **Studio real audio smoke** starts from a unique empty runtime root, enforces and records the compiler-free Transkun/NCLS policy, imports the installed packages and requires actual Demucs, Beat This!, Transkun and MR-MT3 execution; a separate job verifies HQ RoFormer separation and sample-count alignment.

Downloader unit coverage validates result normalization, fallback scoring/selection, URL validation and shell-free command construction. Live downloader CI verifies public search results only and deliberately does not download copyrighted music.

Windows CI builds both applications and checks that Lite's archive has no AI, ONNX, FFmpeg or Studio payload. Builds from this development PR remain beta artifacts; they do not publish a stable release or merge the Band Mode branch.
