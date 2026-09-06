"""Automatic spotDL -> direct yt-dlp fallback for Studio Audio -> Band.

spotDL stays the default downloader.  If Spotify metadata search is unavailable,
or spotDL cannot match/download the selected track from its audio providers,
Studio falls back to the already-supported standalone yt-dlp + Deno path.
Manual local audio remains independent of both downloaders.
"""
from __future__ import annotations

import json
import re
import shutil
import uuid
import webbrowser
from dataclasses import replace
from difflib import SequenceMatcher
from pathlib import Path
from tkinter import messagebox

import studio_band_ui
import studio_spotdl
import studio_youtube
from studio_band.protocol import StageError, check_cancel, run_process
from studio_band.resolver import AcquiredAudio, ResolverTrack, SearchReport, _audio_signature_matches
from studio_band.storage import atomic_json, file_hash, read_json
from studio_spotdl import MAX_AUDIO_BYTES, SPOTDL_VERSION, SpotDLError, SpotDLResolver

YTDLP_PROVIDER = "yt_dlp"
SPOTDL_SEARCH_TIMEOUT = 45
YTDLP_SEARCH_TIMEOUT = 75
YTDLP_DOWNLOAD_TIMEOUT = 900
YTDLP_SEARCH_LIMIT = 5


def _clean(value, maximum: int = 300) -> str:
    return " ".join(str(value or "").split())[:maximum]


def _normal(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value).casefold()))


def _youtube_track(result: studio_youtube.YouTubeResult) -> ResolverTrack:
    return ResolverTrack(
        provider=YTDLP_PROVIDER,
        provider_id=result.video_id,
        title=result.title,
        artist=result.channel,
        duration_seconds=float(result.duration_seconds) if result.duration_seconds is not None else None,
        store_url=result.url,
        acquisition="ytdlp_direct_download",
        can_acquire=True,
        format_id="mp3",
        suffix=".mp3",
    )


def _youtube_result(track: ResolverTrack) -> studio_youtube.YouTubeResult:
    if track.provider != YTDLP_PROVIDER or not track.provider_id:
        raise SpotDLError("Choose a direct yt-dlp result first.")
    duration = None
    if track.duration_seconds is not None:
        try:
            duration = max(0, int(round(float(track.duration_seconds))))
        except (TypeError, ValueError):
            duration = None
    return studio_youtube.YouTubeResult(track.provider_id, track.title, track.artist, duration)


def _search_command(executable: Path, deno: Path, query: str, limit: int) -> list[str]:
    count = max(1, min(YTDLP_SEARCH_LIMIT, int(limit)))
    return [
        str(executable),
        "--ignore-config",
        "--no-warnings",
        "--js-runtimes",
        f"deno:{deno}",
        "--flat-playlist",
        "--dump-json",
        "--playlist-end",
        str(count),
        f"ytsearch{count}:{query}",
    ]


def _download_command(
    executable: Path,
    deno: Path,
    ffmpeg: Path,
    output_template: Path,
    result: studio_youtube.YouTubeResult,
) -> list[str]:
    return [
        str(executable),
        "--ignore-config",
        "--no-playlist",
        "--no-warnings",
        "--js-runtimes",
        f"deno:{deno}",
        "--max-filesize",
        "180M",
        "-f",
        "bestaudio/best",
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "--ffmpeg-location",
        str(ffmpeg),
        "-o",
        str(output_template),
        result.url,
    ]


def _search_ytdlp(
    query: str,
    *,
    limit: int = 3,
    cancel=None,
    progress=None,
) -> list[studio_youtube.YouTubeResult]:
    value = _clean(query, 240)
    if len(value) < 2:
        raise SpotDLError("Type at least two characters to search for a song.")
    check_cancel(cancel)
    try:
        executable, deno = studio_youtube.ensure_youtube_components(progress)
    except studio_youtube.StudioError as exc:
        raise SpotDLError("Direct yt-dlp fallback could not prepare its YouTube helpers.", str(exc)) from exc
    check_cancel(cancel)
    if progress:
        progress("Trying direct yt-dlp fallback search…")
    try:
        output = run_process(
            _search_command(executable, deno, value, limit),
            stage="yt-dlp fallback search",
            cancel=cancel,
            timeout=YTDLP_SEARCH_TIMEOUT,
        )
    except StageError as exc:
        raise SpotDLError("Direct yt-dlp fallback could not search YouTube.", exc.details or str(exc)) from exc
    results = studio_youtube.parse_search_output(output, limit=max(1, min(YTDLP_SEARCH_LIMIT, int(limit))))
    if not results:
        raise SpotDLError("Direct yt-dlp fallback found no matching YouTube results.")
    return results


def _match_score(track: ResolverTrack, result: studio_youtube.YouTubeResult) -> float:
    """Prefer the title/artist/duration that most resembles Spotify metadata."""
    wanted_title = _normal(track.title)
    wanted_artist = _normal(track.artist)
    candidate_title = _normal(result.title)
    candidate_channel = _normal(result.channel)
    combined = _normal(f"{track.artist} {track.title}")
    ratio = max(
        SequenceMatcher(None, wanted_title, candidate_title).ratio() if wanted_title else 0.0,
        SequenceMatcher(None, combined, candidate_title).ratio() if combined else 0.0,
    )
    wanted_tokens = set((wanted_title + " " + wanted_artist).split())
    candidate_tokens = set((candidate_title + " " + candidate_channel).split())
    overlap = len(wanted_tokens & candidate_tokens) / max(1, len(wanted_tokens))
    score = ratio * 0.55 + overlap * 0.30
    if wanted_artist and (wanted_artist in candidate_title or wanted_artist in candidate_channel):
        score += 0.10
    if track.duration_seconds and result.duration_seconds:
        delta = abs(float(track.duration_seconds) - float(result.duration_seconds))
        if delta <= 4:
            score += 0.15
        elif delta <= 12:
            score += 0.09
        elif delta <= 25:
            score += 0.03
        elif delta >= 90:
            score -= 0.15
    noisy = {"cover", "karaoke", "reaction", "nightcore", "slowed", "sped", "remix"}
    if noisy & set(candidate_title.split()) and not noisy & set(wanted_title.split()):
        score -= 0.18
    return score


def _pick_youtube_match(track: ResolverTrack, results: list[studio_youtube.YouTubeResult]) -> studio_youtube.YouTubeResult:
    if not results:
        raise SpotDLError("Direct yt-dlp fallback found no YouTube candidate.")
    return max(results, key=lambda result: _match_score(track, result))


def _fast_search_worker(self: SpotDLResolver, query: str, limit: int, *, cancel=None, progress=None) -> list[dict]:
    """Run the lightweight raw-metadata worker with a hard latency cap."""
    self.requests.mkdir(parents=True, exist_ok=True)
    request_id = uuid.uuid4().hex
    request = self.requests / f"{request_id}.request.json"
    response = self.requests / f"{request_id}.response.json"
    atomic_json(request, {"query": query, "limit": limit})
    try:
        run_process(
            [str(self.runtime.python), str(self._worker_path()), str(request), str(response)],
            stage="spotDL search",
            env=self.runtime.manager.environment(),
            cancel=cancel,
            timeout=SPOTDL_SEARCH_TIMEOUT,
        )
        value = read_json(response)
    except StageError as exc:
        details = exc.details
        try:
            value = read_json(response)
            details = str(value.get("error") or details)
        except (OSError, ValueError):
            pass
        raise SpotDLError("spotDL could not search Spotify metadata.", details or str(exc)) from exc
    finally:
        request.unlink(missing_ok=True)
        response.unlink(missing_ok=True)
    if not value.get("ok"):
        raise SpotDLError("spotDL could not search Spotify metadata.", _clean(value.get("error"), 4000))
    tracks = value.get("tracks")
    if not isinstance(tracks, list):
        raise SpotDLError("spotDL returned malformed search results.")
    return tracks


def _fallback_search(self: SpotDLResolver, original_search, query: str, *, limit=10, cancel=None, progress=None) -> SearchReport:
    """Use spotDL/Spotify first; only expose direct YouTube rows if that fails."""
    try:
        return original_search(self, query, limit=limit, cancel=cancel, progress=progress)
    except SpotDLError as primary:
        check_cancel(cancel)
        if progress:
            progress("spotDL search failed; switching to direct yt-dlp fallback…")
        try:
            results = _search_ytdlp(query, limit=min(limit, YTDLP_SEARCH_LIMIT), cancel=cancel, progress=progress)
        except SpotDLError as fallback:
            details = "\n\n".join(filter(None, [
                "spotDL: " + (primary.details or str(primary)),
                "yt-dlp: " + (fallback.details or str(fallback)),
            ]))
            raise SpotDLError("Neither spotDL nor direct yt-dlp could find this song.", details) from fallback
        tracks = [_youtube_track(result) for result in results]
        note = "spotDL metadata search failed, so these are direct yt-dlp/YouTube fallback results."
        if primary.details:
            note += " See Technical details for the spotDL error."
        return SearchReport(tracks[:limit], [note, primary.details or str(primary)])


def _direct_acquire(
    self: SpotDLResolver,
    track: ResolverTrack,
    *,
    fallback_reason: str = "",
    cancel=None,
    progress=None,
) -> AcquiredAudio:
    check_cancel(cancel)
    if track.provider == YTDLP_PROVIDER:
        result = _youtube_result(track)
        cache_track = track
    else:
        query = _clean(f"{track.artist} - {track.title}", 240)
        if progress:
            progress("spotDL matching/provider failed; searching YouTube with direct yt-dlp…")
        results = _search_ytdlp(query, limit=3, cancel=cancel, progress=progress)
        result = _pick_youtube_match(track, results)
        # AcquisitionStore's key excludes acquisition/suffix, so this fallback
        # is cached under the same Spotify track identity. A retry will reuse it
        # instead of failing through spotDL again.
        cache_track = replace(track, acquisition="ytdlp_direct_fallback", suffix=".mp3")

    cached = self.store.cached(cache_track)
    if cached is not None:
        metadata = {
            **cache_track.public_metadata(),
            "audio_match_source": "YouTube via direct yt-dlp fallback",
            "youtube_url": result.url,
            "youtube_video_id": result.video_id,
            "sha256": file_hash(cached),
        }
        if track.provider == "spotdl":
            metadata["spotdl_version"] = SPOTDL_VERSION
            metadata["fallback_reason"] = _clean(fallback_reason, 1000) or "spotDL matching/provider failure"
        return AcquiredAudio(cached, metadata)

    try:
        executable, deno = studio_youtube.ensure_youtube_components(progress)
    except studio_youtube.StudioError as exc:
        raise SpotDLError("Direct yt-dlp fallback could not prepare its YouTube helpers.", str(exc)) from exc
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise SpotDLError("Studio's bundled FFmpeg runtime could not be loaded.", str(exc)) from exc
    ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
    if not ffmpeg.is_file():
        raise SpotDLError("Studio's bundled FFmpeg could not be found.")

    work = self.store.root / "ytdlp-work" / uuid.uuid4().hex
    work.mkdir(parents=True, exist_ok=True)
    output_template = work / "source.%(ext)s"
    try:
        if progress:
            progress("Downloading with direct yt-dlp fallback…")
        try:
            run_process(
                _download_command(executable, deno, ffmpeg, output_template, result),
                stage="yt-dlp fallback download",
                env=self.runtime.manager.environment(ffmpeg),
                cwd=work,
                cancel=cancel,
                timeout=YTDLP_DOWNLOAD_TIMEOUT,
            )
        except StageError as exc:
            raise SpotDLError("Direct yt-dlp fallback could not download the selected audio.", exc.details or str(exc)) from exc
        expected = work / "source.mp3"
        candidates = [expected] if expected.is_file() else sorted(work.glob("*.mp3"))
        if len(candidates) != 1 or not candidates[0].is_file():
            raise SpotDLError("yt-dlp finished but Studio could not locate the fallback MP3.")
        source = candidates[0]
        size = source.stat().st_size
        if size <= 0 or size > MAX_AUDIO_BYTES:
            raise SpotDLError("The yt-dlp fallback audio file has an invalid size.")
        if not _audio_signature_matches(source, ".mp3"):
            raise SpotDLError("The yt-dlp fallback file is not a valid MP3 audio stream.")
        digest = file_hash(source)
        cached = self.store.commit(cache_track, source, ".mp3", digest, size)
        metadata = {
            **cache_track.public_metadata(),
            "audio_match_source": "YouTube via direct yt-dlp fallback",
            "youtube_url": result.url,
            "youtube_video_id": result.video_id,
            "sha256": digest,
        }
        if track.provider == "spotdl":
            metadata["spotdl_version"] = SPOTDL_VERSION
            metadata["fallback_reason"] = _clean(fallback_reason, 1000) or "spotDL matching/provider failure"
        return AcquiredAudio(cached, metadata)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _fallback_acquire(self: SpotDLResolver, original_acquire, track: ResolverTrack, *, cancel=None, progress=None) -> AcquiredAudio:
    if track.provider == YTDLP_PROVIDER:
        return _direct_acquire(self, track, cancel=cancel, progress=progress)
    try:
        return original_acquire(self, track, cancel=cancel, progress=progress)
    except SpotDLError as primary:
        check_cancel(cancel)
        reason = primary.details or str(primary)
        if progress:
            progress("spotDL failed; automatically trying direct yt-dlp fallback…")
        try:
            return _direct_acquire(
                self,
                track,
                fallback_reason=reason,
                cancel=cancel,
                progress=progress,
            )
        except SpotDLError as fallback:
            details = "\n\n".join(filter(None, [
                "spotDL: " + reason,
                "yt-dlp: " + (fallback.details or str(fallback)),
            ]))
            raise SpotDLError("Both spotDL and the direct yt-dlp fallback failed.", details) from fallback


def _configure_auto_ui(owner) -> None:
    owner.storefront.set("Auto")
    owner.search_button.configure(text="Search song")
    setup = studio_spotdl._find_setup_button(owner)
    if setup is not None:
        setup.configure(text="Downloader info")
    for child in owner.music_search_entry.master.winfo_children():
        if child.winfo_class() == "TCombobox":
            child.configure(values=("Auto",), state="readonly", width=9)
    owner.open_source_button.configure(text="Open source")
    owner.resolver_status.set(
        "Automatic download: spotDL first -> direct yt-dlp fallback if spotDL search/matching/provider fails. "
        "Local MP3/WAV/FLAC/M4A/OGG above always remains available."
    )


def install_spotdl_ytdlp_fallback() -> None:
    """Install resolver + UI fallback after the beta.4 spotDL layer is present."""
    resolver_cls = studio_spotdl.SpotDLResolver
    if getattr(resolver_cls, "_ytdlp_fallback_installed", False):
        return

    resolver_cls._run_search_worker = _fast_search_worker
    original_search = resolver_cls.search
    original_acquire = resolver_cls.acquire

    def search(self, query: str, *, limit: int = 10, cancel=None, progress=None):
        return _fallback_search(self, original_search, query, limit=limit, cancel=cancel, progress=progress)

    def acquire(self, track: ResolverTrack, *, cancel=None, progress=None):
        return _fallback_acquire(self, original_acquire, track, cancel=cancel, progress=progress)

    resolver_cls.search = search
    resolver_cls.acquire = acquire
    resolver_cls._ytdlp_fallback_installed = True

    cls = studio_band_ui.BandAudioTab
    original_init = cls.__init__

    def init(self, app):
        original_init(self, app)
        _configure_auto_ui(self)

    def show_search_results(self, report: SearchReport):
        first = None
        for index, track in enumerate(report.tracks):
            iid = f"source:{index}"
            first = first or iid
            self.search_results[iid] = track
            source = "yt-dlp fallback" if track.provider == YTDLP_PROVIDER else "spotDL"
            action = "Direct download -> Analyze" if track.provider == YTDLP_PROVIDER else "Download -> Analyze"
            self.source_tree.insert("", "end", iid=iid, text=track.title,
                                    values=(track.artist or "—", source, action))
        warning = " Fallback/setup note; see Technical details." if report.warnings else ""
        self.resolver_status.set(f"Found {len(report.tracks)} result(s). Select the correct song.{warning}")
        if report.warnings:
            self.details = json.dumps({"downloader_notes": report.warnings}, indent=2, ensure_ascii=False)
        if first is not None:
            self.source_tree.selection_set(first)
            self.source_tree.focus(first)
            self.source_selected()

    def source_selected(self):
        track = self._selected_source()
        self.acquire_button.configure(state="normal" if track and not self.busy else "disabled")
        self.open_source_button.configure(state="normal" if track and track.store_url and not self.busy else "disabled")
        if not track:
            self.open_source_button.configure(text="Open source")
            return
        if track.provider == YTDLP_PROVIDER:
            self.open_source_button.configure(text="Open YouTube")
            self.resolver_status.set("spotDL search was unavailable. This direct yt-dlp/YouTube fallback result is ready to download and analyze.")
        else:
            self.open_source_button.configure(text="Open Spotify")
            self.resolver_status.set("Ready. spotDL is the default downloader; direct yt-dlp will be tried automatically if its matching/provider fails.")

    def open_selected_source(self):
        track = self._selected_source()
        if not track or not track.store_url:
            self.resolver_status.set("This result has no source page.")
            return
        try:
            opened = bool(webbrowser.open(track.store_url, new=2, autoraise=True))
        except webbrowser.Error:
            opened = False
        label = "YouTube" if track.provider == YTDLP_PROVIDER else "Spotify"
        self.resolver_status.set(f"Opened the {label} page in your browser." if opened else "Could not open your web browser.")

    def acquire_selected(self):
        track = self._selected_source()
        if not track or self.busy:
            self.resolver_status.set("Choose a song result first.")
            return
        if track.provider == YTDLP_PROVIDER:
            explanation = "Studio will use direct yt-dlp for this YouTube fallback result."
        else:
            explanation = "Studio will try spotDL first. If its audio matching/provider fails, direct yt-dlp is tried automatically."
        allowed = messagebox.askyesno(
            "Confirm audio rights",
            explanation + "\n\nContinue only if you are allowed to download and locally analyze this audio for MIDI conversion.",
            parent=self.workspace,
        )
        if not allowed:
            return
        self.start(
            lambda: self.resolver.acquire(
                track,
                cancel=self.cancel,
                progress=lambda text: self.events.put(("progress", text)),
            ),
            "acquired",
            "audio acquisition",
        )

    def source_setup(self):
        if self.busy:
            return None
        spotdl_status = self.resolver.runtime.status()
        spotdl_state = f"spotDL {SPOTDL_VERSION}: ready" if spotdl_status.get("ready") else f"spotDL {SPOTDL_VERSION}: installs automatically on first search"
        deno_state = "spotDL Deno: ready" if spotdl_status.get("deno_ready") else "spotDL Deno: attempted automatically"
        messagebox.showinfo(
            "Automatic downloader",
            spotdl_state + "\n" + deno_state + "\n\n"
            "1. spotDL - default downloader using Spotify metadata and YouTube/YouTube Music matching.\n"
            "2. direct yt-dlp - automatic fallback if spotDL search, matching, or provider download fails.\n\n"
            "The direct fallback uses Studio's verified yt-dlp/Deno helpers and bundled FFmpeg. Local audio remains available without either downloader.",
            parent=self.workspace,
        )
        return None

    cls.__init__ = init
    cls.show_search_results = show_search_results
    cls.source_selected = source_selected
    cls.open_selected_source = open_selected_source
    cls.acquire_selected = acquire_selected
    cls.source_setup = source_setup
    cls._spotdl_ytdlp_fallback_installed = True
