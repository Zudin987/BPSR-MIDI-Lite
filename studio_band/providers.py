"""beta.8 provider compatibility layer with BS-RoFormer six-stem evidence.

The proven specialist adapters remain in ``providers_legacy``. This file adds
only the stronger HQ separation path requested for beta.8, then patches the
legacy provider registry so every existing caller keeps the same API.
"""
from __future__ import annotations

import gc
from pathlib import Path

from . import providers_legacy as _legacy
from .providers_legacy import *  # noqa: F401,F403
from .runtime import HQ_MODEL, HQ_SIX_STEM_MODEL

_STEM_NAMES = ("vocals", "piano", "guitar", "bass", "drums", "other")
_ORIGINAL_OWNERSHIP_RESOLVER = _legacy._resolve_spectral_ownership
_ACTIVE_ROFORMER_EVIDENCE = None

# Underscore helpers were public-by-convention before the compatibility split.
# Re-expose them and route legacy calls through these names so existing focused
# tests/debug integrations can still monkeypatch the provider facade.
_audio = _legacy._audio
_events_from_midi = _legacy._events_from_midi
_prepare_mr_mt3_checkpoint = _legacy._prepare_mr_mt3_checkpoint
device_for = _legacy.device_for
_LEGACY_MR_MT3 = _legacy.mr_mt3
_LEGACY_MUSCRIPTOR = _legacy.muscriptor


def _call_legacy_compat(function, payload: dict, report):
    original = (
        _legacy._audio,
        _legacy._events_from_midi,
        _legacy._prepare_mr_mt3_checkpoint,
        _legacy.device_for,
    )
    _legacy._audio = _audio
    _legacy._events_from_midi = _events_from_midi
    _legacy._prepare_mr_mt3_checkpoint = _prepare_mr_mt3_checkpoint
    _legacy.device_for = device_for
    try:
        return function(payload, report)
    finally:
        (
            _legacy._audio,
            _legacy._events_from_midi,
            _legacy._prepare_mr_mt3_checkpoint,
            _legacy.device_for,
        ) = original


def mr_mt3(payload: dict, report) -> dict:
    return _call_legacy_compat(_LEGACY_MR_MT3, payload, report)


def muscriptor(payload: dict, report) -> dict:
    return _call_legacy_compat(_LEGACY_MUSCRIPTOR, payload, report)


def _path_from_separator(output, target: Path) -> Path:
    path = Path(output)
    if path.is_absolute() and path.exists():
        return path
    direct = target / path
    if direct.exists():
        return direct
    cwd_path = Path.cwd() / path
    if cwd_path.exists():
        return cwd_path
    return direct


def _modern_six_stem(instrumental: Path, target: Path, device: str, report) -> dict[str, str]:
    """Run BS-Roformer-SW as a six-stem second opinion for the instrumental."""
    import soundfile as sf
    import torch
    from audio_separator.separator import Separator

    # The vocal split model is already out of scope. Encourage PyTorch to return
    # cached allocations before loading the ~700 MB six-stem checkpoint.
    gc.collect()
    if device == "cuda":
        torch.cuda.empty_cache()

    # Filled by roformer() per job. Reusing the vocal model directory preserves
    # one deterministic cache for both RoFormer checkpoints/configs.
    model_dir = _modern_six_stem.model_dir
    cached = (model_dir / HQ_SIX_STEM_MODEL).is_file()
    _legacy._report(
        report,
        "Loading BS-RoFormer six-stem evidence…" if cached else
        "Downloading BS-RoFormer six-stem evidence model…",
        activity=device if cached else "download",
        stage_fraction=0.58,
    )
    separator = Separator(
        model_file_dir=str(model_dir), output_dir=str(target), output_format="WAV",
        sample_rate=44100, use_soundfile=True, normalization_threshold=0.99,
        mdxc_params={"segment_size": 256, "override_model_segment_size": False,
                     "batch_size": 1, "overlap": None, "pitch_shift": 0},
    )
    separator.load_model(model_filename=HQ_SIX_STEM_MODEL)
    _legacy._report(report, f"Separating six-stem RoFormer evidence on {device.upper()}…",
                    activity=device, stage_fraction=0.64)
    outputs = separator.separate(
        str(instrumental),
        custom_output_names={name: f"hq6_{name}" for name in
                             ("bass", "drums", "other", "vocals", "guitar", "piano")},
    )

    input_audio, sample_rate = _legacy._audio(instrumental)
    frames = len(input_audio)
    mapped: dict[str, str] = {}
    for output in outputs:
        path = _path_from_separator(output, target)
        lower = path.stem.lower()
        name = next((item for item in _STEM_NAMES if f"hq6_{item}" in lower), None)
        if name is None or not path.is_file():
            continue
        audio, sr = _legacy._audio(path)
        if sr != sample_rate or len(audio) < frames:
            raise ValueError(f"BS-RoFormer six-stem output changed the {name} timeline")
        if len(audio) > frames:
            sf.write(str(path), audio[:frames], sr, subtype="FLOAT")
        mapped[name] = str(path)
    if set(mapped) != set(_STEM_NAMES):
        missing = ", ".join(sorted(set(_STEM_NAMES) - set(mapped)))
        raise ValueError("BS-RoFormer six-stem output was incomplete" +
                         (f": {missing}" if missing else ""))
    return mapped


# Function attribute is filled by roformer() per job; workers are single-stage
# processes, so this avoids introducing another public provider protocol.
_modern_six_stem.model_dir = Path(".")


def roformer(payload: dict, report) -> dict:
    """Keep the vocal-first split, then add modern six-stem evidence on CUDA."""
    import torch

    device = _legacy.device_for(payload.get("device", "auto"))
    result = _legacy.roformer(payload, report)
    result["model"] = HQ_MODEL
    result.setdefault("warnings", [])

    # The six-stem model is deliberately an HQ/CUDA evidence layer. CPU keeps
    # the established vocal split + Demucs path rather than turning a normal
    # conversion into an extremely long hidden job.
    if device != "cuda" or not result.get("instrumental"):
        return result

    target = Path(payload["output"])
    model_dir = Path(payload["models"]) / "roformer"
    model_dir.mkdir(parents=True, exist_ok=True)
    _modern_six_stem.model_dir = model_dir
    try:
        result["stems"] = _modern_six_stem(Path(result["instrumental"]), target, device, report)
        result["model"] = f"{HQ_MODEL}+{HQ_SIX_STEM_MODEL}"
        result["six_stem_evidence"] = True
    except Exception as exc:
        # The vocal split is already valid. A second-opinion failure must not
        # throw away the whole conversion; Demucs remains the deterministic
        # six-stem source and the warning/provenance makes the fallback visible.
        result["warnings"].append(
            f"BS-RoFormer six-stem evidence unavailable: {exc}. Demucs ensemble retained."
        )
        result["six_stem_evidence"] = False
    finally:
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    result["model_files"] = [str(path) for path in model_dir.iterdir() if path.is_file()]
    return result


def _discover_roformer_evidence(audio_path: Path):
    """Load cached sibling hq6_* stems produced by the preceding HQ split."""
    import torch

    parent = audio_path.parent
    evidence = {}
    input_audio, sample_rate = _legacy._audio(audio_path)
    frames = len(input_audio)
    for name in _STEM_NAMES:
        candidates = sorted(parent.glob(f"hq6_{name}.*"))
        path = next((item for item in candidates if item.is_file()), None)
        if path is None:
            return None
        audio, sr = _legacy._audio(path)
        if sr != sample_rate or len(audio) != frames or audio.shape[1] != input_audio.shape[1]:
            return None
        evidence[name] = torch.from_numpy(audio.T.copy())
    return evidence


def _ownership_with_roformer(waveform, six, fine, sample_rate: int, report):
    """Blend the RoFormer opinion into Demucs evidence before ownership masks."""
    evidence = _ACTIVE_ROFORMER_EVIDENCE
    if not evidence:
        return _ORIGINAL_OWNERSHIP_RESOLVER(waveform, six, fine, sample_rate, report)

    # htdemucs_6s remains the mixture-wide base. htdemucs_ft and BS-Roformer-SW
    # become equal second opinions where both exist; SW supplies direct piano
    # and guitar evidence that the four-stem fine-tuned Demucs model lacks.
    combined = dict(fine or {})
    for name, tensor in evidence.items():
        combined[name] = ((combined[name] + tensor) * 0.5
                          if name in combined else tensor)
    return _ORIGINAL_OWNERSHIP_RESOLVER(waveform, six, combined, sample_rate, report)


def demucs(payload: dict, report) -> dict:
    """Run the established Demucs ensemble, consuming sibling RoFormer evidence."""
    global _ACTIVE_ROFORMER_EVIDENCE

    evidence = None
    audio_path = Path(payload["audio"])
    # Only an HQ vocal split produces hq_instrumental + hq6_* siblings. Standard
    # jobs therefore pay no extra I/O or model cost.
    if "hq_instrumental" in audio_path.stem.lower():
        try:
            evidence = _discover_roformer_evidence(audio_path)
        except Exception:
            evidence = None

    _ACTIVE_ROFORMER_EVIDENCE = evidence
    _legacy._resolve_spectral_ownership = _ownership_with_roformer
    try:
        result = _legacy.demucs(payload, report)
    finally:
        _ACTIVE_ROFORMER_EVIDENCE = None
        _legacy._resolve_spectral_ownership = _ownership_with_roformer

    if evidence:
        result["model"] = result.get("model", "htdemucs_6s") + "+BS-Roformer-SW"
        result["six_stem_evidence"] = True
    return result


# Patch the backing module used by its existing run_provider() dispatcher. All
# other providers remain the established implementations; wrappers preserve the
# pre-split monkeypatch/debug surface for MR-MT3 and MuScriptor.
_legacy._resolve_spectral_ownership = _ownership_with_roformer
_legacy.PROVIDERS["roformer"] = roformer
_legacy.PROVIDERS["demucs"] = demucs
_legacy.PROVIDERS["mr_mt3"] = mr_mt3
_legacy.PROVIDERS["muscriptor"] = muscriptor
PROVIDERS = _legacy.PROVIDERS
DISTRIBUTIONS = _legacy.DISTRIBUTIONS
run_provider = _legacy.run_provider
