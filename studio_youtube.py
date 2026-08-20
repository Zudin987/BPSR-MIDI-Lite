from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

YTDLP_EXE_URL = (
    "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp.exe"
)
YTDLP_SUMS_URL = (
    "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/SHA2-256SUMS"
)
DENO_ZIP_NAME = "deno-x86_64-pc-windows-msvc.zip"
DENO_ZIP_URL = f"https://github.com/denoland/deno/releases/latest/download/{DENO_ZIP_NAME}"
DENO_SUM_URL = DENO_ZIP_URL + ".sha256sum"
USER_AGENT = "BPSR-MIDI-Studio/0.1"
TOP_RESULTS = 3
MAX_VIDEO_SECONDS = 15 * 60
MAX_COMPONENT_BYTES = 96 * 1024 * 1024
COMPONENT_REFRESH_SECONDS = 3 * 24 * 60 * 60
CACHE_MAX_AGE_SECONDS = 2 * 24 * 60 * 60
CACHE_MAX_BYTES = 512 * 1024 * 1024
TRANSCRIPTION_CACHE_VERSION = "bp040-v1"

_PROGRESS = Callable[[str], None]
_BASIC_PITCH_MODEL = None


class StudioError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class YouTubeResult:
    video_id: str
    title: str
    channel: str
    duration_seconds: int | None

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


def _local_app_data() -> Path:
    raw = os.environ.get("LOCALAPPDATA")
    if raw:
        return Path(raw)
    return Path.home() / "AppData" / "Local"


def component_directory() -> Path:
    path = _local_app_data() / "BPSR MIDI Studio" / "components"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_directory() -> Path:
    path = Path(tempfile.gettempdir()) / "BPSR-MIDI-Studio" / "YouTube"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _request_bytes(url: str, *, max_bytes: int, timeout: float = 30.0) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Encoding": "identity",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS GitHub URL
            length = response.headers.get("Content-Length")
            if length:
                try:
                    if int(length) > max_bytes:
                        raise StudioError("A required Studio component was unexpectedly large.")
                except ValueError:
                    pass
            data = response.read(max_bytes + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise StudioError("Could not download the YouTube helper from GitHub.") from exc
    if len(data) > max_bytes:
        raise StudioError("A required Studio component was unexpectedly large.")
    return data


def _expected_ytdlp_sha256() -> str:
    sums = _request_bytes(YTDLP_SUMS_URL, max_bytes=2 * 1024 * 1024).decode(
        "utf-8", errors="replace"
    )
    match = re.search(r"(?im)^([0-9a-f]{64})\s+\*?yt-dlp\.exe\s*$", sums)
    if not match:
        raise StudioError("Could not verify the yt-dlp download.")
    return match.group(1).lower()


def _install_latest_ytdlp(target: Path) -> None:
    expected = _expected_ytdlp_sha256()
    data = _request_bytes(YTDLP_EXE_URL, max_bytes=MAX_COMPONENT_BYTES)
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise StudioError("The yt-dlp download failed its SHA-256 verification.")
    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)


def _expected_deno_sha256() -> str:
    checksum = _request_bytes(DENO_SUM_URL, max_bytes=256 * 1024).decode(
        "utf-8", errors="replace"
    )
    match = re.search(r"(?im)^([0-9a-f]{64})\s+\*?deno-x86_64-pc-windows-msvc\.zip\s*$", checksum)
    if not match:
        raise StudioError("Could not verify the Deno runtime download.")
    return match.group(1).lower()


def _install_latest_deno(target: Path) -> None:
    expected = _expected_deno_sha256()
    data = _request_bytes(DENO_ZIP_URL, max_bytes=MAX_COMPONENT_BYTES)
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise StudioError("The Deno runtime download failed its SHA-256 verification.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            member = archive.getinfo("deno.exe")
            if member.file_size > 160 * 1024 * 1024:
                raise StudioError("The Deno runtime archive was unexpectedly large.")
            extracted = archive.read(member)
    except (KeyError, zipfile.BadZipFile) as exc:
        raise StudioError("The Deno runtime archive was invalid.") from exc
    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(extracted)
    os.replace(tmp, target)


def ensure_ytdlp(progress: _PROGRESS | None = None) -> Path:
    target = component_directory() / "yt-dlp.exe"
    stale = True
    if target.exists():
        try:
            stale = (time.time() - target.stat().st_mtime) > COMPONENT_REFRESH_SECONDS
        except OSError:
            stale = True
    if target.exists() and not stale:
        return target

    if progress is not None:
        progress(
            "Preparing YouTube support…"
            if not target.exists()
            else "Refreshing YouTube support…"
        )
    try:
        _install_latest_ytdlp(target)
    except StudioError:
        if target.exists():
            return target
        raise
    return target


def ensure_deno(progress: _PROGRESS | None = None) -> Path:
    """Keep the JS runtime yt-dlp now requires for full YouTube support."""
    target = component_directory() / "deno.exe"
    stale = True
    if target.exists():
        try:
            stale = (time.time() - target.stat().st_mtime) > 14 * 24 * 60 * 60
        except OSError:
            stale = True
    if target.exists() and not stale:
        return target

    if progress is not None:
        progress(
            "Preparing YouTube JavaScript support…"
            if not target.exists()
            else "Refreshing YouTube JavaScript support…"
        )
    try:
        _install_latest_deno(target)
    except StudioError:
        if target.exists():
            return target
        raise
    return target


def ensure_youtube_components(progress: _PROGRESS | None = None) -> tuple[Path, Path]:
    return ensure_ytdlp(progress), ensure_deno(progress)


def _creation_flags() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0


def _run_ytdlp(
    executable: Path,
    args: list[str],
    *,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [str(executable), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=_creation_flags(),
        )
    except subprocess.TimeoutExpired as exc:
        raise StudioError("YouTube took too long to respond. Try again.") from exc
    except OSError as exc:
        raise StudioError("Could not start the YouTube helper.") from exc


def _friendly_ytdlp_error(stderr: str) -> StudioError:
    lower = stderr.casefold()
    if (
        "sign in" in lower
        or "cookies" in lower
        or "confirm you" in lower and "bot" in lower
        or "login" in lower
    ):
        return StudioError(
            "YouTube blocked anonymous access to this upload. "
            "Try another result; Studio does not use account sign-in or cookies."
        )
    if "not available in your country" in lower or "geo" in lower and "restricted" in lower:
        return StudioError("This YouTube upload is not available in your region.")
    if "private video" in lower or "video unavailable" in lower:
        return StudioError("This YouTube upload is unavailable. Try another result.")
    return StudioError("YouTube could not provide this item right now. Try again or choose another result.")


def parse_search_output(stdout: str, *, limit: int = TOP_RESULTS) -> list[YouTubeResult]:
    results: list[YouTubeResult] = []
    seen: set[str] = set()
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        video_id = str(item.get("id") or "").strip()
        title = " ".join(str(item.get("title") or "").split())
        if not video_id or not title or video_id in seen:
            continue
        duration_raw = item.get("duration")
        try:
            duration = int(round(float(duration_raw))) if duration_raw is not None else None
        except (TypeError, ValueError):
            duration = None
        channel = " ".join(
            str(item.get("channel") or item.get("uploader") or "").split()
        )
        seen.add(video_id)
        results.append(
            YouTubeResult(
                video_id=video_id[:32],
                title=title[:180],
                channel=channel[:100],
                duration_seconds=duration,
            )
        )
        if len(results) >= max(1, int(limit)):
            break
    return results


def search_youtube(
    query: str,
    *,
    limit: int = TOP_RESULTS,
    progress: _PROGRESS | None = None,
) -> list[YouTubeResult]:
    value = " ".join(query.split()).strip()
    if len(value) < 2:
        raise StudioError("Type at least 2 characters to search YouTube.")
    executable, deno = ensure_youtube_components(progress)
    count = max(1, min(TOP_RESULTS, int(limit)))
    if progress is not None:
        progress("Searching YouTube…")
    process = _run_ytdlp(
        executable,
        [
            "--ignore-config",
            "--no-warnings",
            "--js-runtimes",
            f"deno:{deno}",
            "--flat-playlist",
            "--dump-json",
            "--playlist-end",
            str(count),
            f"ytsearch{count}:{value}",
        ],
        timeout=60.0,
    )
    if process.returncode != 0:
        raise _friendly_ytdlp_error(process.stderr)
    results = parse_search_output(process.stdout, limit=count)
    if not results:
        raise StudioError("No YouTube results matched that search.")
    return results


def duration_label(seconds: int | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes}:{sec:02d}"


def _ffmpeg_executable() -> Path:
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
    except ImportError as exc:
        raise StudioError("The Studio audio component is missing. Reinstall BPSR MIDI Studio.") from exc
    path = Path(get_ffmpeg_exe())
    if not path.exists():
        raise StudioError("The Studio FFmpeg component is missing. Reinstall BPSR MIDI Studio.")
    return path


def _cache_midi_path(video_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", video_id)[:40]
    return cache_directory() / f"{safe_id}_{TRANSCRIPTION_CACHE_VERSION}.mid"


def _work_directory(video_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", video_id)[:40]
    path = cache_directory() / f"work_{safe_id}_{int(time.time())}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _download_audio(
    result: YouTubeResult,
    work_dir: Path,
    *,
    progress: _PROGRESS | None = None,
) -> Path:
    if result.duration_seconds is not None and result.duration_seconds > MAX_VIDEO_SECONDS:
        raise StudioError("This video is over 15 minutes. Choose a normal song-length upload.")

    executable, deno = ensure_youtube_components(progress)
    ffmpeg = _ffmpeg_executable()
    if progress is not None:
        progress("Getting audio from YouTube…")
    output_template = str(work_dir / "source.%(ext)s")
    process = _run_ytdlp(
        executable,
        [
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
            "wav",
            "--ffmpeg-location",
            str(ffmpeg),
            "-o",
            output_template,
            result.url,
        ],
        timeout=240.0,
    )
    if process.returncode != 0:
        raise _friendly_ytdlp_error(process.stderr)

    wav = work_dir / "source.wav"
    if not wav.exists():
        candidates = list(work_dir.glob("source.*"))
        if not candidates:
            raise StudioError("YouTube audio finished but the temporary audio file was not created.")
        wav = candidates[0]
    return wav


def _basic_pitch_model():
    global _BASIC_PITCH_MODEL
    if _BASIC_PITCH_MODEL is not None:
        return _BASIC_PITCH_MODEL
    try:
        from basic_pitch import ICASSP_2022_MODEL_PATH
        from basic_pitch.inference import Model
    except ImportError as exc:
        raise StudioError("The Studio transcription model is missing. Reinstall BPSR MIDI Studio.") from exc
    try:
        _BASIC_PITCH_MODEL = Model(ICASSP_2022_MODEL_PATH)
    except Exception as exc:
        raise StudioError("Could not load the audio-to-MIDI model.") from exc
    return _BASIC_PITCH_MODEL


def _transcribe_audio(
    audio_path: Path,
    midi_path: Path,
    *,
    progress: _PROGRESS | None = None,
) -> None:
    if progress is not None:
        progress("Listening for notes and creating MIDI…")
    try:
        from basic_pitch.inference import predict
    except ImportError as exc:
        raise StudioError("The Studio transcription component is missing.") from exc

    try:
        _model_output, midi_data, note_events = predict(
            audio_path,
            _basic_pitch_model(),
            onset_threshold=0.58,
            frame_threshold=0.35,
            minimum_note_length=90.0,
            minimum_frequency=32.70,
            maximum_frequency=2093.00,
            multiple_pitch_bends=False,
            melodia_trick=True,
        )
    except Exception as exc:
        raise StudioError("Audio-to-MIDI conversion failed for this song.") from exc
    if not note_events:
        raise StudioError("No clear musical notes were detected in this audio.")
    try:
        midi_data.write(str(midi_path))
    except Exception as exc:
        raise StudioError("The converted MIDI could not be saved to temporary cache.") from exc


def convert_result_to_midi(
    result: YouTubeResult,
    *,
    progress: _PROGRESS | None = None,
) -> Path:
    cleanup_cache()
    target = _cache_midi_path(result.video_id)
    if target.exists() and target.stat().st_size > 0:
        if progress is not None:
            progress("Using the cached MIDI conversion…")
        return target

    work_dir = _work_directory(result.video_id)
    try:
        audio_path = _download_audio(result, work_dir, progress=progress)
        _transcribe_audio(audio_path, target, progress=progress)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    if progress is not None:
        progress("MIDI created. Running BPSR Song Check…")
    return target


_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_song_filename(title: str, video_id: str) -> str:
    cleaned = _INVALID_FILENAME.sub("_", " ".join(title.split())).strip(" ._")
    if not cleaned:
        cleaned = f"YouTube {video_id}"
    cleaned = cleaned[:120].rstrip(" .")
    return f"{cleaned}.mid"


def save_midi_to_local(midi_path: Path, title: str, video_id: str, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    base = Path(safe_song_filename(title, video_id))
    target = folder / base
    counter = 2
    while target.exists():
        target = folder / f"{base.stem} ({counter}){base.suffix}"
        counter += 1
    shutil.copy2(midi_path, target)
    return target


def cleanup_cache() -> None:
    root = cache_directory()
    now = time.time()
    files: list[Path] = []
    for path in root.iterdir():
        try:
            if path.is_dir():
                if (now - path.stat().st_mtime) > 6 * 60 * 60:
                    shutil.rmtree(path, ignore_errors=True)
                continue
            if (now - path.stat().st_mtime) > CACHE_MAX_AGE_SECONDS:
                path.unlink(missing_ok=True)
                continue
            files.append(path)
        except OSError:
            continue

    def _stat(item: Path) -> tuple[float, int]:
        try:
            stat = item.stat()
            return stat.st_mtime, stat.st_size
        except OSError:
            return 0.0, 0

    total = sum(_stat(path)[1] for path in files)
    if total <= CACHE_MAX_BYTES:
        return
    for path in sorted(files, key=lambda item: _stat(item)[0]):
        try:
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            total -= size
        except OSError:
            continue
        if total <= CACHE_MAX_BYTES:
            break
