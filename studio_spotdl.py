"""spotDL-only music search/download integration for Studio Audio -> Band.

The main Studio EXE stays dependency-light. On first use this module creates a
small isolated Python runtime, installs a pinned spotDL release, reuses Studio's
bundled FFmpeg, and feeds the downloaded audio into the existing Audio -> Band
pipeline. Manual local audio remains available at all times.
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from tkinter import messagebox
from urllib.parse import urlsplit

import studio_band_ui
from studio_band.protocol import StageError, check_cancel, run_process
from studio_band.resolver import (
    AcquisitionStore,
    AcquiredAudio,
    ResolverTrack,
    SearchReport,
    _audio_signature_matches,
)
from studio_band.runtime import RuntimeManager
from studio_band.storage import atomic_json, data_root, file_hash, file_lock, read_json

SPOTDL_VERSION = "4.5.2"
SPOTDL_REQUIREMENTS = [f"spotdl=={SPOTDL_VERSION}"]
MAX_AUDIO_BYTES = 2 * 1024**3


class SpotDLError(RuntimeError):
    def __init__(self, message: str, details: str = ""):
        super().__init__(message)
        self.details = details


def _clean(value, maximum: int = 300) -> str:
    return " ".join(str(value or "").split())[:maximum]


def _spotify_track_url(value: str) -> str:
    url = _clean(value, 1000)
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise SpotDLError("spotDL returned an invalid Spotify track URL.") from exc
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != "open.spotify.com":
        raise SpotDLError("spotDL returned an unexpected non-Spotify track URL.")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[-2] != "track" or not parts[-1]:
        raise SpotDLError("Only individual Spotify track results are supported here.")
    return f"https://open.spotify.com/track/{parts[-1]}"


def _track_from_payload(item: dict) -> ResolverTrack:
    if not isinstance(item, dict):
        raise SpotDLError("spotDL returned malformed search metadata.")
    title = _clean(item.get("name") or item.get("title"))
    if not title:
        raise SpotDLError("spotDL returned a track without a title.")
    artists = item.get("artists")
    if isinstance(artists, list):
        artist = ", ".join(_clean(value, 120) for value in artists if _clean(value, 120))
    else:
        artist = _clean(item.get("artist"), 240)
    provider_id = _clean(item.get("song_id") or item.get("track_id"), 100)
    store_url = _clean(item.get("url"), 1000)
    if not store_url and provider_id:
        store_url = f"https://open.spotify.com/track/{provider_id}"
    store_url = _spotify_track_url(store_url)
    if not provider_id:
        provider_id = store_url.rsplit("/", 1)[-1]
    duration = item.get("duration")
    try:
        duration_seconds = float(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration_seconds = None
    return ResolverTrack(
        provider="spotdl",
        provider_id=provider_id,
        title=title,
        artist=artist,
        album=_clean(item.get("album_name") or item.get("album")),
        duration_seconds=duration_seconds,
        isrc=_clean(item.get("isrc"), 32).upper(),
        release_date=_clean(item.get("date") or item.get("original_date"), 32),
        store_url=store_url,
        acquisition="spotdl_youtube_download",
        can_acquire=True,
        format_id="mp3",
        suffix=".mp3",
    )


class SpotDLRuntime:
    """Independent managed Python for spotDL so model environments never conflict."""

    def __init__(self, manager: RuntimeManager | None = None):
        self.manager = manager or RuntimeManager()
        self.name = "spotdl"
        self.root = self.manager.runtime_root / self.name
        self.record = self.root / "studio-spotdl-runtime.json"

    @property
    def python(self) -> Path:
        return self.manager.python(self.name)

    def status(self) -> dict:
        try:
            record = read_json(self.record)
        except (OSError, ValueError):
            record = {}
        return {
            "ready": self.python.is_file() and record.get("requirements") == SPOTDL_REQUIREMENTS,
            "deno_ready": bool(record.get("deno_ready")),
            "version": record.get("version"),
        }

    def available(self) -> bool:
        return bool(self.status()["ready"])

    def ensure(self, *, cancel=None, progress=None, repair: bool = False) -> dict:
        if self.available() and not repair:
            return self.status()
        with file_lock(self.manager.runtime_root / "spotdl.lock"):
            if self.available() and not repair:
                return self.status()
            try:
                uv = self.manager._uv(cancel, progress)  # reuse Studio's pinned/verified uv bootstrap
                if progress:
                    progress("Preparing spotDL runtime (first use only)…")
                if repair:
                    self.record.unlink(missing_ok=True)
                if not self.python.is_file():
                    run_process(
                        [str(uv), "venv", "--python", "3.11", "--managed-python", str(self.root)],
                        stage="spotDL setup",
                        env=self.manager.environment(),
                        cancel=cancel,
                        progress=progress,
                        timeout=1800,
                    )
                args = [str(uv), "pip", "install", "--python", str(self.python)]
                if repair:
                    args.append("--reinstall")
                run_process(
                    args + SPOTDL_REQUIREMENTS,
                    stage="spotDL setup",
                    env=self.manager.environment(),
                    cancel=cancel,
                    progress=progress,
                    timeout=1800,
                )
                frozen = run_process(
                    [str(uv), "pip", "freeze", "--python", str(self.python)],
                    stage="spotDL setup",
                    env=self.manager.environment(),
                    cancel=cancel,
                    timeout=120,
                )
                deno_ready = False
                deno_error = ""
                try:
                    if progress:
                        progress("Installing spotDL's recommended Deno helper…")
                    run_process(
                        [str(self.python), "-m", "spotdl", "--download-deno"],
                        stage="spotDL Deno setup",
                        env=self.manager.environment(),
                        cancel=cancel,
                        timeout=600,
                    )
                    deno_ready = True
                except StageError as exc:
                    # Deno is strongly recommended by spotDL but not required for
                    # every song. Keep the runtime usable and surface a warning.
                    deno_error = exc.details or str(exc)
                atomic_json(
                    self.record,
                    {
                        "requirements": SPOTDL_REQUIREMENTS,
                        "packages": frozen,
                        "python": "3.11",
                        "version": SPOTDL_VERSION,
                        "deno_ready": deno_ready,
                        "deno_error": deno_error[-4000:],
                    },
                )
            except StageError as exc:
                raise SpotDLError("spotDL could not be installed. Retry the search or check your connection.", exc.details or str(exc)) from exc
        return self.status()


class SpotDLResolver:
    def __init__(self, runtime: SpotDLRuntime | None = None, store: AcquisitionStore | None = None):
        self.runtime = runtime or SpotDLRuntime()
        self.store = store or AcquisitionStore()
        self.requests = data_root() / "spotdl-requests"
        self._search_cache: dict[str, SearchReport] = {}

    def _worker_path(self) -> Path:
        return Path(__file__).resolve().parent / "studio_band" / "spotdl_worker.py"

    def _run_search_worker(self, query: str, limit: int, *, cancel=None, progress=None) -> list[dict]:
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
                progress=progress,
                timeout=120,
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

    def search(self, query: str, *, limit: int = 10, cancel=None, progress=None) -> SearchReport:
        query = _clean(query, 240)
        if len(query) < 2:
            raise SpotDLError("Type at least two characters to search for a song.")
        check_cancel(cancel)
        if query.casefold() in self._search_cache:
            return self._search_cache[query.casefold()]
        status = self.runtime.ensure(cancel=cancel, progress=progress)
        if progress:
            progress("Searching with spotDL…")
        payloads = self._run_search_worker(query, max(1, min(20, int(limit))), cancel=cancel, progress=progress)
        tracks = []
        seen = set()
        for item in payloads:
            try:
                track = _track_from_payload(item)
            except SpotDLError:
                continue
            if track.provider_id in seen:
                continue
            seen.add(track.provider_id)
            tracks.append(track)
        if not tracks:
            raise SpotDLError("No songs matched. Try the exact title and artist, or choose a local audio file.")
        warnings = []
        if not status.get("deno_ready"):
            warnings.append("Deno helper is unavailable; spotDL may fail on a small number of YouTube matches.")
        report = SearchReport(tracks[:limit], warnings)
        self._search_cache[query.casefold()] = report
        return report

    @staticmethod
    def _download_command(track: ResolverTrack, python: Path, ffmpeg: Path, output_template: Path) -> list[str]:
        url = _spotify_track_url(track.store_url)
        return [
            str(python), "-m", "spotdl", "download",
            "--audio", "youtube-music", "youtube",
            "--lyrics",
            "--format", "mp3",
            "--ffmpeg", str(ffmpeg),
            "--threads", "1",
            "--simple-tui",
            "--log-level", "INFO",
            "--output", str(output_template),
            url,
        ]

    def acquire(self, track: ResolverTrack, *, cancel=None, progress=None) -> AcquiredAudio:
        if track.provider != "spotdl" or not track.can_acquire:
            raise SpotDLError("Choose a spotDL result first.")
        self.runtime.ensure(cancel=cancel, progress=progress)
        cached = self.store.cached(track)
        if cached is not None:
            metadata = {**track.public_metadata(), "spotdl_version": SPOTDL_VERSION, "sha256": file_hash(cached)}
            return AcquiredAudio(cached, metadata)
        check_cancel(cancel)
        # Keep Studio-only FFmpeg out of Lite's import/test environment. The
        # Studio spec explicitly bundles imageio_ffmpeg, so import it only when
        # a user actually starts a spotDL audio acquisition.
        try:
            import imageio_ffmpeg
        except ImportError as exc:
            raise SpotDLError("Studio's bundled FFmpeg runtime could not be loaded.", str(exc)) from exc
        ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
        if not ffmpeg.is_file():
            raise SpotDLError("Studio's bundled FFmpeg could not be found.")
        work = self.store.root / "spotdl-work" / uuid.uuid4().hex
        work.mkdir(parents=True, exist_ok=True)
        output_template = work / "{track-id}.{output-ext}"
        try:
            if progress:
                progress("spotDL is matching Spotify metadata to YouTube / YouTube Music…")
            command = self._download_command(track, self.runtime.python, ffmpeg, output_template)
            try:
                run_process(
                    command,
                    stage="spotDL download",
                    env=self.runtime.manager.environment(ffmpeg),
                    cwd=work,
                    cancel=cancel,
                    progress=progress,
                    timeout=1800,
                )
            except StageError as exc:
                raise SpotDLError("spotDL could not download the selected track.", exc.details or str(exc)) from exc
            expected = work / f"{track.provider_id}.mp3"
            candidates = [expected] if expected.is_file() else sorted(work.glob("*.mp3"))
            if len(candidates) != 1 or not candidates[0].is_file():
                raise SpotDLError("spotDL finished but Studio could not locate the downloaded MP3.")
            source = candidates[0]
            size = source.stat().st_size
            if size <= 0 or size > MAX_AUDIO_BYTES:
                raise SpotDLError("The downloaded audio file has an invalid size.")
            if not _audio_signature_matches(source, ".mp3"):
                raise SpotDLError("The downloaded file is not a valid MP3 audio stream.")
            digest = file_hash(source)
            cached = self.store.commit(track, source, ".mp3", digest, size)
            metadata = {
                **track.public_metadata(),
                "spotdl_version": SPOTDL_VERSION,
                "audio_match_source": "YouTube / YouTube Music via spotDL",
                "sha256": digest,
            }
            return AcquiredAudio(cached, metadata)
        finally:
            shutil.rmtree(work, ignore_errors=True)


def _find_setup_button(owner):
    frame = owner.music_search_entry.master
    for child in frame.winfo_children():
        if child.winfo_class() == "TButton" and child is not owner.search_button:
            return child
    return None


def _configure_spotdl_ui(owner) -> None:
    owner.resolver = SpotDLResolver()
    owner.storefront.set("spotDL")
    owner.search_button.configure(text="Search spotDL")
    setup = _find_setup_button(owner)
    if setup is not None:
        setup.configure(text="spotDL info")
    for child in owner.music_search_entry.master.winfo_children():
        if child.winfo_class() == "TCombobox":
            child.configure(values=("spotDL",), state="readonly", width=9)
    owner.source_tree.heading("provider", text="Source")
    owner.source_tree.heading("availability", text="Action")
    owner.source_tree.column("provider", width=90, minwidth=75, stretch=False)
    owner.source_tree.column("availability", width=170, minwidth=130, stretch=False)
    owner.acquire_button.configure(text="Download & Analyze")
    owner.open_source_button.configure(text="Open Spotify")
    owner.resolver_status.set(
        "spotDL only: Spotify metadata search -> YouTube / YouTube Music audio match. "
        "Local MP3/WAV/FLAC/M4A/OGG above always remains available."
    )


def install_spotdl_band_audio() -> None:
    cls = studio_band_ui.BandAudioTab
    if getattr(cls, "_spotdl_only_installed", False):
        return

    original_init = cls.__init__
    original_open = cls.open_selected_source

    def init(self, app):
        original_init(self, app)
        _configure_spotdl_ui(self)

    def search_music(self):
        if self.busy:
            return
        query = self.music_query.get().strip()
        self.source_tree.delete(*self.source_tree.get_children())
        self.search_results.clear()
        self.acquire_button.configure(state="disabled")
        self.open_source_button.configure(state="disabled")
        self.resolver_status.set("Preparing spotDL and searching Spotify metadata…")
        self.start(
            lambda: self.resolver.search(
                query,
                cancel=self.cancel,
                progress=lambda text: self.events.put(("progress", text)),
            ),
            "search_done",
            "music search",
        )

    def show_search_results(self, report: SearchReport):
        first = None
        for index, track in enumerate(report.tracks):
            iid = f"source:{index}"
            first = first or iid
            self.search_results[iid] = track
            self.source_tree.insert(
                "",
                "end",
                iid=iid,
                text=track.title,
                values=(track.artist or "—", "spotDL", "Download -> Analyze"),
            )
        warning = " Deno warning; see Technical details." if report.warnings else ""
        self.resolver_status.set(f"Found {len(report.tracks)} spotDL result(s). Select the correct song.{warning}")
        if report.warnings:
            self.details = json.dumps({"spotdl_notes": report.warnings}, indent=2, ensure_ascii=False)
        if first is not None:
            self.source_tree.selection_set(first)
            self.source_tree.focus(first)
            self.source_selected()

    def source_selected(self):
        track = self._selected_source()
        self.acquire_button.configure(state="normal" if track and not self.busy else "disabled")
        self.open_source_button.configure(state="normal" if track and track.store_url and not self.busy else "disabled")
        if track:
            self.resolver_status.set(
                "Ready. spotDL will use this Spotify track's metadata to find the closest YouTube / YouTube Music audio match."
            )

    def open_selected_source(self):
        original_open(self)
        if self._selected_source() is not None:
            self.resolver_status.set("Opened the Spotify track page in your browser.")

    def acquire_selected(self):
        track = self._selected_source()
        if not track or self.busy:
            self.resolver_status.set("Choose a spotDL song result first.")
            return
        allowed = messagebox.askyesno(
            "Confirm audio rights",
            "spotDL will download the matched audio from YouTube / YouTube Music.\n\n"
            "Continue only if you are allowed to download and locally analyze this audio for MIDI conversion.",
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
        status = self.resolver.runtime.status()
        state = f"Installed spotDL {SPOTDL_VERSION}." if status.get("ready") else (
            f"spotDL {SPOTDL_VERSION} is not installed yet; Studio installs it automatically on the first search."
        )
        deno = " Deno helper is ready." if status.get("deno_ready") else (
            " Deno will also be attempted automatically because spotDL recommends it for better YouTube compatibility."
        )
        messagebox.showinfo(
            "spotDL source",
            state + deno + "\n\nSearch uses Spotify metadata. Audio is matched and downloaded by spotDL from YouTube / YouTube Music. "
            "Studio reuses its bundled FFmpeg, and manual local audio remains available without spotDL.",
            parent=self.workspace,
        )
        return None

    cls.__init__ = init
    cls.search_music = search_music
    cls.show_search_results = show_search_results
    cls.source_selected = source_selected
    cls.open_selected_source = open_selected_source
    cls.acquire_selected = acquire_selected
    cls.source_setup = source_setup
    cls._spotdl_only_installed = True
