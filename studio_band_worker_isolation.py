"""Keep external Python 3.11 model workers away from PyInstaller's Python 3.10 payload.

A one-file Studio build extracts CPython 3.10 extension modules (for example
_socket.pyd) beside studio_band_worker.py in PyInstaller's _MEI directory.
Launching a managed Python 3.11 interpreter with that root script puts _MEI at
sys.path[0], so 3.11 can accidentally import a 3.10 extension and fail with
"Module use of python310.dll conflicts with this version of Python".

External model workers are therefore copied into a content-addressed, source-
only bundle under Studio's runtime directory before a managed interpreter is
started. The bundle contains only Python sources, never the frozen EXE's .pyd
or DLL files.
"""
from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

from studio_band.protocol import StageError
from studio_band.runtime import PROVIDER_RUNTIME, RuntimeManager
from studio_band.storage import atomic_json, file_lock, read_json


def _source_payload() -> tuple[Path, list[Path]]:
    """Return the extracted/source worker entry and package Python files."""
    import studio_band.runtime as runtime_module

    package = Path(runtime_module.__file__).resolve().parent
    root = package.parent
    worker = root / "studio_band_worker.py"
    sources = sorted(package.glob("*.py"), key=lambda path: path.name.casefold())
    if not worker.is_file() or not sources:
        raise StageError(
            "Runtime setup",
            "Studio's isolated worker payload is missing. Re-download the Studio build and retry.",
        )
    return worker, sources


def _bundle_fingerprint(worker: Path, sources: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in [worker, *sources]:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def stage_external_worker(manager: RuntimeManager) -> Path:
    """Copy model-worker Python sources into a clean content-addressed bundle."""
    worker, sources = _source_payload()
    fingerprint = _bundle_fingerprint(worker, sources)
    parent = manager.runtime_root / "worker-source"
    target = parent / fingerprint[:24]
    entry = target / "studio_band_worker.py"
    manifest = target / "studio-worker-bundle.json"

    def ready() -> bool:
        try:
            record = read_json(manifest)
            if record.get("sha256") != fingerprint or not entry.is_file():
                return False
            package = target / "studio_band"
            return all((package / source.name).is_file() for source in sources)
        except (OSError, ValueError):
            return False

    if ready():
        return entry

    parent.mkdir(parents=True, exist_ok=True)
    with file_lock(parent / "bundle.lock"):
        if ready():
            return entry
        # A missing manifest means a previous copy was interrupted. Rebuild only
        # this content-addressed directory; never touch another running bundle.
        shutil.rmtree(target, ignore_errors=True)
        package = target / "studio_band"
        package.mkdir(parents=True, exist_ok=True)
        shutil.copy2(worker, entry)
        for source in sources:
            shutil.copy2(source, package / source.name)
        atomic_json(
            manifest,
            {
                "sha256": fingerprint,
                "entry": "studio_band_worker.py",
                "sources": [source.name for source in sources],
                "purpose": "clean source-only bridge from frozen Studio to managed Python 3.11 runtimes",
            },
        )
    return entry


def install_external_worker_isolation() -> None:
    """Patch RuntimeManager so frozen external providers use the clean bundle."""
    cls = RuntimeManager
    if getattr(cls, "_studio_external_worker_isolation", False):
        return
    original = cls.command_for

    def command_for(self: RuntimeManager, provider: str) -> list[str]:
        runtime = PROVIDER_RUNTIME.get(provider)
        if runtime and getattr(sys, "frozen", False):
            if not self.available(runtime):
                raise StageError(
                    provider,
                    "Its isolated runtime is missing. Use Advanced → Install/repair models, then Retry.",
                )
            return [str(self.python(runtime)), str(stage_external_worker(self))]
        return original(self, provider)

    cls.command_for = command_for
    cls._studio_external_worker_isolation = True
