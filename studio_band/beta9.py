"""beta.9 quality pass: targeted drum/piano evidence and conservative fusion.

This module is intentionally additive.  beta.8 remains the proven baseline and
beta.9 patches only the optional quality path, so a missing specialist never
blocks an Audio -> Band conversion.
"""
from __future__ import annotations

import math
import os
import shutil
import urllib.request
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

ARIA_AMT_REVISION = "a1ab73fc901d1759ec3bc173c146b3c6a3040261"
ARIA_UTILS_REVISION = "4ed0749d2d70918610f03a5316bf283479ff9d09"
ARIA_CHECKPOINT_REVISION = "8cc4cf5c83b47f2689ac256a947b2a57c17a4c8b"
ARIA_CHECKPOINT = "piano-medium-double-1.0.safetensors"
ARIA_CHECKPOINT_SIZE = 446_577_344
ARIA_CHECKPOINT_SHA256 = "089d3129dbe93246aeda55efe668c8a48af08afaf9dd15c64cef0a07c0fb30a4"
ARIA_SOURCE = (
    "aria-amt @ https://github.com/EleutherAI/aria-amt/archive/"
    f"{ARIA_AMT_REVISION}.zip"
)
ARIA_UTILS_SOURCE = (
    "ariautils @ https://github.com/EleutherAI/aria-utils/archive/"
    f"{ARIA_UTILS_REVISION}.zip"
)
ARIA_CHECKPOINT_URL = (
    "https://huggingface.co/datasets/loubb/aria-midi/resolve/"
    f"{ARIA_CHECKPOINT_REVISION}/{ARIA_CHECKPOINT}?download=true"
)
DRUMSEP_MODEL = "drumsep-6stem"

_APPLIED = False


def _patch_runtimes(runtime) -> None:
    drumsep_requirements = [
        "mdxnet-infer==0.1.0",
        "torch==2.11.0",
        "torchaudio==2.11.0",
        "numpy==1.26.4",
        "soundfile==0.13.1",
    ]
    aria_base_requirements = [
        "torch==2.11.0",
        "torchaudio==2.11.0",
        "numpy==1.26.4",
        "soundfile==0.13.1",
        "safetensors>=0.4",
        "librosa>=0.10",
        "tqdm>=4.64",
        "orjson>=3.9",
        "mido==1.3.3",
    ]
    aria_requirements = [*aria_base_requirements, ARIA_UTILS_SOURCE, ARIA_SOURCE]

    runtime.RUNTIMES["drumsep"] = drumsep_requirements
    runtime.RUNTIME_TORCH_BACKENDS["drumsep"] = {"cpu": "cpu", "cuda": "cu128"}
    runtime.RUNTIME_LABELS["drumsep"] = "DrumSep kit separator"
    runtime.RUNTIME_VALIDATION["drumsep"] = (
        "import importlib.metadata as metadata\n"
        "import mdxnet_infer, torch, torchaudio\n"
        "assert metadata.version('mdxnet-infer') == '0.1.0'\n"
        "assert metadata.version('torch').partition('+')[0] == '2.11.0'\n"
        "assert metadata.version('torchaudio').partition('+')[0] == '2.11.0'"
    )
    runtime.PROVIDER_RUNTIME["drumsep"] = "drumsep"
    runtime.PROVIDER_MODEL["drumsep"] = DRUMSEP_MODEL

    # Upstream Aria-AMT declares torchaudio<=2.5 and its batch CLI asserts POSIX.
    # Studio therefore installs the pinned source with --no-deps into its own
    # CUDA 12.8 / Torch 2.11 environment and uses only the upstream single-file
    # decoder primitives. This keeps current NVIDIA support and works on Windows.
    runtime.RUNTIMES["aria"] = aria_requirements
    runtime.RUNTIME_TORCH_BACKENDS["aria"] = {"cuda": "cu128"}
    runtime.RUNTIME_LABELS["aria"] = "Aria-AMT piano reviewer"
    runtime.RUNTIME_VALIDATION["aria"] = (
        "import importlib.metadata as metadata\n"
        "import amt.run, amt.inference.transcribe, ariautils, torch, torchaudio\n"
        "assert metadata.version('aria-amt') == '0.0.1'\n"
        "assert metadata.version('ariautils') == '0.0.1'\n"
        "assert metadata.version('torch').partition('+')[0] == '2.11.0'\n"
        "assert metadata.version('torchaudio').partition('+')[0] == '2.11.0'"
    )
    runtime.PROVIDER_RUNTIME["aria_amt"] = "aria"
    runtime.PROVIDER_MODEL["aria_amt"] = f"medium-double@{ARIA_AMT_REVISION[:10]}"

    original_install = runtime.RuntimeManager.install

    def install(self, name: str, *, device: str = "cpu", cancel=None, progress=None,
                repair: bool = False) -> None:
        if name != "aria":
            return original_install(
                self, name, device=device, cancel=cancel, progress=progress, repair=repair
            )
        if device == "auto":
            device = "cuda" if runtime.detect_hardware().cuda else "cpu"
        if device != "cuda":
            raise runtime.RuntimeSetupError(
                "aria",
                "Aria-AMT targeted review requires a working NVIDIA CUDA device.",
                "The beta.9 Aria-AMT adapter never starts an implicit CPU transcription.",
            )
        if self.available(name, device=device) and not repair:
            return

        target = self.runtime_root / name
        with runtime.file_lock(self.runtime_root / (name + ".lock")):
            if self.available(name, device=device) and not repair:
                return
            if repair:
                (target / "studio-runtime.json").unlink(missing_ok=True)
            environment = self.environment()
            try:
                runtime.emit_progress(
                    progress, "Preparing Aria-AMT piano reviewer (first use only)…",
                    activity="install", stage_fraction=0.0, indeterminate=True,
                )
                uv = self._uv(cancel, progress)
                if not self.python(name).exists():
                    runtime.run_process(
                        [str(uv), "venv", "--python", "3.11", "--managed-python", str(target)],
                        stage="Runtime setup", env=environment, cancel=cancel,
                        progress=progress, timeout=1800,
                    )
                args = [str(uv), "pip", "install", "--python", str(self.python(name))]
                if repair:
                    args.append("--reinstall")
                runtime.emit_progress(
                    progress, "Installing Aria-AMT CUDA compute components…",
                    activity="install", stage_fraction=0.30, indeterminate=True,
                )
                runtime.run_process(
                    args + aria_base_requirements +
                    ["--torch-backend", "cu128", "--strict"],
                    stage="Runtime setup", env=environment, cancel=cancel,
                    progress=progress, timeout=3600,
                )
                runtime.emit_progress(
                    progress, "Installing pinned Aria-AMT source…",
                    activity="install", stage_fraction=0.66, indeterminate=True,
                )
                runtime.run_process(
                    args + ["--no-deps", ARIA_UTILS_SOURCE, ARIA_SOURCE],
                    stage="Runtime setup", env=environment, cancel=cancel,
                    progress=progress, timeout=1800,
                )
                validation = runtime.RUNTIME_VALIDATION["aria"] + (
                    "\nassert torch.version.cuda and torch.version.cuda.startswith('12.8')"
                    "\nassert torch.cuda.is_available()"
                    "\nvalue=(torch.ones(8, device='cuda')*2).sum().item()"
                    "\ntorch.cuda.synchronize()"
                    "\nassert value == 16"
                )
                runtime.run_process(
                    [str(self.python(name)), "-c", validation],
                    stage="Runtime setup", env=environment, cancel=cancel,
                    progress=progress, timeout=300,
                )
                frozen = runtime.run_process(
                    [str(uv), "pip", "freeze", "--python", str(self.python(name))],
                    stage="Runtime setup", env=environment, cancel=cancel, timeout=60,
                )
                runtime.atomic_json(
                    target / "studio-runtime.json",
                    {
                        "requirements": runtime.RUNTIMES["aria"],
                        "packages": frozen,
                        "python": "3.11",
                        "device_install": "cuda",
                        "torch_backend": "cu128",
                        "constraints": [],
                        "binary_only": [],
                        "validated": True,
                    },
                )
                runtime.emit_progress(
                    progress, "Aria-AMT piano reviewer ready",
                    activity="install", stage_fraction=1.0, indeterminate=False,
                )
            except runtime.Cancelled:
                raise
            except Exception as exc:
                (target / "studio-runtime.json").unlink(missing_ok=True)
                details = getattr(exc, "details", "") or str(exc)
                raise runtime.RuntimeSetupError(
                    "aria",
                    "Could not prepare the optional Aria-AMT piano reviewer.",
                    details,
                ) from exc

    runtime.RuntimeManager.install = install


def _drum_onsets(samples, sample_rate: int, role: str):
    import numpy as np

    audio = np.asarray(samples, dtype="float32")
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    elif audio.ndim != 1:
        audio = audio.reshape(-1)
    if not len(audio):
        return []

    hop = 512
    frame = 1536
    energies = []
    for start in range(0, len(audio), hop):
        chunk = audio[start:min(len(audio), start + frame)]
        energies.append(float(np.sqrt(np.mean(chunk * chunk) + 1e-12)))
    energies = np.asarray(energies, dtype="float64")
    if len(energies) < 3 or float(energies.max()) < 1e-6:
        return []

    compressed = np.log1p(energies * 180.0)
    flux = np.maximum(0.0, np.diff(compressed, prepend=compressed[0]))
    positive = flux[flux > 0]
    if not len(positive):
        return []
    floor = max(float(np.percentile(positive, 72)) * 0.70, float(flux.max()) * 0.075)
    min_gap = {
        "KICK": .065, "SNARE": .065, "TOM": .075,
        "CLOSED_HAT": .035, "RIDE": .060, "CRASH": .120,
    }.get(role, .055)
    min_steps = max(1, round(min_gap * sample_rate / hop))
    peak = float(flux.max()) + 1e-12
    found = []
    last = -10**9
    for index in range(1, len(flux) - 1):
        if index - last < min_steps or flux[index] < floor:
            continue
        if flux[index] < flux[index - 1] or flux[index] < flux[index + 1]:
            continue
        strength = min(1.0, float(flux[index]) / peak)
        local_energy = min(1.0, float(energies[index]) / (float(energies.max()) + 1e-12))
        confidence = min(.88, .54 + .22 * math.sqrt(strength) + .12 * local_energy)
        start = max(0.0, index * hop / sample_rate - .006)
        found.append((start, confidence, strength))
        last = index
    return found


def _drumsep_provider(legacy, payload: dict, report) -> dict:
    import soundfile as sf
    from mdxnet_infer import MDX23CInference
    from .music import MusicEvent

    device = legacy.device_for(payload.get("device", "auto"))
    cache = Path(payload["models"]) / "drumsep"
    cache.mkdir(parents=True, exist_ok=True)
    cached = MDX23CInference.is_cached(DRUMSEP_MODEL, cache_dir=cache)
    legacy._report(
        report,
        "Loading DrumSep six-kit evidence…" if cached else
        "Downloading verified DrumSep six-kit model…",
        activity=device if cached else "download", stage_fraction=.06,
    )
    engine = MDX23CInference.from_pretrained(
        DRUMSEP_MODEL, cache_dir=cache, device=device, progress=False
    )
    audio, sample_rate = legacy._audio(payload["audio"])
    legacy._report(
        report, f"Separating kick/snare/toms/hats/ride/crash on {device.upper()}…",
        activity=device, stage_fraction=.20,
    )
    separated = engine.separate(audio, sample_rate=sample_rate, progress=False)
    target = Path(payload["output"])
    target.mkdir(parents=True, exist_ok=True)
    stems = {}
    events = []
    roles = {
        "kick": "KICK", "snare": "SNARE", "toms": "TOM",
        "hh": "CLOSED_HAT", "ride": "RIDE", "crash": "CRASH",
    }
    for name, role in roles.items():
        samples = separated.get(name)
        if samples is None:
            continue
        path = target / f"drumsep_{name}.wav"
        sf.write(str(path), samples, sample_rate, subtype="FLOAT")
        stems[name] = str(path)
        for onset, confidence, strength in _drum_onsets(samples, sample_rate, role):
            events.append(
                MusicEvent(
                    "drums", role, onset, onset + (.09 if role in {"CRASH", "RIDE"} else .065),
                    None, max(35, min(120, round(45 + strength * 65))),
                    confidence, "drumsep", {"drumsep_evidence", "kit_separation"},
                    evidence={
                        "confidence_kind": "MDX23C kit isolation plus separated-stem onset",
                        "kit_stem": name,
                        "onset_strength": strength,
                    },
                ).to_dict()
            )
    if set(stems) != set(roles):
        missing = ", ".join(sorted(set(roles) - set(stems)))
        raise ValueError(f"DrumSep did not return all six kit stems: {missing}")
    model_files = [str(path) for path in cache.rglob("*") if path.is_file()]
    return {
        "events": events, "stems": stems, "device": device, "model": DRUMSEP_MODEL,
        "model_files": model_files,
        "warnings": [
            "DrumSep checkpoint license terms are not formally documented by its original authors; "
            "beta.9 uses it only in the explicit quality/cross-check path."
        ],
    }


def _download_aria_checkpoint(legacy, models: Path, report) -> Path:
    models.mkdir(parents=True, exist_ok=True)
    target = models / ARIA_CHECKPOINT
    if (target.is_file() and target.stat().st_size == ARIA_CHECKPOINT_SIZE and
            legacy.file_hash(target) == ARIA_CHECKPOINT_SHA256):
        return target
    target.unlink(missing_ok=True)
    partial = target.with_suffix(target.suffix + ".partial")
    partial.unlink(missing_ok=True)
    legacy._report(
        report, "Downloading pinned Aria-AMT piano checkpoint…",
        activity="download", stage_fraction=.05,
    )
    request = urllib.request.Request(ARIA_CHECKPOINT_URL, headers={"User-Agent": "BPSR-MIDI-Studio"})
    try:
        with urllib.request.urlopen(request, timeout=60) as remote, partial.open("wb") as out:
            total = 0
            while chunk := remote.read(1024 * 1024):
                total += len(chunk)
                if total > ARIA_CHECKPOINT_SIZE + 8 * 1024 * 1024:
                    raise ValueError("Aria-AMT checkpoint download is unexpectedly large")
                out.write(chunk)
        if partial.stat().st_size != ARIA_CHECKPOINT_SIZE:
            raise ValueError("Aria-AMT checkpoint size does not match the pinned artifact")
        if legacy.file_hash(partial) != ARIA_CHECKPOINT_SHA256:
            raise ValueError("Aria-AMT checkpoint checksum does not match the pinned artifact")
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def _aria_amt_provider(legacy, payload: dict, report) -> dict:
    import soundfile as sf
    import torch
    import torchaudio.functional as audio_functional
    from amt.audio import AudioTransform, SAMPLE_RATE
    from amt.config import load_model_config
    from amt.inference import transcribe as transcribe_module
    from amt.inference.model import AmtEncoderDecoder, ModelConfig
    from amt.tokenizer import AmtTokenizer
    from amt.utils import _load_weight

    device = legacy.device_for(payload.get("device", "auto"), allow_cpu_fallback=False)
    if device != "cuda":
        raise RuntimeError("Aria-AMT targeted review requires CUDA")
    segments = list(payload.get("segments") or [])
    if not segments:
        return {"events": [], "device": device, "model": "medium-double", "model_files": []}

    checkpoint = _download_aria_checkpoint(
        legacy, Path(payload["models"]) / "aria", report
    )
    legacy._report(
        report, "Loading Aria-AMT targeted piano reviewer…",
        activity="cuda", stage_fraction=.14,
    )
    tokenizer = AmtTokenizer()
    config = ModelConfig(**load_model_config("medium-double"))
    config.set_vocab_size(tokenizer.vocab_size)
    model = AmtEncoderDecoder(config)
    state = _load_weight(ckpt_path=str(checkpoint))
    normalized = {
        (key[len("_orig_mod."):] if key.startswith("_orig_mod.") else key): value
        for key, value in state.items()
    }
    model.load_state_dict(normalized)
    cache_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float
    model.decoder.setup_cache(
        batch_size=1, max_seq_len=transcribe_module.MAX_BLOCK_LEN, dtype=cache_dtype
    )
    model.cuda().eval()
    transform = AudioTransform().cuda()
    target = Path(payload["output"])
    target.mkdir(parents=True, exist_ok=True)
    events = []
    target_samples = round(SAMPLE_RATE * transcribe_module.LEN_MS / 1000)

    with sf.SoundFile(str(payload["audio"])) as source:
        source_rate = int(source.samplerate)
        for index, region in enumerate(segments):
            start = max(0.0, float(region["start"]))
            end = max(start + .05, float(region["end"]))
            source.seek(max(0, min(len(source), round(start * source_rate))))
            frames = max(1, round((end - start) * source_rate))
            samples = source.read(frames, dtype="float32", always_2d=True)
            mono = torch.from_numpy(samples.mean(axis=1).copy())
            if source_rate != SAMPLE_RATE:
                mono = audio_functional.resample(mono, source_rate, SAMPLE_RATE)
            if len(mono) < target_samples:
                mono = torch.nn.functional.pad(mono, (0, target_samples - len(mono)))
            else:
                mono = mono[:target_samples]
            legacy._report(
                report,
                f"Aria-AMT reviewing piano region {index + 1}/{len(segments)}…",
                activity="cuda",
                stage_fraction=.22 + .66 * (index / max(1, len(segments))),
            )
            sequence = [tokenizer.bos_tok]
            silent = transcribe_module._get_silent_intervals(mono)
            (sequence,) = transcribe_module.process_segments(
                tasks=[((mono, sequence), 0)],
                model=model, audio_transform=transform, tokenizer=tokenizer,
                logger=__import__("logging").getLogger(__name__),
            )
            sequence = transcribe_module._process_silent_intervals(
                sequence, intervals=silent, tokenizer=tokenizer
            )
            if len(sequence) < 10:
                continue
            last_onset = next(
                (token[1] for token in reversed(sequence)
                 if isinstance(token, tuple) and token[0] == "onset"),
                None,
            )
            if last_onset is None:
                continue
            midi_dict = tokenizer.detokenize(tokenized_seq=sequence, len_ms=last_onset)
            midi_dict.remove_redundant_pedals()
            midi_path = target / f"aria_region_{index:02d}.mid"
            midi_dict.to_midi().save(str(midi_path))
            for record in legacy._events_from_midi(midi_path, "aria_amt", "piano"):
                relative_start = float(record["start"])
                relative_end = float(record["end"])
                if relative_start >= end - start + .10:
                    continue
                record["start"] = start + relative_start
                record["end"] = min(end, start + relative_end)
                if record["end"] <= record["start"]:
                    continue
                record["confidence"] = .66
                record["original_confidence"] = .66
                record["tags"] = sorted(set(record.get("tags", [])) | {"targeted_piano_review"})
                record["evidence"] = {
                    **record.get("evidence", {}),
                    "coverage_start": start,
                    "coverage_end": end,
                    "region_score": float(region.get("score", 0.0)),
                    "confidence_kind": "Aria-AMT targeted piano second opinion",
                }
                events.append(record)
    del model
    torch.cuda.empty_cache()
    return {
        "events": events, "device": device, "model": "medium-double",
        "model_files": [str(checkpoint)],
        "targeted": True,
        "coverage": segments,
        "warnings": [
            "Aria-AMT checkpoint is used only for targeted quality review; "
            "its published model-data terms are non-commercial."
        ],
    }


def _piano_review_regions(audio_path: Path, events: list[dict], metric: dict) -> list[dict]:
    import numpy as np
    import soundfile as sf

    notes = [event for event in events if event.get("source") == "piano"]
    if not notes:
        return []
    with sf.SoundFile(str(audio_path)) as source:
        duration = len(source) / float(source.samplerate)
        sample_rate = int(source.samplerate)
        global_rms = float(metric.get("rms", 0.0))
        if global_rms <= 0:
            # Sample a bounded amount only for routing, not transcription.
            position = source.tell()
            source.seek(0)
            probe = source.read(min(len(source), sample_rate * 45), dtype="float32", always_2d=True)
            source.seek(position)
            global_rms = float(np.sqrt(np.mean(probe * probe) + 1e-12)) if len(probe) else 0.0
        if global_rms < 1e-5:
            return []
        spectral = float(metric.get("spectral_confidence", metric.get("confidence_prior", .55)))
        leakage = float(metric.get("leakage", .45))
        window = 12.0
        candidates = []
        for start in [i * window for i in range(max(1, math.ceil(duration / window)))]:
            end = min(duration, start + window)
            region_notes = [
                event for event in notes
                if float(event["start"]) < end and float(event["end"]) > start
            ]
            source.seek(round(start * sample_rate))
            chunk = source.read(
                max(1, round((end - start) * sample_rate)),
                dtype="float32", always_2d=True,
            )
            local_rms = float(np.sqrt(np.mean(chunk * chunk) + 1e-12)) if len(chunk) else 0.0
            active = local_rms >= max(1e-5, global_rms * .18)
            if not active:
                continue
            density = len(region_notes) / max(.25, end - start)
            sparse = 1.0 if not region_notes else max(0.0, min(1.0, (.40 - density) / .40))
            weak_notes = (
                1.0 - sum(float(event.get("confidence", .5)) for event in region_notes) / len(region_notes)
                if region_notes else 1.0
            )
            score = (
                .38 * (1.0 - max(0.0, min(1.0, spectral))) +
                .24 * max(0.0, min(1.0, leakage)) +
                .24 * sparse + .14 * weak_notes
            )
            if score >= .27:
                candidates.append({
                    "start": start, "end": end, "score": round(score, 4),
                    "reasons": ["piano_second_opinion"],
                })
    return sorted(
        sorted(candidates, key=lambda item: (-item["score"], item["start"]))[:3],
        key=lambda item: item["start"],
    )


def _patch_providers(providers) -> None:
    providers._legacy.PROVIDERS["drumsep"] = (
        lambda payload, report: _drumsep_provider(providers._legacy, payload, report)
    )
    providers._legacy.DISTRIBUTIONS["drumsep"] = "mdxnet-infer"
    providers._legacy.PROVIDERS["aria_amt"] = (
        lambda payload, report: _aria_amt_provider(providers._legacy, payload, report)
    )
    providers._legacy.DISTRIBUTIONS["aria_amt"] = "aria-amt"


def _patch_pipeline(pipeline) -> None:
    original_stage = pipeline.BandPipeline._stage

    def stage(self, client, job, provider, audio, payload, cancel, report, warnings,
              settings, hardware):
        result = original_stage(
            self, client, job, provider, audio, payload, cancel, report, warnings,
            settings, hardware,
        )
        if provider == "demucs":
            self._beta9_stem_metrics = result.get("metrics", {})
            return result

        quality_pass = bool(
            settings.cross_check and settings.device != "cpu" and hardware.cuda
        )
        if not quality_pass:
            return result
        metrics = getattr(self, "_beta9_stem_metrics", {})

        if provider == "transkun" and result.get("events"):
            regions = _piano_review_regions(
                Path(audio), result.get("events", []), metrics.get("piano", {})
            )
            if regions:
                try:
                    extra = original_stage(
                        self, client, job, "aria_amt", audio, {"segments": regions},
                        cancel, report, warnings, settings, hardware,
                    )
                except Exception as exc:
                    if isinstance(exc, pipeline.Cancelled):
                        raise
                    warnings.append(f"Targeted Aria-AMT piano review unavailable: {exc}")
                    result.setdefault("warnings", []).append(
                        "Targeted Aria-AMT review unavailable; Transkun remains authoritative."
                    )
                else:
                    result.setdefault("events", []).extend(extra.get("events", []))
                    warnings.extend(extra.get("warnings", []))
                    result.setdefault("provenance", {})["aria_amt_review"] = {
                        "regions": regions,
                        "events": len(extra.get("events", [])),
                        "provider": extra.get("provenance", {}),
                    }

        if provider in {"adtof", "drums_dsp"}:
            drum_metric = metrics.get("drums", {})
            if float(drum_metric.get("rms", 1.0)) >= 1e-5:
                try:
                    extra = original_stage(
                        self, client, job, "drumsep", audio, {},
                        cancel, report, warnings, settings, hardware,
                    )
                except Exception as exc:
                    if isinstance(exc, pipeline.Cancelled):
                        raise
                    warnings.append(f"DrumSep kit evidence unavailable: {exc}")
                    result.setdefault("warnings", []).append(
                        "DrumSep unavailable; existing drum transcription retained."
                    )
                else:
                    result.setdefault("events", []).extend(extra.get("events", []))
                    warnings.extend(extra.get("warnings", []))
                    result.setdefault("provenance", {})["drumsep_evidence"] = {
                        "events": len(extra.get("events", [])),
                        "provider": extra.get("provenance", {}),
                    }
        return result

    pipeline.BandPipeline._stage = stage


_ENGINE_PRIOR = {
    "piano": {"transkun": 1.00, "aria_amt": .90, "basic_pitch": .66,
              "muscriptor": .68, "mr_mt3": .68, "mr_mt3_repair": .74},
    "drums": {"adtof": 1.00, "drumsep": .92, "drums_dsp": .62,
              "mr_mt3": .70, "mr_mt3_repair": .76},
    "bass": {"torchcrepe": 1.00, "basic_pitch": .84, "muscriptor": .64},
    "vocals": {"torchcrepe": 1.00, "basic_pitch": .82, "muscriptor": .62},
    "guitar": {"basic_pitch": .84, "muscriptor": .76, "mr_mt3": .70,
               "mr_mt3_repair": .76},
    "other": {"basic_pitch": .80, "muscriptor": .74, "mr_mt3": .68,
              "mr_mt3_repair": .74},
}


def _engine_prior(event) -> float:
    return _ENGINE_PRIOR.get(event.source, {}).get(event.engine, .70)


def _dedupe_independent(fusion, events):
    kept = []
    rejected = []
    buckets = defaultdict(list)
    for event in sorted(events, key=lambda item: (item.start, item.source, item.pitch or -1)):
        key = (event.source, event.role if event.source == "drums" else event.pitch)
        duplicate_index = None
        for index in reversed(buckets[key][-8:]):
            other = kept[index]
            if event.start - other.start > .085:
                break
            if other.engine == event.engine:
                continue
            if abs(event.start - other.start) <= .070 and (
                min(event.end, other.end) > max(event.start, other.start) - .025
            ):
                duplicate_index = index
                break
        if duplicate_index is None:
            buckets[key].append(len(kept))
            kept.append(event)
            continue
        other = kept[duplicate_index]
        winner, loser = (
            (event, other) if event.confidence > other.confidence else (other, event)
        )
        supporters = sorted({
            other.engine, event.engine,
            *winner.evidence.get("beta9_support_engines", []),
        })
        merged = replace(
            winner,
            confidence=min(.99, max(winner.confidence, loser.confidence) +
                           .05 * (1 - max(winner.confidence, loser.confidence))),
            end=max(winner.end, loser.end),
            tags=winner.tags | loser.tags | {"independent_agreement"},
            evidence={
                **winner.evidence,
                "beta9_support_engines": supporters,
                "independent_duplicate_event": loser.event_id,
            },
        )
        kept[duplicate_index] = merged
        rejected.append(fusion.reject(loser, "independent_engine_duplicate"))
    return sorted(kept, key=lambda item: (item.start, item.source, item.pitch or -1)), rejected


def _patch_fusion(fusion, pipeline) -> None:
    original_fuse = fusion.fuse
    original_build_master = fusion.build_master

    def fuse(primary, reference, beat_map, stem_metrics=None):
        primary_index = fusion._index(primary)
        strengthened = []
        for event in primary:
            support = fusion.agreements(event, primary_index)
            by_engine = {}
            for other in support:
                if other.engine == event.engine:
                    continue
                current = by_engine.get(other.engine)
                if current is None or other.confidence > current.confidence:
                    by_engine[other.engine] = other
            confidence = event.confidence
            evidence = dict(event.evidence)
            if by_engine:
                support_value = sum(
                    other.confidence * _engine_prior(other)
                    for other in by_engine.values()
                )
                confidence += (1 - confidence) * min(.32, .10 + .10 * support_value)
                evidence["beta9_support_engines"] = sorted(by_engine)
            # Tiny reliability nudge only; measured/specialist confidence remains dominant.
            confidence += (_engine_prior(event) - .70) * .055
            strengthened.append(replace(
                event, confidence=max(0.0, min(.98, confidence)), evidence=evidence
            ))

        fused_events, removed = original_fuse(
            strengthened, reference, beat_map, stem_metrics
        )
        adjusted = []
        for event in fused_events:
            confidence = event.confidence
            evidence = dict(event.evidence)
            if event.source == "drums" and beat_map.beats and beat_map.confidence >= .60:
                nearest = min(beat_map.beats, key=lambda beat: abs(beat - event.start))
                distance = abs(nearest - event.start)
                evidence["nearest_beat_distance"] = distance
                if distance <= .055:
                    confidence += .035 * (1 - confidence)
            adjusted.append(replace(
                event, confidence=min(.99, confidence), evidence=evidence
            ))
        adjusted, duplicates = _dedupe_independent(fusion, adjusted)
        removed.extend(duplicates)
        return adjusted, removed

    def build_master(digest, duration, beats, primary, reference, provenance, warnings):
        master = original_build_master(
            digest, duration, beats, primary, reference, provenance, warnings
        )
        metrics = provenance.get("stem_metrics", {})
        presence = {}
        retained = []
        for source in ("piano", "guitar", "bass", "drums", "other"):
            metric = metrics.get(source, {})
            rms = float(metric.get("rms", 1.0 if not metric else 0.0))
            spectral = float(metric.get(
                "spectral_confidence", metric.get("confidence_prior", .50)
            ))
            leakage = float(metric.get("leakage", .50))
            source_events = [event for event in master.events if event.source == source]
            ref_events = [event for event in reference if event.source == source]
            event_rate_target = max(4.0, duration / 12.0)
            event_score = min(1.0, len(source_events) / event_rate_target)
            reference_score = min(1.0, len(ref_events) / max(2.0, duration / 30.0))
            energy_score = max(
                0.0, min(1.0, (math.log10(max(rms, 1e-8)) + 5.0) / 2.5)
            )
            score = max(0.0, min(
                1.0,
                .35 * energy_score + .30 * event_score + .20 * reference_score +
                .15 * max(0.0, min(1.0, spectral)) - .10 * max(0.0, min(1.0, leakage)),
            ))
            absent = (
                (rms < 1e-5 and len(source_events) < 2 and not ref_events) or
                (score < .20 and len(source_events) < 3 and not ref_events)
            )
            state = "absent" if absent else "uncertain" if score < .45 else "present"
            presence[source] = {
                "state": state, "score": round(score, 4), "rms": rms,
                "event_count": len(source_events), "reference_count": len(ref_events),
                "spectral_confidence": spectral, "leakage": leakage,
            }
            for event in source_events:
                if absent:
                    master.rejected.append(fusion.reject(event, "instrument_absent"))
                elif state == "uncertain":
                    retained.append(replace(
                        event,
                        confidence=max(0.0, event.confidence * .94),
                        tags=event.tags | {"instrument_presence_uncertain"},
                        evidence={**event.evidence, "instrument_presence_score": score},
                    ))
                else:
                    retained.append(event)
        untouched = [
            event for event in master.events
            if event.source not in {"piano", "guitar", "bass", "drums", "other"}
        ]
        master.events = sorted(untouched + retained, key=lambda event: (event.start, event.source))
        master.provenance["instrument_presence"] = presence
        absent_names = [name for name, value in presence.items() if value["state"] == "absent"]
        if absent_names:
            master.warnings.append(
                "Suppressed likely-absent instrument parts: " + ", ".join(absent_names) + "."
            )
        return master

    fusion.fuse = fuse
    fusion.build_master = build_master
    # pipeline imported build_master by value; update that binding too.
    pipeline.build_master = build_master


def apply_beta9() -> None:
    global _APPLIED
    if _APPLIED:
        return
    from . import fusion, pipeline, providers, runtime

    _patch_runtimes(runtime)
    _patch_providers(providers)
    _patch_pipeline(pipeline)
    _patch_fusion(fusion, pipeline)
    _APPLIED = True
