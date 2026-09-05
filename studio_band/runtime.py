"""Studio model manager. Heavy dependencies live in independent managed Pythons."""
from __future__ import annotations

import ctypes
import io
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

from . import PIPELINE_VERSION
from .progress import emit_progress
from .protocol import Cancelled, RuntimeSetupError, StageError, check_cancel, run_process
from .storage import atomic_json, atomic_text, cache_key, data_root, file_hash, file_lock, read_json

UV_VERSION = "0.8.22"
UV_SHA256 = "5049375aa2a5162f132b2c1cb992e25d42d47d934cab8c174dbe6f60973dcc12"
HQ_MODEL = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"

# Do not add these to either application's requirements. Each row is a separate
# venv; Demucs's older torch and Studio's numpy<2 never constrain other engines.
RUNTIMES = {
    "separator": ["demucs==4.0.1", "torch==2.0.1", "torchaudio==2.0.2", "numpy==1.26.4", "soundfile==0.13.1", "setuptools<81"],
    "piano": ["transkun==2.0.1", "torch==2.5.1", "torchaudio==2.5.1", "numpy==1.26.4", "soundfile==0.13.1", "setuptools<81"],
    "beat": ["beat-this==1.1.0", "torch==2.5.1", "torchaudio==2.5.1", "numpy==1.26.4", "soundfile==0.13.1"],
    # MR-MT3's packaged T5 adapter uses the plural past_key_values/cache API.
    "mt3": ["mt3-infer==0.2.0", "torch==2.5.1", "torchaudio==2.5.1", "torchvision==0.20.1", "transformers==4.57.1", "numpy==1.26.4"],
    "hq": ["audio-separator[cpu]==0.30.2", "torch==2.5.1", "torchaudio==2.5.1", "numpy==1.26.4", "soundfile==0.13.1"],
}

# Transkun 2.0.1 declares ``ncls`` without a version. ncls 0.0.70 has no
# CPython 3.11 Windows wheel, so an unconstrained resolver attempts a local C
# build and requires MSVC. 0.0.68 publishes a CPython 3.11 win_amd64 wheel.
# Keep this as a resolver constraint (rather than editing Transkun) and require
# a wheel so a future index change can never silently reintroduce compilation.
WINDOWS_RUNTIME_CONSTRAINTS = {"piano": ("ncls==0.0.68",)}
WINDOWS_BINARY_ONLY = {"piano": ("ncls",)}
RUNTIME_LABELS = {
    "separator": "six-stem separator",
    "piano": "Transkun",
    "beat": "beat detector",
    "mt3": "musical cross-check",
    "hq": "HQ separator",
}
RUNTIME_VALIDATION = {
    "separator": "import demucs, torch, torchaudio",
    "piano": (
        "import importlib.metadata as metadata\n"
        "import ncls, transkun\n"
        "from transkun.Data import writeMidi\n"
        "assert metadata.version('transkun') == '2.0.1'\n"
        "if __import__('os').name == 'nt': assert metadata.version('ncls') == '0.0.68'"
    ),
    "beat": "import beat_this, torch, torchaudio",
    "mt3": "import mt3_infer, torch, torchaudio, transformers",
    "hq": "import audio_separator, torch, torchaudio",
}
PROVIDER_RUNTIME = {"demucs": "separator", "roformer": "hq", "transkun": "piano",
                    "beat_this": "beat", "mr_mt3": "mt3", "adtof": "drums"}
PROVIDER_MODEL = {"demucs": "htdemucs_6s", "roformer": HQ_MODEL, "transkun": "2.0",
                  "beat_this": "final0", "mr_mt3": "mr_mt3", "basic_pitch": "ICASSP_2022",
                  "drums_dsp": "spectral-onsets-1", "beat_dsp": "onset-autocorrelation-1"}


@dataclass
class Hardware:
    cuda: bool = False
    vram_gb: float = 0.0
    ram_gb: float = 0.0
    gpu: str = ""


def detect_hardware() -> Hardware:
    result = Hardware()
    try:
        if os.name == "nt":
            class Memory(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                    (x, ctypes.c_ulonglong) for x in ("total", "avail", "page", "page_avail", "virt", "virt_avail", "extended")]
            memory = Memory()
            memory.length = ctypes.sizeof(Memory)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
                result.ram_gb = memory.total / 1024**3
        else:
            result.ram_gb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3
    except (OSError, ValueError, AttributeError):
        pass
    try:
        output = subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                                         timeout=4, text=True, stderr=subprocess.DEVNULL,
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        name, memory = output.splitlines()[0].rsplit(",", 1)
        result.cuda, result.vram_gb, result.gpu = True, float(memory) / 1024, name.strip()
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        pass
    return result


def choose_separator(quality: str, hardware: Hardware, hq_available: bool) -> str:
    if quality not in {"auto", "standard", "hq"}:
        raise ValueError("Unknown separation quality")
    if quality == "hq":
        return "roformer"
    if quality == "auto" and hq_available and hardware.cuda and hardware.vram_gb >= 6 and hardware.ram_gb >= 16:
        return "roformer"
    return "demucs"


class RuntimeManager:
    def __init__(self, root: Path | None = None):
        self.root = root or data_root()
        self.runtime_root = self.root / "runtime"
        self.models = self.root / "models"

    def python(self, name: str) -> Path:
        return self.runtime_root / name / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    @staticmethod
    def install_policy(name: str, *, platform_name: str | None = None) -> dict[str, list[str]]:
        windows = (os.name if platform_name is None else platform_name) == "nt"
        return {
            "constraints": list(WINDOWS_RUNTIME_CONSTRAINTS.get(name, ())) if windows else [],
            "binary_only": list(WINDOWS_BINARY_ONLY.get(name, ())) if windows else [],
        }

    def _constraint_file(self, name: str, constraints: list[str]) -> Path | None:
        if not constraints:
            return None
        path = self.runtime_root / "constraints" / f"{name}-windows-cpython311.txt"
        content = "".join(requirement + "\n" for requirement in constraints)
        try:
            if path.read_text(encoding="utf-8") == content:
                return path
        except OSError:
            pass
        atomic_text(path, content)
        return path

    def available(self, name: str) -> bool:
        if name == "drums":
            return self.python(name).is_file()  # user-managed ADTOF installation only
        try:
            record = read_json(self.runtime_root / name / "studio-runtime.json")
            policy = self.install_policy(name)
            validated = record.get("validated") is True or (
                "validated" not in record and not policy["constraints"] and not policy["binary_only"]
            )
            return (
                self.python(name).is_file()
                and record["requirements"] == RUNTIMES[name]
                and record.get("constraints", []) == policy["constraints"]
                and record.get("binary_only", []) == policy["binary_only"]
                and validated
            )
        except (OSError, ValueError, KeyError):
            return False

    def environment(self, ffmpeg: Path | None = None) -> dict:
        env = os.environ.copy()
        # Avoid inheriting frozen app / caller Python state into other frameworks.
        for key in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "PYTEST_CURRENT_TEST"):
            env.pop(key, None)
        # Resolver credentials belong only to the desktop process.  Never pass
        # catalogue or entitlement secrets to AI/model worker subprocesses.
        for key in list(env):
            if (key == "BPSR_APPLE_MUSIC_TOKEN" or
                    key.startswith(("BPSR_MASSIVEMUSIC_", "BPSR_BANDCAMP_"))):
                env.pop(key, None)
        env.update({"PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1", "PYTHONNOUSERSITE": "1",
                    "TORCH_HOME": str(self.models / "torch"),
                    "HF_HOME": str(self.models / "huggingface"),
                    "MT3_CHECKPOINT_DIR": str(self.models / "mt3"),
                    "UV_PYTHON_INSTALL_DIR": str(self.runtime_root / "python"),
                    "UV_CACHE_DIR": str(self.runtime_root / "uv-cache"),
                    "UV_NO_PROGRESS": "1"})
        if ffmpeg:
            directory = ffmpeg.parent
            if ffmpeg.is_file():
                # imageio's executable has a versioned name. Third-party audio
                # engines invoke literal `ffmpeg`; expose our verified bundled
                # binary under that name, without requiring a system install.
                directory = self.runtime_root / "tools" / "ffmpeg" / file_hash(ffmpeg)
                alias = directory / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
                directory.mkdir(parents=True, exist_ok=True)
                with file_lock(directory / "copy.lock"):
                    if not alias.exists() or file_hash(alias) != directory.name:
                        temporary = alias.with_suffix(".tmp")
                        shutil.copy2(ffmpeg, temporary)
                        os.replace(temporary, alias)
            env["PATH"] = str(directory) + os.pathsep + env.get("PATH", "")
            env["IMAGEIO_FFMPEG_EXE"] = str(ffmpeg)
        return env

    def _uv(self, cancel=None, progress=None) -> Path:
        # Source checkouts can use a preinstalled uv. Frozen Windows needs no
        # system Python, pip, shell installer, or administrator installation.
        if not getattr(sys, "frozen", False) and shutil.which("uv"):
            return Path(shutil.which("uv"))
        target = self.runtime_root / "tools" / "uv.exe"
        if target.exists():
            try:
                record = read_json(target.with_suffix(".json"))
                if record.get("version") == UV_VERSION and record.get("sha256") == file_hash(target):
                    return target
            except (OSError, ValueError):
                pass  # interrupted bootstrap: download and verify again
        if os.name != "nt":
            raise StageError("Runtime setup", "Install uv for this source checkout and retry.")
        check_cancel(cancel)
        emit_progress(progress, "Downloading the isolated runtime manager…", activity="download",
                      stage_fraction=0.0, indeterminate=True)
        url = f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/uv-x86_64-pc-windows-msvc.zip"
        target.parent.mkdir(parents=True, exist_ok=True)
        archive = target.with_suffix(".zip.tmp")
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "BPSR-MIDI-Studio"}), timeout=30) as remote, archive.open("wb") as out:
                size = 0
                try:
                    total = int(remote.headers.get("Content-Length", ""))
                except (TypeError, ValueError):
                    total = 0
                while chunk := remote.read(1024 * 1024):
                    check_cancel(cancel)
                    size += len(chunk)
                    if size > 80 * 1024**2:
                        raise ValueError("Runtime download is unexpectedly large")
                    out.write(chunk)
                    emit_progress(progress, "Downloading the isolated runtime manager…", activity="download",
                                  stage_fraction=(0.10 * min(1.0, size / total)) if total else 0.0,
                                  indeterminate=not bool(total), bytes_done=size, bytes_total=total or None)
            if file_hash(archive) != UV_SHA256:
                raise ValueError("Runtime download checksum does not match the pinned release")
            with zipfile.ZipFile(archive) as bundle:
                entry = next(x for x in bundle.infolist() if Path(x.filename).name == "uv.exe")
                target.write_bytes(bundle.read(entry))
            atomic_json(target.with_suffix(".json"), {"version": UV_VERSION, "sha256": file_hash(target)})
            emit_progress(progress, "Isolated runtime manager ready", activity="install",
                          stage_fraction=0.10, indeterminate=False)
        finally:
            archive.unlink(missing_ok=True)
        return target

    def install(self, name: str, *, device: str = "cpu", cancel=None, progress=None, repair: bool = False) -> None:
        if device == "auto":
            device = "cuda" if detect_hardware().cuda else "cpu"
        if name not in RUNTIMES:
            raise StageError("Runtime setup", "This optional backend must be installed separately; see the model license notes.")
        if self.available(name) and not repair:
            return
        with file_lock(self.runtime_root / (name + ".lock")):
            if self.available(name) and not repair:
                return
            target = self.runtime_root / name
            if repair:
                (target / "studio-runtime.json").unlink(missing_ok=True)
            environment = self.environment()
            label = RUNTIME_LABELS.get(name, name)
            policy = self.install_policy(name)
            try:
                emit_progress(progress, f"Preparing {label} runtime (first use only)…", activity="install",
                              stage_fraction=0.0, indeterminate=True)
                uv = self._uv(cancel, progress)
                constraint_file = self._constraint_file(name, policy["constraints"])
                if not self.python(name).exists():
                    emit_progress(progress, "Creating isolated Python 3.11 environment…", activity="install",
                                  stage_fraction=0.12, indeterminate=True)
                    run_process([str(uv), "venv", "--python", "3.11", "--managed-python", str(target)],
                                stage="Runtime setup", env=environment, cancel=cancel, progress=progress, timeout=1800)
                emit_progress(progress, "Python 3.11 environment ready", activity="install",
                              stage_fraction=0.20, indeterminate=False)
                # Windows PyPI torch wheels support CUDA. The explicit CPU index
                # avoids downloading multi-GB CUDA dependencies on CPU-only PCs.
                args = [str(uv), "pip", "install", "--python", str(self.python(name))]
                if repair:
                    args.append("--reinstall")
                requirements = RUNTIMES[name]
                if device == "cpu":
                    torch_requirements = [x for x in requirements if x.split("==")[0] in {"torch", "torchaudio", "torchvision"}]
                    if torch_requirements:
                        emit_progress(progress, f"Installing {label} compute components…", activity="install",
                                      stage_fraction=0.25, indeterminate=True)
                        run_process(args + torch_requirements + ["--index-url", "https://download.pytorch.org/whl/cpu"],
                                    stage="Runtime setup", env=environment, cancel=cancel, progress=progress, timeout=3600)
                emit_progress(progress, f"Installing {label} transcription components…", activity="install",
                              stage_fraction=0.50, indeterminate=True)
                policy_args: list[str] = []
                if constraint_file is not None:
                    policy_args += ["--constraints", str(constraint_file)]
                for package in policy["binary_only"]:
                    policy_args += ["--only-binary", package]
                run_process(args + requirements + policy_args + ["--strict"], stage="Runtime setup", env=environment,
                            cancel=cancel, progress=progress, timeout=3600)
                emit_progress(progress, f"Verifying {label} imports and versions…", activity="install",
                              stage_fraction=0.90, indeterminate=True)
                validation = RUNTIME_VALIDATION[name]
                run_process([str(self.python(name)), "-c", validation], stage="Runtime setup", env=environment,
                            cancel=cancel, progress=progress, timeout=300)
                frozen = run_process([str(uv), "pip", "freeze", "--python", str(self.python(name))],
                                     stage="Runtime setup", env=environment, cancel=cancel, timeout=60)
                atomic_json(target / "studio-runtime.json", {"requirements": requirements, "packages": frozen,
                                                             "python": "3.11", "device_install": device,
                                                             "constraints": policy["constraints"],
                                                             "binary_only": policy["binary_only"], "validated": True})
                emit_progress(progress, f"{label.title()} runtime ready", activity="install",
                              stage_fraction=1.0, indeterminate=False)
            except StageError as exc:
                (target / "studio-runtime.json").unlink(missing_ok=True)
                details = exc.details or str(exc)
                if name == "piano" and policy["constraints"]:
                    message = "Could not prepare Transkun runtime. Windows dependency installation failed."
                else:
                    message = f"Could not prepare the {label} runtime. Component installation failed."
                raise RuntimeSetupError(name, message, details, exc.retryable) from exc
            except Cancelled:
                raise
            except Exception as exc:
                (target / "studio-runtime.json").unlink(missing_ok=True)
                message = ("Could not prepare Transkun runtime. Windows dependency installation failed."
                           if name == "piano" and policy["constraints"] else
                           f"Could not prepare the {label} runtime. Component installation failed.")
                raise RuntimeSetupError(name, message, str(exc)) from exc

    def command_for(self, provider: str) -> list[str]:
        root = Path(__file__).resolve().parent.parent
        script = root / "studio_band_worker.py"
        runtime = PROVIDER_RUNTIME.get(provider)
        if runtime:
            if not self.available(runtime):
                raise StageError(provider, "Its isolated runtime is missing. Use Advanced → Install/repair models, then Retry.")
            return [str(self.python(runtime)), str(script)]
        if getattr(sys, "frozen", False):
            return [sys.executable, "--studio-worker"]
        return [sys.executable, str(script)]

    def fingerprint(self, provider: str) -> str:
        name = PROVIDER_RUNTIME.get(provider)
        record = {}
        if name:
            try:
                record = read_json(self.runtime_root / name / "studio-runtime.json")
            except (OSError, ValueError):
                record = {"missing": True}
        return cache_key(provider, PROVIDER_MODEL.get(provider), record, PIPELINE_VERSION)

    def statuses(self) -> list[dict]:
        return [{"runtime": name, "status": "ready" if self.available(name) else "not installed",
                 "requirements": RUNTIMES.get(name, []), **self.install_policy(name)}
                for name in (*RUNTIMES, "drums")]
