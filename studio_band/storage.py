"""Atomic, content-addressed stages and isolated, expiring audio jobs."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import PIPELINE_VERSION

MAX_JSON_BYTES = 128 * 1024 * 1024


def read_json(path: Path) -> Any:
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("JSON file is too large")
    return json.loads(path.read_text(encoding="utf-8"),
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f"Invalid number: {x}")))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                                        separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_key(*values: Any) -> str:
    data = json.dumps([PIPELINE_VERSION, *values], sort_keys=True, allow_nan=False, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def data_root() -> Path:
    override = os.environ.get("BPSR_STUDIO_BAND_HOME")
    if override:
        return Path(override).expanduser().resolve()
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    return base / "BPSR-MIDI-Studio" / "band-accurate"


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """OS-held lock: automatically released after a crash, across Studio processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0)
        if not handle.read(1):
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another Studio process is using this job/runtime. Try again when it finishes.") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


class JobStore:
    def __init__(self, root: Path | None = None):
        self.root = root or data_root() / "cache"
        self.root.mkdir(parents=True, exist_ok=True)

    def job(self, source: Path, digest: str) -> Path:
        # Name is derived only from a locally calculated digest, never the song title.
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid source hash")
        job = self.root / ("job_" + digest)
        job.mkdir(exist_ok=True)
        for folder in ("stems", "transcription", "analysis", "output", "requests"):
            (job / folder).mkdir(exist_ok=True)
        os.utime(job, None)
        return job

    def copy_source(self, job: Path, source: Path, digest: str) -> Path:
        target = job / ("original" + source.suffix.lower())
        if not target.exists() or file_hash(target) != digest:
            temporary = target.with_suffix(target.suffix + ".tmp")
            shutil.copyfile(source, temporary)
            if file_hash(temporary) != digest:
                temporary.unlink(missing_ok=True)
                raise ValueError("The source audio changed while it was being copied. Retry the conversion.")
            os.replace(temporary, target)
        return target

    def cached(self, folder: Path, key: str) -> dict[str, Any] | None:
        path = folder / key / "complete.json"
        try:
            record = read_json(path)
            if record.get("key") != key:
                return None
            for relative, digest in record.get("files", {}).items():
                target = (path.parent / relative).resolve()
                if not target.is_relative_to(path.parent.resolve()) or file_hash(target) != digest:
                    return None
            return record["result"]
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def commit_stage(self, folder: Path, key: str, result: dict[str, Any], files: list[Path] = ()) -> None:
        base = folder / key
        digests = {str(p.relative_to(base)): file_hash(p) for p in files}
        atomic_json(base / "complete.json", {"key": key, "files": digests, "result": result})

    def cleanup(self, days: int = 14, max_bytes: int = 20 * 1024**3) -> int:
        jobs = sorted((p for p in self.root.glob("job_*") if p.is_dir() and not p.is_symlink()),
                      key=lambda p: p.stat().st_mtime)
        sizes = {p: sum(f.stat().st_size for f in p.rglob("*") if f.is_file() and not f.is_symlink()) for p in jobs}
        total, removed = sum(sizes.values()), 0
        for job in jobs:
            if time.time() - job.stat().st_mtime < days * 86400 and total <= max_bytes:
                continue
            try:
                with file_lock(self.root / (job.name + ".lock")):
                    shutil.rmtree(job)
                total -= sizes[job]
                removed += 1
            except (OSError, RuntimeError):
                continue
        return removed
