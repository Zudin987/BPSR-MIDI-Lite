"""Optional heavyweight precision judges.

YourMT3+ is invoked from its upstream Hugging Face Space at runtime because the
upstream code is GPL-3.0; BPSR does not vendor or redistribute that code.
Mega53 is similarly downloaded from its pinned upstream MIT source/release and is
used only for local piano-vs-guitar ownership evidence, never as the main separator.
"""
from __future__ import annotations

from argparse import Namespace
import gc
import hashlib
import os
from pathlib import Path
import shutil
import sys
import urllib.request
import zipfile

YOURMT3_SPACE_REPO = "mimbres/YourMT3"
YOURMT3_SPACE_REVISION = "5e66c1e"
YOURMT3_MODEL_REPO = "mimbres/YourMT3"
YOURMT3_MODEL_REVISION = "e45ebd70398682d54b7bb1901a5216e18f3b1824"
YOURMT3_EXPERIMENT = "mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b36_nops"
YOURMT3_CHECKPOINT = f"logs/2024/{YOURMT3_EXPERIMENT}/checkpoints/last.ckpt"

MEGA53_SOURCE_REVISION = "0e5f1159fc5ea87fc13b957584e178b4977e5dd3"
MEGA53_RELEASE = "v1.0.21"
MEGA53_CONFIG = "mvsep_mega_model_bs_roformer_53_stems.yaml"
MEGA53_CHECKPOINT = "mvsep_mega_model_bs_roformer_53_stems_v1.ckpt"
MEGA53_CONFIG_SHA256 = "7e198062a251587088adb91215a4f44ab59e67bd62fcc805cf54d6e7dfc51103"
MEGA53_CHECKPOINT_SHA256 = "c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f"
MEGA53_CHECKPOINT_SIZE = 1_368_919_887


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, target: Path, *, sha256: str | None = None,
              max_bytes: int | None = None, report=None, message: str = "Downloading model…") -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        if sha256 is None or _sha256(target) == sha256:
            return target
        target.unlink(missing_ok=True)
    partial = target.with_suffix(target.suffix + ".partial")
    partial.unlink(missing_ok=True)
    if report:
        report({"message": message, "activity": "download", "stage_fraction": .08, "indeterminate": True})
    request = urllib.request.Request(url, headers={"User-Agent": "BPSR-MIDI-Studio"})
    try:
        with urllib.request.urlopen(request, timeout=90) as remote, partial.open("wb") as out:
            size = 0
            while chunk := remote.read(1024 * 1024):
                size += len(chunk)
                if max_bytes and size > max_bytes:
                    raise ValueError("Model download is unexpectedly large")
                out.write(chunk)
        if sha256 and _sha256(partial) != sha256:
            raise ValueError("Downloaded model checksum does not match the pinned upstream release")
        partial.replace(target)
        return target
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _yourmt3_source(models: Path, report=None) -> Path:
    from huggingface_hub import snapshot_download

    target = models / "yourmt3" / "upstream-space"
    marker = target / ".bpsr-revision"
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == YOURMT3_SPACE_REVISION:
        return target
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    if report:
        report({
            "message": "Downloading pinned YourMT3+ inference code (optional cross-check)…",
            "activity": "download", "stage_fraction": .05, "indeterminate": True,
        })
    snapshot_download(
        repo_id=YOURMT3_SPACE_REPO, repo_type="space", revision=YOURMT3_SPACE_REVISION,
        allow_patterns=["amt/src/**", "model_helper.py"], local_dir=str(target),
    )
    marker.write_text(YOURMT3_SPACE_REVISION, encoding="utf-8")
    return target


def _yourmt3_checkpoint(source: Path, models: Path, report=None) -> Path:
    from huggingface_hub import hf_hub_download

    expected = source / "amt" / "logs" / "2024" / YOURMT3_EXPERIMENT / "checkpoints" / "last.ckpt"
    if expected.is_file() and expected.stat().st_size > 1024 * 1024:
        return expected
    if report:
        report({
            "message": "Downloading YourMT3+ multi-instrument checkpoint…",
            "activity": "download", "stage_fraction": .12, "indeterminate": True,
        })
    cached = Path(hf_hub_download(
        repo_id=YOURMT3_MODEL_REPO, filename=YOURMT3_CHECKPOINT,
        revision=YOURMT3_MODEL_REVISION, cache_dir=str(models / "huggingface"),
    ))
    expected.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cached, expected)
    return expected


def _yourmt3_args():
    checkpoint = f"{YOURMT3_EXPERIMENT}@last.ckpt"
    return [
        checkpoint, "-p", "2024", "-tk", "mc13_full_plus_256",
        "-dec", "multi-t5", "-nl", "26", "-enc", "perceiver-tf",
        "-sqr", "1", "-ff", "moe", "-wf", "4", "-nmoe", "8", "-kmoe", "2",
        "-act", "silu", "-epe", "rope", "-rp", "1", "-ac", "spec",
        "-hop", "300", "-atc", "1", "-pr", "16",
    ]


def yourmt3_review(payload: dict, report=None) -> dict:
    """Run YourMT3+ only on already-selected uncertain windows."""
    import soundfile as sf
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("YourMT3+ precision review requires CUDA")
    segments = list(payload.get("segments") or [])[:3]
    if not segments:
        return {"events": [], "review_only": True, "model": "YourMT3+"}

    models = Path(payload["models"])
    source = _yourmt3_source(models, report)
    checkpoint = _yourmt3_checkpoint(source, models, report)
    src_path = source / "amt" / "src"
    sys.path.insert(0, str(src_path))
    sys.path.insert(0, str(source))
    previous_cwd = Path.cwd()
    out = Path(payload["output"])
    out.mkdir(parents=True, exist_ok=True)
    events = []
    model = None
    try:
        os.chdir(source)
        import importlib.util
        spec = importlib.util.spec_from_file_location("bpsr_yourmt3_model_helper", source / "model_helper.py")
        if not spec or not spec.loader:
            raise RuntimeError("Could not load the pinned YourMT3+ model helper")
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        if report:
            report({
                "message": "Loading YourMT3+ targeted multi-instrument judge…",
                "activity": "gpu", "stage_fraction": .22, "indeterminate": True,
            })
        # Match the official Space: construct/load on CPU first, then move once.
        model = helper.load_model_checkpoint(_yourmt3_args(), device="cpu")
        model = model.to("cuda")

        audio, sample_rate = sf.read(str(payload["audio"]), dtype="float32", always_2d=True)
        for index, region in enumerate(segments):
            start = max(0.0, float(region["start"]))
            end = min(len(audio) / sample_rate, float(region["end"]))
            if end <= start:
                continue
            clip = out / f"yourmt3_region_{index}.wav"
            sf.write(str(clip), audio[round(start * sample_rate):round(end * sample_rate)], sample_rate, subtype="FLOAT")
            if report:
                report({
                    "message": f"YourMT3+ cross-check · region {index+1}/{len(segments)}",
                    "activity": "gpu", "stage_fraction": .32 + .55 * (index / max(1, len(segments))),
                    "indeterminate": False,
                })
            region_dir = out / f"yourmt3_work_{index}"
            region_dir.mkdir(exist_ok=True)
            os.chdir(region_dir)
            midi = Path(helper.transcribe(model, {"filepath": str(clip), "track_name": f"region_{index}"}))
            from . import providers_legacy as legacy
            from .music import MusicEvent
            for record in legacy._events_from_midi(midi, "yourmt3"):
                event = MusicEvent.from_dict(record)
                event.start += start
                event.end += start
                event.confidence = min(.78, max(.62, event.confidence + .08))
                event.original_confidence = event.confidence
                event.tags.add("yourmt3_review")
                event.evidence.update({
                    "coverage_start": start, "coverage_end": end,
                    "review_only": True,
                    "confidence_kind": "YourMT3+ targeted independent model prior",
                })
                events.append(event.to_dict())
            os.chdir(source)
    finally:
        os.chdir(previous_cwd)
        if model is not None:
            del model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        for value in (str(source), str(src_path)):
            while value in sys.path:
                sys.path.remove(value)

    return {
        "events": events, "device": "cuda", "model": "YourMT3+ PTF.MoE+Multi noPS",
        "review_only": True, "space_revision": YOURMT3_SPACE_REVISION,
        "checkpoint_revision": YOURMT3_MODEL_REVISION, "model_files": [str(checkpoint)],
        "warnings": [
            "YourMT3+ upstream inference code is GPL-3.0 and is downloaded at runtime; "
            "BPSR does not vendor it. The checkpoint repository declares Apache-2.0."
        ],
    }


def _mega53_source(models: Path, report=None) -> Path:
    target = models / "mega53" / "source"
    marker = target / ".bpsr-revision"
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == MEGA53_SOURCE_REVISION:
        return target
    archive = models / "mega53" / f"source-{MEGA53_SOURCE_REVISION}.zip"
    url = "https://github.com/ZFTurbo/Music-Source-Separation-Training/archive/" f"{MEGA53_SOURCE_REVISION}.zip"
    _download(url, archive, max_bytes=100 * 1024 * 1024, report=report,
              message="Downloading pinned Mega53 inference source…")
    extract = target.parent / "extract"
    shutil.rmtree(extract, ignore_errors=True)
    extract.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(extract)
    root = next(path for path in extract.iterdir() if path.is_dir())
    shutil.rmtree(target, ignore_errors=True)
    shutil.move(str(root), str(target))
    shutil.rmtree(extract, ignore_errors=True)
    marker.write_text(MEGA53_SOURCE_REVISION, encoding="utf-8")
    return target


def _mega53_assets(models: Path, report=None) -> tuple[Path, Path]:
    root = models / "mega53"
    base = "https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/" f"{MEGA53_RELEASE}"
    config = _download(
        f"{base}/{MEGA53_CONFIG}", root / MEGA53_CONFIG,
        sha256=MEGA53_CONFIG_SHA256, max_bytes=64 * 1024, report=report,
        message="Downloading verified Mega53 configuration…",
    )
    checkpoint = _download(
        f"{base}/{MEGA53_CHECKPOINT}", root / MEGA53_CHECKPOINT,
        sha256=MEGA53_CHECKPOINT_SHA256, max_bytes=MEGA53_CHECKPOINT_SIZE + 1024 * 1024,
        report=report, message="Downloading verified Mega53 53-stem checkpoint (~1.4 GB)…",
    )
    if checkpoint.stat().st_size != MEGA53_CHECKPOINT_SIZE:
        raise ValueError("Mega53 checkpoint size does not match the pinned release")
    return config, checkpoint


def _pitch_energy(samples, sample_rate: int, pitch: int) -> float:
    import numpy as np

    values = np.asarray(samples, dtype="float64")
    if values.ndim == 2:
        values = values.mean(axis=0) if values.shape[0] <= 2 else values.mean(axis=1)
    if len(values) < 256:
        return 0.0
    values = values - float(values.mean())
    nfft = 1 << min(15, max(12, (len(values)-1).bit_length()))
    if len(values) < nfft:
        values = np.pad(values, (0, nfft-len(values)))
    else:
        values = values[:nfft]
    power = np.abs(np.fft.rfft(values * np.hanning(len(values)))) ** 2
    freqs = np.fft.rfftfreq(len(values), 1.0 / sample_rate)
    f0 = 440.0 * 2 ** ((pitch - 69) / 12.0)
    total = 0.0
    for harmonic in range(1, 5):
        center = f0 * harmonic
        if center >= sample_rate * .48:
            break
        width = max(3.0, center * .014)
        mask = (freqs >= center-width) & (freqs <= center+width)
        if mask.any():
            total += float(power[mask].sum()) / (harmonic ** .5)
    return total


def mega53_ownership(payload: dict, report=None) -> dict:
    """Use Mega53 only to judge piano-vs-guitar ownership in uncertain windows."""
    import numpy as np
    import soundfile as sf
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("Mega53 ownership review requires CUDA")
    segments = list(payload.get("segments") or [])[:3]
    candidates = list(payload.get("candidates") or [])
    if not segments or not candidates:
        return {"ownership": [], "review_only": True, "model": "MVSep Mega53"}

    models = Path(payload["models"])
    source = _mega53_source(models, report)
    config_path, checkpoint_path = _mega53_assets(models, report)
    sys.path.insert(0, str(source))
    previous_cwd = Path.cwd()
    model = None
    ownership = []
    try:
        os.chdir(source)
        from utils.settings import get_model_from_config
        from utils.model_utils import bigshifts_wrapper, load_start_checkpoint

        model, config = get_model_from_config("bs_roformer", str(config_path))
        old = torch.load(str(checkpoint_path), map_location="cpu", weights_only=False)
        args = Namespace(
            start_check_point=str(checkpoint_path), model_type="bs_roformer",
            lora_checkpoint_loralib="", lora_checkpoint_peft="", load_only_compatible_weights=False,
        )
        load_start_checkpoint(args, model, old, type_="inference")
        model = model.to("cuda").eval()
        audio, sample_rate = sf.read(str(payload["audio"]), dtype="float32", always_2d=True)
        mix = audio.T

        for region_index, region in enumerate(segments):
            start = max(0.0, float(region["start"]))
            end = min(len(audio) / sample_rate, float(region["end"]))
            region_candidates = [
                item for item in candidates
                if start <= (float(item["start"]) + float(item["end"])) * .5 <= end
                and item.get("pitch") is not None and item.get("source") in {"piano", "guitar"}
            ]
            if not region_candidates or end <= start:
                continue
            if report:
                report({
                    "message": f"Mega53 ownership check · region {region_index+1}/{len(segments)}",
                    "activity": "gpu", "stage_fraction": .30 + .55 * (region_index / max(1, len(segments))),
                    "indeterminate": False,
                })
            clip = mix[:, round(start*sample_rate):round(end*sample_rate)]
            separated = bigshifts_wrapper(
                config, model, clip, torch.device("cuda"), model_type="bs_roformer", pbar=False, bigshifts=1,
            )
            if not isinstance(separated, dict):
                names = list(getattr(config.training, "instruments", []))
                separated = {name: separated[i] for i, name in enumerate(names)}
            guitar_stems = {name: value for name, value in separated.items() if "guitar" in str(name).lower()}
            piano_stems = {
                name: value for name, value in separated.items()
                if "piano" in str(name).lower() or str(name).lower() == "keys"
            }

            for item in region_candidates:
                local_start = max(0.0, float(item["start"]) - start - .025)
                local_end = min(end-start, max(local_start + .10, float(item["end"]) - start + .06))
                left, right = round(local_start*sample_rate), round(local_end*sample_rate)
                pitch = int(item["pitch"])
                guitar_energy = sum(_pitch_energy(value[..., left:right], sample_rate, pitch) for value in guitar_stems.values())
                piano_energy = sum(_pitch_energy(value[..., left:right], sample_rate, pitch) for value in piano_stems.values())
                margin_db = 10.0 * np.log10((guitar_energy + 1e-18) / (piano_energy + 1e-18))
                ownership.append({
                    "source": str(item["source"]), "pitch": pitch,
                    "start": float(item["start"]), "end": float(item["end"]),
                    "guitar_energy": float(guitar_energy), "piano_energy": float(piano_energy),
                    "guitar_vs_piano_db": round(float(margin_db), 3),
                    "preferred": "guitar" if margin_db > 2.0 else "piano" if margin_db < -2.0 else "ambiguous",
                    "coverage_start": start, "coverage_end": end,
                })
            del separated
            gc.collect()
            torch.cuda.empty_cache()
    finally:
        os.chdir(previous_cwd)
        if model is not None:
            del model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        while str(source) in sys.path:
            sys.path.remove(str(source))

    return {
        "ownership": ownership, "device": "cuda", "model": "MVSep Mega 53 Stems BS-RoFormer",
        "review_only": True, "source_revision": MEGA53_SOURCE_REVISION,
        "model_files": [str(config_path), str(checkpoint_path)],
        "warnings": [
            "Mega53 is used only for targeted instrument-ownership evidence; "
            "its 53 outputs are not used as replacement song stems."
        ],
    }
