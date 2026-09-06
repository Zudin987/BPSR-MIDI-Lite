"""Real inference adapters, imported only in workers. No models are vendored."""
from __future__ import annotations

import importlib.metadata
import inspect
import math
import os
import shutil
import statistics
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .music import MusicEvent
from .progress import ProgressEvent, format_elapsed
from .runtime import HQ_MODEL, PROVIDER_MODEL
from .storage import atomic_json, file_hash

GM_DRUMS = {
    35: "KICK", 36: "KICK", 37: "SNARE", 38: "SNARE", 40: "SNARE",
    42: "CLOSED_HAT", 44: "CLOSED_HAT", 46: "OPEN_HAT",
    49: "CRASH", 52: "CRASH", 55: "CRASH", 57: "CRASH",
    51: "RIDE", 53: "RIDE", 59: "RIDE",
    41: "TOM", 43: "TOM", 45: "TOM", 47: "TOM", 48: "TOM", 50: "TOM",
}

MR_MT3_SHA256 = "b8a3807ed265059abd25ad7f68142c06c35e8f6144dcaa45bd55946a3745398f"


def _report(report, message: str, *, activity: str = "processing",
            stage_fraction: float | None = None, indeterminate: bool = True) -> None:
    report(ProgressEvent(message, activity=activity, stage_fraction=stage_fraction,
                         indeterminate=indeterminate))


def device_for(requested: str, *, allow_cpu_fallback: bool = True) -> str:
    import torch
    if requested == "cpu":
        return "cpu"
    reason = "PyTorch did not find a usable NVIDIA CUDA device"
    try:
        if torch.cuda.is_available():
            # An installed CUDA wheel may predate the GPU architecture. Test a
            # real kernel instead of treating nvidia-smi as sufficient.
            (torch.ones(8, device="cuda") * 2).sum().item()
            torch.cuda.synchronize()
            return "cuda"
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
    if allow_cpu_fallback:
        return "cpu"
    raise RuntimeError("CUDA acceleration could not start. " + reason)


@contextmanager
def _working_heartbeat(report, message: str, *, activity: str,
                       stage_fraction: float, interval: float = 20.0):
    """Report truthful liveness while a third-party blocking call is active."""
    _report(report, message, activity=activity, stage_fraction=stage_fraction)
    stopped = threading.Event()
    started = time.monotonic()

    def pulse() -> None:
        while not stopped.wait(interval):
            elapsed = format_elapsed(time.monotonic() - started)
            _report(
                report,
                f"{message.rstrip('.… ')} — still working ({elapsed} in this step)…",
                activity=activity,
                stage_fraction=stage_fraction,
            )

    thread = threading.Thread(target=pulse, daemon=True, name="studio-provider-progress")
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=min(1.0, interval + 0.1))


def _audio(path):
    import soundfile as sf
    audio, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return audio, sr


def _events_from_midi(path: Path, engine: str, source: str | None = None) -> list[dict]:
    import mido
    programs, active, events, clock = {}, {}, [], 0.0
    for message in mido.MidiFile(str(path)):
        clock += message.time
        if message.type == "program_change":
            programs[message.channel] = message.program
        if message.type == "note_on" and message.velocity:
            key = (message.channel, message.note)
            active.setdefault(key, []).append((clock, message.velocity, programs.get(message.channel, 0)))
        elif message.type == "note_off" or (message.type == "note_on" and not message.velocity):
            key = (message.channel, message.note)
            if not active.get(key):
                continue
            start, velocity, program = active[key].pop(0)
            if clock <= start:
                continue
            part = source or ("drums" if message.channel == 9 else "guitar" if 24 <= program <= 31
                              else "bass" if 32 <= program <= 39 else "piano" if program <= 7 else "other")
            role = (GM_DRUMS.get(message.note, "PERCUSSION") if part == "drums" else
                    "BASS" if part == "bass" else "HARMONY")
            event = MusicEvent(part, role, start, clock, None if part == "drums" else message.note,
                               velocity, 0.72 if engine == "transkun" else 0.60, engine,
                               {"confidence_prior"}, evidence={"gm_pitch": message.note, "program": program,
                                                              "confidence_kind": "engine prior; MIDI has no posterior"})
            events.append(event.to_dict())
    return events


def basic_pitch(payload: dict, report) -> dict:
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import predict
    from studio_youtube import _basic_pitch_model
    source = payload["source"]
    # Bass limits do not share the broad piano/song range. Keep the original
    # register here: BPSR fitting belongs after the musical map.
    limits = {"bass": (30.87, 246.94, 100.0), "guitar": (73.42, 1318.51, 85.0),
              "vocals": (65.41, 1396.91, 90.0), "piano": (27.5, 4186.01, 70.0),
              "other": (65.41, 2093.0, 120.0)}
    low, high, minimum = limits[source]
    _report(report, "Listening for " + source + " notes with the bundled model…",
            activity="cpu", stage_fraction=0.12)
    _, _, notes = predict(Path(payload["audio"]), _basic_pitch_model(),
                          onset_threshold=0.50 if source == "bass" else 0.55,
                          frame_threshold=0.30, minimum_note_length=minimum,
                          minimum_frequency=low, maximum_frequency=high,
                          multiple_pitch_bends=False, melodia_trick=source != "bass")
    events = []
    for start, end, pitch, strength, *_ in notes:
        if float(end) <= float(start):
            continue
        confidence = max(0.0, min(1.0, float(strength)))
        events.append(MusicEvent(source, "MAIN_MELODY" if source == "vocals" else "BASS" if source == "bass" else "HARMONY",
                                 float(start), float(end), int(pitch), max(1, min(127, round(40 + confidence * 75))),
                                 confidence, "basic_pitch", evidence={"confidence_kind": "activation amplitude"}).to_dict())
    return {"events": events, "device": "cpu", "model_files": [str(ICASSP_2022_MODEL_PATH)]}


def torchcrepe_pitch(payload: dict, report) -> dict:
    """Monophonic pitch evidence for vocal/bass specialist validation."""
    import numpy as np
    import torch
    import torchaudio.functional as audio_functional
    import torchcrepe

    source = payload["source"]
    if source not in {"vocals", "bass"}:
        raise ValueError("torchcrepe validation is only defined for vocals and bass")
    device = device_for(payload.get("device", "auto"))
    audio, sample_rate = _audio(payload["audio"])
    waveform = torch.from_numpy(audio.mean(axis=1).copy())
    if sample_rate != 16000:
        waveform = audio_functional.resample(waveform, sample_rate, 16000)
        sample_rate = 16000
    peak = waveform.abs().max()
    if float(peak) > 1:
        waveform = waveform / peak
    hop_length = 160
    low, high = ((65.41, 1396.91) if source == "vocals" else (30.87, 246.94))
    variant = "full" if device == "cuda" else "tiny"
    with _working_heartbeat(
        report,
        f"Validating {source} pitch evidence with torchcrepe on {device.upper()}…",
        activity=device,
        stage_fraction=0.48,
    ):
        with torch.inference_mode():
            pitch, periodicity = torchcrepe.predict(
                waveform[None].to(device), sample_rate, hop_length, low, high,
                variant, batch_size=2048, device=device, return_periodicity=True,
            )
    hz = pitch[0].detach().cpu().numpy().astype("float64")
    periodicity = periodicity[0].detach().cpu().numpy().astype("float64")
    samples = waveform.detach().cpu().numpy().astype("float64")

    # Periodicity is independent evidence. Combine it with an actual local
    # energy measurement so silence and residual bleed do not become notes.
    frame_radius = sample_rate // 50
    midi = np.full(len(hz), np.nan)
    reliable = np.zeros(len(hz), dtype=bool)
    for index, frequency in enumerate(hz):
        center = index * hop_length
        frame = samples[max(0, center-frame_radius):min(len(samples), center+frame_radius)]
        rms = math.sqrt(float(np.mean(frame**2))) if len(frame) else 0.0
        if (math.isfinite(frequency) and low <= frequency <= high and
                periodicity[index] >= 0.48 and rms >= 10 ** (-58 / 20)):
            midi[index] = 69 + 12 * math.log2(frequency / 440)
            reliable[index] = True
    # A five-frame median removes vibrato-induced semitone flicker without
    # moving onsets or pretending the contour is polyphonic.
    smoothed = midi.copy()
    for index in np.flatnonzero(reliable):
        local = midi[max(0, index-2):index+3]
        local = local[np.isfinite(local)]
        if len(local):
            smoothed[index] = float(np.median(local))

    events = []
    active_pitch = None
    active_start = 0

    def finish(end_index: int) -> None:
        nonlocal active_pitch, active_start
        if active_pitch is None:
            return
        start = active_start * hop_length / sample_rate
        end = max(start + hop_length / sample_rate, end_index * hop_length / sample_rate)
        frames = periodicity[active_start:end_index]
        confidence = float(np.mean(frames)) if len(frames) else 0.0
        if end-start >= (0.07 if source == "vocals" else 0.09) and confidence >= 0.48:
            events.append(MusicEvent(
                source,
                "MAIN_MELODY" if source == "vocals" else "BASS",
                start, end, int(active_pitch), max(1, min(127, round(35 + confidence * 80))),
                min(0.99, confidence), "torchcrepe", {"pitch_validation"},
                evidence={"confidence_kind": "torchcrepe periodicity plus local stem energy",
                          "mean_periodicity": confidence, "model_variant": variant},
            ).to_dict())
        active_pitch = None

    for index in range(len(smoothed)):
        detected = int(round(smoothed[index])) if reliable[index] else None
        if active_pitch is None and detected is not None:
            active_pitch, active_start = detected, index
        elif active_pitch is not None and detected != active_pitch:
            finish(index)
            if detected is not None:
                active_pitch, active_start = detected, index
    finish(len(smoothed))
    assets = list((Path(torchcrepe.__file__).parent / "assets").glob("*.pth"))
    return {"events": events, "device": device, "model": variant,
            "model_files": [str(path) for path in assets]}


def _resolve_spectral_ownership(waveform, six, fine, sample_rate: int, report):
    """Allocate mixture bins once across stems and return measured evidence."""
    import torch

    names = ("vocals", "piano", "guitar", "bass", "drums", "other")
    output = torch.zeros((len(names), *waveform.shape), dtype=torch.float32)
    accumulators = {
        name: {"owned": 0.0, "purity": 0.0, "agreement": 0.0, "agreement_weight": 0.0}
        for name in names
    }
    n_fft, hop = 1024, 256
    window = torch.hann_window(n_fft)
    chunk_frames = sample_rate * 10
    _report(report, "Resolving cross-stem leakage and measuring spectral ownership on CPU…",
            activity="cpu", stage_fraction=0.86)
    for start in range(0, waveform.shape[-1], chunk_frames):
        end = min(waveform.shape[-1], start + chunk_frames)
        analysis_start = max(0, start - 2*n_fft)
        analysis_end = min(waveform.shape[-1], end + 2*n_fft)
        length = analysis_end-analysis_start
        mixture_spec = torch.stft(waveform[:, analysis_start:analysis_end], n_fft,
                                  hop_length=hop, window=window, pad_mode="constant",
                                  return_complex=True)
        six_audio = torch.stack([six[name][:, analysis_start:analysis_end] for name in names])
        six_shape = six_audio.shape[:2]
        packed_six = torch.stft(six_audio.reshape(-1, length), n_fft, hop_length=hop,
                                window=window, pad_mode="constant", return_complex=True)
        six_stack = packed_six.reshape(*six_shape, *packed_six.shape[-2:])
        six_specs = {name: six_stack[index] for index, name in enumerate(names)}
        fine_specs = {}
        if fine:
            fine_names = tuple(fine)
            fine_audio = torch.stack([fine[name][:, analysis_start:analysis_end] for name in fine_names])
            fine_shape = fine_audio.shape[:2]
            packed_fine = torch.stft(fine_audio.reshape(-1, length), n_fft, hop_length=hop,
                                     window=window, pad_mode="constant", return_complex=True)
            fine_stack = packed_fine.reshape(*fine_shape, *packed_fine.shape[-2:])
            fine_specs = {name: fine_stack[index] for index, name in enumerate(fine_names)}
        magnitudes = {}
        for name in names:
            base = six_specs[name].abs()
            if name in fine_specs and name != "other":
                base = (base + fine_specs[name].abs()) * 0.5
            magnitudes[name] = base
        if "other" in fine_specs:
            group = ("piano", "guitar", "other")
            group_sum = sum((six_specs[name].abs() for name in group)) + 1e-8
            group_target = fine_specs["other"].abs()
            for name in group:
                adjusted = six_specs[name].abs() * group_target / group_sum
                magnitudes[name] = 0.65 * magnitudes[name] + 0.35 * adjusted
        stack = torch.stack([magnitudes[name] for name in names])
        weights = stack.square()
        masks = weights / (weights.sum(dim=0, keepdim=True) + 1e-10)
        owned_specs = mixture_spec.unsqueeze(0) * masks
        resolved = torch.istft(owned_specs.reshape(-1, *owned_specs.shape[-2:]), n_fft,
                               hop_length=hop, window=window, length=length)
        resolved = resolved.reshape(len(names), waveform.shape[0], length)
        crop_start = start-analysis_start
        output[:, :, start:end] = resolved[:, :, crop_start:crop_start+(end-start)]
        mixture_power = mixture_spec.abs().square()
        for stem_index, name in enumerate(names):
            assigned = mixture_power * masks[stem_index]
            owned = float(assigned.sum())
            accumulators[name]["owned"] += owned
            accumulators[name]["purity"] += float((assigned * masks[stem_index]).sum())
            comparison = fine_specs.get(name)
            if name in {"piano", "guitar", "other"} and "other" in fine_specs:
                comparison = fine_specs["other"]
                first = sum((six_specs[item].abs() for item in ("piano", "guitar", "other")))
            else:
                first = six_specs[name].abs()
            if comparison is not None:
                second = comparison.abs()
                agreement = 2 * torch.minimum(first, second) / (first + second + 1e-8)
                agreement_weight = mixture_power
                accumulators[name]["agreement"] += float((agreement * agreement_weight).sum())
                accumulators[name]["agreement_weight"] += float(agreement_weight.sum())
    metrics = {}
    for stem_index, name in enumerate(names):
        values = accumulators[name]
        purity = max(0.0, min(1.0, values["purity"] / max(1e-12, values["owned"])))
        agreement = (max(0.0, min(1.0, values["agreement"] / values["agreement_weight"]))
                     if values["agreement_weight"] else None)
        spectral_confidence = max(0.0, min(1.0, 0.20 + 0.55 * purity + 0.25 *
                                           (agreement if agreement is not None else purity)))
        samples = output[stem_index]
        metrics[name] = {
            "rms": float(samples.to(torch.float64).square().mean().sqrt()),
            "spectral_purity": purity,
            "leakage": 1-purity,
            "ensemble_agreement": agreement,
            "spectral_confidence": spectral_confidence,
            "confidence_prior": spectral_confidence,
            "confidence_kind": "measured mixture-bin ownership; heuristic, not probability",
        }
    return output, metrics


def demucs(payload: dict, report) -> dict:
    import soundfile as sf
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model
    device = device_for(payload.get("device", "auto"))
    ensemble_requested = bool(payload.get("ensemble", True))
    ensemble = ensemble_requested and device == "cuda"
    torch.manual_seed(0)
    checkpoint_root = Path(os.environ["TORCH_HOME"]) / "hub" / "checkpoints"
    cached_weights = list(checkpoint_root.glob("*.th"))
    model_label = "htdemucs_6s + htdemucs_ft separation ensemble" if ensemble else "htdemucs_6s separator"
    with _working_heartbeat(
        report,
        (f"Loading the {model_label}…" if cached_weights else f"Downloading the {model_label} models…"),
        activity=device if cached_weights else "download", stage_fraction=0.05,
    ):
        model = get_model("htdemucs_6s")
        model.eval()
        fine_model = get_model("htdemucs_ft") if ensemble else None
        if fine_model is not None:
            fine_model.eval()
    audio, sr = _audio(payload["audio"])
    if sr != model.samplerate or audio.shape[1] != model.audio_channels:
        raise ValueError("Separator expects the prepared stereo 44.1 kHz audio")
    waveform = torch.from_numpy(audio.T.copy())
    ref = waveform.mean(0)
    mean, scale = ref.mean(), ref.std()
    fine = {}
    if float(scale) < 1e-8:
        six = {name: torch.zeros_like(waveform) for name in model.sources}
    else:
        normalized = (waveform - mean) / scale
        with _working_heartbeat(
            report, f"Separating six instrument stems with htdemucs_6s on {device.upper()}…",
            activity=device, stage_fraction=0.18,
        ):
            with torch.inference_mode():
                separated = apply_model(model, normalized[None], device=device, shifts=1, split=True,
                                        overlap=0.25, progress=False, num_workers=0)[0]
        six = {name: tensor.cpu() * scale for name, tensor in zip(model.sources, separated)}
        if fine_model is not None:
            with _working_heartbeat(
                report, f"Running fine-tuned four-stem separation evidence on {device.upper()}…",
                activity=device, stage_fraction=0.52,
            ):
                with torch.inference_mode():
                    fine_separated = apply_model(fine_model, normalized[None], device=device, shifts=1,
                                                 split=True, overlap=0.25, progress=False, num_workers=0)[0]
            fine = {name: tensor.cpu() * scale for name, tensor in zip(fine_model.sources, fine_separated)}
    resolved, metrics = _resolve_spectral_ownership(waveform, six, fine, sr, report)
    target = Path(payload["output"])
    target.mkdir(parents=True, exist_ok=True)
    stems = {}
    for name, tensor in zip(("vocals", "piano", "guitar", "bass", "drums", "other"), resolved):
        path = target / (name + ".wav")
        samples = tensor.numpy().T
        sf.write(str(path), samples, sr, subtype="FLOAT")
        stems[name] = str(path)
    if set(stems) != {"vocals", "piano", "guitar", "bass", "drums", "other"}:
        raise ValueError("Demucs did not return the expected six stems")
    weights = list(checkpoint_root.glob("*.th"))
    warnings = []
    if ensemble_requested and not ensemble:
        warnings.append("The dual Demucs ensemble needs working CUDA; htdemucs_6s plus spectral ownership was used on CPU.")
    return {"stems": stems, "metrics": metrics, "device": device,
            "model": "htdemucs_6s+htdemucs_ft" if ensemble else "htdemucs_6s",
            "ensemble": ensemble, "warnings": warnings, "model_files": [str(x) for x in weights]}


def roformer(payload: dict, report) -> dict:
    import numpy as np
    import soundfile as sf
    from audio_separator.separator import Separator
    device = device_for(payload.get("device", "auto"))
    if device == "cpu":
        # audio-separator selects CUDA automatically; explicitly hide it before
        # constructing the provider when CPU was requested or the probe failed.
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
    target = Path(payload["output"])
    target.mkdir(parents=True, exist_ok=True)
    models = Path(payload["models"]) / "roformer"
    models.mkdir(parents=True, exist_ok=True)
    model_cached = (models / HQ_MODEL).is_file()
    _report(
        report,
        "Loading the HQ vocal separator…" if model_cached else "Downloading the HQ vocal separator model…",
        activity=device if model_cached else "download",
        stage_fraction=0.05,
    )
    separator = Separator(model_file_dir=str(models), output_dir=str(target), output_format="WAV",
                          sample_rate=44100, use_soundfile=True, normalization_threshold=0.99,
                          # In this version the RoFormer overlap parameter is
                          # the step in seconds, not a divisor: 4 gives overlap
                          # between the selected checkpoint's 8-second windows.
                          mdxc_params={"segment_size": 256, "override_model_segment_size": False, "batch_size": 1, "overlap": 4})
    separator.load_model(model_filename=HQ_MODEL)
    _report(report, f"Separating HQ vocals on {device.upper()}…", activity=device, stage_fraction=0.20)
    samples, sample_rate = _audio(payload["audio"])
    frames = len(samples)
    config = separator.model_instance.model_data_cfgdict
    minimum_frames = int(config.audio.hop_length * (config.inference.dim_t-1))
    working_audio = payload["audio"]
    padded = target / "_hq_model_input.wav"
    previous_directory = Path.cwd()
    try:
        # Upstream's overlap-add assumes at least one whole model window.
        # Add trailing context for short clips, preserving sample zero and
        # restoring the SAME original end boundary on both returned stems.
        if frames < minimum_frames:
            sf.write(str(padded), np.pad(samples, ((0, minimum_frames-frames), (0, 0))), sample_rate, subtype="FLOAT")
            working_audio = str(padded)
        # audio-separator 0.30.2's soundfile writer omits output_dir even though
        # the API returns relative paths. Isolate that upstream behavior inside
        # the worker's own output directory.
        os.chdir(target)
        outputs = separator.separate(working_audio, custom_output_names={"Vocals": "hq_vocals", "Instrumental": "hq_instrumental"})
    finally:
        os.chdir(previous_directory)
        padded.unlink(missing_ok=True)
    paths = [Path(x) if Path(x).is_absolute() else target / x for x in outputs]
    vocals = next((p for p in paths if "hq_vocals" in p.name), None)
    instrumental = next((p for p in paths if "hq_instrumental" in p.name), None)
    if not vocals or not instrumental or not vocals.exists() or not instrumental.exists():
        raise ValueError("HQ separator did not return vocals and instrumental audio")
    for path in (vocals, instrumental):
        audio, sr = _audio(path)
        if sr != sample_rate or len(audio) < frames:
            raise ValueError("HQ separator changed the source timeline")
        if len(audio) > frames:
            sf.write(str(path), audio[:frames], sr, subtype="FLOAT")
    # A vocal RoFormer is not a six-stem model. The orchestrator runs Demucs on
    # this instrumental file, then uses this cleaner vocal stem for melody.
    return {"vocals": str(vocals), "instrumental": str(instrumental), "device": device,
            "model_files": [str(p) for p in models.iterdir() if p.is_file()]}


def beat_this(payload: dict, report) -> dict:
    from beat_this.inference import File2Beats
    device = device_for(payload.get("device", "auto"))
    checkpoint = Path(os.environ["TORCH_HOME"]) / "hub" / "checkpoints" / "beat_this-final0.ckpt"
    _report(
        report,
        "Loading the beat and timing model…" if checkpoint.is_file() else
        "Downloading the beat and timing model…",
        activity=device if checkpoint.is_file() else "download",
        stage_fraction=0.05,
    )
    tracker = File2Beats(checkpoint_path="final0", device=device, dbn=False)
    _report(report, f"Detecting the song's beat and downbeats on {device.upper()}…",
            activity=device, stage_fraction=0.20)
    beats, downbeats = tracker(payload["audio"])
    intervals = [float(b-a) for a, b in zip(beats, beats[1:]) if b > a]
    bpm = 60 / statistics.median(intervals) if intervals else None
    path = Path(os.environ["TORCH_HOME"]) / "hub" / "checkpoints" / "beat_this-final0.ckpt"
    return {"beat_map": {"bpm": bpm, "beats": [float(x) for x in beats],
                          "downbeats": [float(x) for x in downbeats], "engine": "beat_this",
                          "confidence": 0.8 if len(beats) > 3 else 0.2},
            "device": device, "model_files": [str(path)] if path.exists() else []}


def transkun(payload: dict, report) -> dict:
    import moduleconf
    import numpy as np
    import soxr
    import torch
    import transkun as package
    from transkun.Data import writeMidi
    device = device_for(payload.get("device", "auto"))
    root = Path(package.__file__).parent / "pretrained"
    weight, config = root / "2.0.pt", root / "2.0.conf"
    _report(report, "Loading the Transkun piano specialist from the installed runtime…",
            activity=device, stage_fraction=0.10)
    configuration = moduleconf.parseFromFile(str(config))["Model"]
    model = configuration.module.TransKun(conf=configuration.config).to(device)
    checkpoint = torch.load(str(weight), map_location=device, weights_only=False)
    model.load_state_dict(checkpoint.get("best_state_dict", checkpoint.get("state_dict")), strict=True)
    model.eval()
    # Read the prepared WAV directly: upstream's CLI uses from_mp3 and assumes
    # 16-bit scaling, which is inappropriate for our floating-point WAVs.
    audio, sr = _audio(payload["audio"])
    if sr != model.fs:
        audio = soxr.resample(audio, sr, model.fs)
    _report(report, f"Transcribing Piano on {device.upper()}…", activity=device, stage_fraction=0.20)
    with torch.inference_mode():
        notes = model.transcribe(torch.from_numpy(np.asarray(audio, dtype="float32")).to(device),
                                 stepInSecond=None, segmentSizeInSecond=None, discardSecondHalf=False)
    target = Path(payload["output"]) / "transkun.mid"
    target.parent.mkdir(parents=True, exist_ok=True)
    writeMidi(notes).write(str(target))
    return {"events": _events_from_midi(target, "transkun", "piano"), "device": device,
            "model_files": [str(weight), str(config)]}


def _muscriptor_source(instrument: str) -> str:
    """Map MuScriptor's MT3_FULL_PLUS instrument groups onto BPSR parts."""
    name = instrument.casefold().replace(" ", "_")
    if name in {"voice", "vocals", "singing_voice"}:
        return "vocals"
    if "piano" in name or name == "organ":
        return "piano"
    if "guitar" in name:
        return "guitar"
    if "bass" in name:
        return "bass"
    if name == "drums":
        return "drums"
    return "other"


def muscriptor(payload: dict, report) -> dict:
    """Run one global transcription pass as independent fusion evidence."""
    from muscriptor.events import NoteEndEvent, ProgressEvent as MuScriptorProgress
    from muscriptor.transcription_model import TranscriptionModel

    variant = str(payload.get("model", "medium")).casefold()
    if variant not in {"medium", "large"}:
        raise ValueError("MuScriptor model must be Medium or Large")
    device = device_for(payload.get("device", "auto"), allow_cpu_fallback=False)
    override = os.environ.get("BPSR_MUSCRIPTOR_WEIGHTS", "").strip()
    source = override or variant
    hf_home = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface")))
    cache = hf_home / "hub" / f"models--MuScriptor--muscriptor-{variant}"
    cached = bool(override and Path(override).is_file()) or any(cache.glob("snapshots/*/model.safetensors"))
    action = "Loading cached" if cached else "Downloading gated"
    with _working_heartbeat(
        report,
        f"{action} MuScriptor {variant.title()} global model…",
        activity=device if cached else "download",
        stage_fraction=0.05,
    ):
        model = TranscriptionModel.load_model(weights_path=source, device=device)

    _report(
        report,
        f"Starting MuScriptor {variant.title()} full-song evidence pass on {device.upper()}…",
        activity=device,
        stage_fraction=0.15,
    )
    events = []
    for item in model.transcribe(payload["audio"], batch_size=1, prelude_forcing=True):
        if isinstance(item, MuScriptorProgress):
            fraction = item.completed / max(1, item.total)
            _report(
                report,
                f"MuScriptor global evidence on {device.upper()} · chunk {item.completed}/{item.total}",
                activity=device,
                stage_fraction=0.15 + 0.82 * fraction,
                indeterminate=False,
            )
            continue
        if not isinstance(item, NoteEndEvent):
            continue
        start_event = item.start_event
        start, end = float(start_event.start_time), float(item.end_time)
        pitch = int(start_event.pitch)
        if end <= start or not 0 <= pitch <= 127:
            continue
        source_name = _muscriptor_source(str(start_event.instrument))
        drum_pitch = pitch if source_name == "drums" else None
        role = (
            GM_DRUMS.get(pitch, "PERCUSSION") if source_name == "drums" else
            "MELODY" if source_name == "vocals" else
            "BASS" if source_name == "bass" else "HARMONY"
        )
        event = MusicEvent(
            source_name,
            role,
            start,
            end,
            None if source_name == "drums" else pitch,
            80,
            0.64,
            "muscriptor",
            {"global_music_model", "instrument_evidence"},
            evidence={
                "instrument": str(start_event.instrument),
                "gm_pitch": drum_pitch,
                "confidence_kind": "MuScriptor global-model prior; no calibrated posterior",
            },
        )
        events.append(event.to_dict())
    return {"events": events, "device": device, "model": variant}


def _prepare_mr_mt3_checkpoint(report) -> Path:
    """Download through huggingface_hub with retries and verify upstream hash."""
    from huggingface_hub import hf_hub_download

    target = Path(os.environ["MT3_CHECKPOINT_DIR"]) / "mr_mt3" / "mt3.pth"
    if target.is_file() and file_hash(target) == MR_MT3_SHA256:
        return target
    if target.exists():
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    errors = []
    for attempt, delay in enumerate((0, 3, 8), 1):
        if delay:
            _report(report, f"Model host is busy; retrying MR-MT3 download in {delay} seconds…",
                    activity="waiting", stage_fraction=0.03)
            time.sleep(delay)
        try:
            _report(report, f"Downloading the MR-MT3 model (attempt {attempt}/3)…",
                    activity="download", stage_fraction=0.04)
            downloaded = Path(hf_hub_download(
                repo_id="gudgud1014/MR-MT3", filename="mt3.pth",
                local_dir=str(target.parent),
            ))
            if downloaded.resolve() != target.resolve():
                shutil.copy2(downloaded, target)
            if file_hash(target) != MR_MT3_SHA256:
                target.unlink(missing_ok=True)
                raise RuntimeError("downloaded checkpoint checksum did not match the pinned MR-MT3 model")
            return target
        except Exception as exc:
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
    raise RuntimeError("Could not download the verified MR-MT3 model after 3 attempts. " + " | ".join(errors))


def mr_mt3(payload: dict, report) -> dict:
    import soxr
    from mt3_infer import load_model
    requested = payload.get("device", "auto")
    try:
        # Auto/CUDA must never silently turn a several-minute GPU inference into
        # an unbounded CPU wait. Advanced → CPU remains an intentional opt-in.
        device = device_for(requested, allow_cpu_fallback=requested == "cpu")
    except RuntimeError as exc:
        raise RuntimeError(
            "Independent musical cross-check could not start GPU acceleration. "
            "It was stopped instead of falling back to a very slow CPU run. " + str(exc)
        ) from exc
    checkpoint = Path(os.environ["MT3_CHECKPOINT_DIR"]) / "mr_mt3" / "mt3.pth"
    weights = [checkpoint] if checkpoint.is_file() else []
    load_message = (
        "Loading the independent musical cross-check…" if weights else
        "Downloading the independent musical cross-check model…"
    )
    with _working_heartbeat(
        report, load_message, activity=device if weights else "download", stage_fraction=0.05,
    ):
        checkpoint = _prepare_mr_mt3_checkpoint(report)
        model = load_model("mr_mt3", checkpoint_path=str(checkpoint), device=device, auto_download=False)
    audio, sr = _audio(payload["audio"])
    audio = audio.mean(axis=1)
    if sr != 16000:
        audio = soxr.resample(audio, sr, 16000)
    duration = len(audio) / 16000
    requested_segments = payload.get("segments")
    segments = requested_segments or [{"start": 0.0, "end": duration, "score": 1.0}]
    validated = []
    for segment in segments:
        start = max(0.0, float(segment["start"]))
        end = min(duration, float(segment["end"]))
        if end-start >= (0.25 if requested_segments else 0.001):
            validated.append({"start": start, "end": end, "score": float(segment.get("score", 0.0))})
    if not validated:
        return {"events": [], "device": device, "coverage": [], "targeted": bool(requested_segments),
                "model_files": [str(x) for x in weights]}

    # Run only the uncertain windows selected by the orchestrator. Model load is
    # shared, and each section boundary gives honest forward progress even though
    # the third-party forward call itself cannot report a byte/percent value.
    target_root = Path(payload["output"])
    target_root.mkdir(parents=True, exist_ok=True)
    events = []
    count = len(validated)
    for index, segment in enumerate(validated):
        start, end = segment["start"], segment["end"]
        samples = audio[round(start*16000):round(end*16000)]
        if count == 1 and not requested_segments:
            fractions = (0.20, 0.45, 0.90)
        else:
            span = 0.78 / count
            base = 0.18 + index * span
            fractions = (base, base + span * 0.28, base + span * 0.82)
        label = f"uncertain section {index+1}/{count} ({start:.1f}–{end:.1f}s)"
        preparation_message = (f"Preparing {label} for the musical cross-check on CPU…"
                               if requested_segments else
                               "Preparing audio features for the musical cross-check on CPU…")
        inference_message = (f"Cross-checking {label} on {device.upper()}…"
                             if requested_segments else
                             f"Cross-checking musical evidence on {device.upper()}…")
        decode_message = (f"Decoding {label}…" if requested_segments else
                          "Decoding the independent musical cross-check…")
        with _working_heartbeat(
            report, preparation_message,
            activity="cpu", stage_fraction=fractions[0],
        ):
            features = model.preprocess(samples, 16000)
        with _working_heartbeat(
            report, inference_message,
            activity=device, stage_fraction=fractions[1],
        ):
            outputs = model.forward(features)
        with _working_heartbeat(
            report, decode_message,
            activity="cpu", stage_fraction=fractions[2],
        ):
            midi = model.decode(outputs)
        target = target_root / f"mr-mt3-{index+1:02d}.mid"
        midi.save(str(target))
        for event in _events_from_midi(target, "mr_mt3"):
            event["start"] += start
            event["end"] += start
            event["tags"] = sorted(set(event.get("tags", [])) | {"targeted_cross_check"})
            event["evidence"] = {
                **event.get("evidence", {}),
                "coverage_start": start, "coverage_end": end,
                "uncertainty_score": segment["score"],
            }
            events.append(event)
    weights = list(Path(os.environ["MT3_CHECKPOINT_DIR"]).rglob("mt3.pth"))
    return {"events": events, "device": device, "coverage": validated,
            "targeted": bool(requested_segments), "model_files": [str(x) for x in weights]}


def adtof(payload: dict, report) -> dict:
    from adtof_pytorch import transcribe_to_midi
    device = device_for(payload.get("device", "auto"))
    target = Path(payload["output"]) / "adtof.mid"
    target.parent.mkdir(parents=True, exist_ok=True)
    _report(report, f"Transcribing drum hits on {device.upper()}…", activity=device, stage_fraction=0.15)
    kwargs = {"device": device} if "device" in inspect.signature(transcribe_to_midi).parameters else {}
    transcribe_to_midi(payload["audio"], str(target), **kwargs)
    import adtof_pytorch
    weights = list(Path(adtof_pytorch.__file__).parent.rglob("*.pth"))
    return {"events": _events_from_midi(target, "adtof", "drums"), "device": device,
            "model_files": [str(x) for x in weights]}


def _onset_features(audio_path: str):
    import numpy as np
    from scipy.signal import stft
    audio, sr = _audio(audio_path)
    mono = audio.mean(axis=1)
    # A short STFT produces semantic energy/onset evidence, never pitched notes.
    frequencies, times, spectrum = stft(mono, sr, nperseg=1024, noverlap=583, boundary="zeros")
    power = np.abs(spectrum)**2
    bands = []
    for low, high in ((30, 180), (180, 4000), (5000, 18000)):
        energy = power[(frequencies >= low) & (frequencies < high)].sum(axis=0)
        flux = np.maximum(0, np.diff(energy, prepend=0))
        bands.append((energy, flux))
    return np, times, bands


def drums_dsp(payload: dict, report) -> dict:
    from scipy.signal import find_peaks
    np, times, bands = _onset_features(payload["audio"])
    _report(report, "Detecting drum attacks on CPU…", activity="cpu", stage_fraction=0.15)
    events = []
    for (energy, flux), role in zip(bands, ("KICK", "SNARE", "CLOSED_HAT")):
        if len(flux) < 4 or float(np.max(energy)) < 1e-10:
            continue
        floor = max(float(np.percentile(flux, 90)) * 0.55, float(np.max(flux)) * 0.06, 1e-10)
        peaks, properties = find_peaks(flux, height=floor, prominence=floor * 0.5, distance=5)
        for index in peaks:
            total = sum(float(b[0][index]) for b in bands) + 1e-12
            share = float(energy[index]) / total
            if (role == "KICK" and share < 0.12) or (role == "CLOSED_HAT" and share < 0.06):
                continue
            strength = float(flux[index]) / (float(np.max(flux)) + 1e-12)
            confidence = min(0.68, 0.32 + strength * 0.23 + share * 0.13)
            start = max(0.0, float(times[index]) - 0.006)
            events.append(MusicEvent("drums", role, start, start + 0.07, None,
                                     max(35, min(110, round(40 + 65 * math.sqrt(strength)))), confidence,
                                     "drums_dsp", {"fallback", "coarse_drum_class"},
                                     evidence={"confidence_kind": "spectral heuristic", "band_share": share}).to_dict())
    return {"events": events, "device": "cpu", "warnings": ["Drum fallback estimates kick/snare/closed hat only; cymbals and toms need the musical cross-check or optional drum model."]}


def beat_dsp(payload: dict, report) -> dict:
    from scipy.signal import find_peaks, correlate
    np, times, bands = _onset_features(payload["audio"])
    if len(times) < 4:
        return {"beat_map": {"engine": "beat_dsp"}, "device": "cpu"}
    flux = sum(x[1] for x in bands)
    if float(np.max(flux)) < 1e-9:
        return {"beat_map": {"engine": "beat_dsp"}, "device": "cpu"}
    hop = float(times[1] - times[0])
    centered = flux - flux.mean()
    correlation = correlate(centered, centered, mode="full", method="fft")[len(flux)-1:]
    low, high = max(1, round(60/200/hop)), min(len(flux)-1, round(60/50/hop))
    if high <= low:
        return {"beat_map": {"engine": "beat_dsp"}, "device": "cpu"}
    lag = low + int(np.argmax(correlation[low:high+1]))
    peaks, _ = find_peaks(flux, distance=max(1, round(lag * 0.65)), prominence=float(np.max(flux)) * 0.08)
    # Use observed attacks, not an invented rigid grid; no guessed downbeats.
    beats = [float(times[p]) for p in peaks]
    return {"beat_map": {"bpm": 60/(lag*hop), "beats": beats, "downbeats": [], "engine": "beat_dsp", "confidence": 0.25},
            "device": "cpu", "warnings": ["Beat fallback has no reliable downbeats; automatic grid snapping is disabled."]}


PROVIDERS = {"basic_pitch": basic_pitch, "torchcrepe": torchcrepe_pitch,
             "demucs": demucs, "roformer": roformer,
             "beat_this": beat_this, "transkun": transkun, "muscriptor": muscriptor, "mr_mt3": mr_mt3,
             "adtof": adtof, "drums_dsp": drums_dsp, "beat_dsp": beat_dsp}
DISTRIBUTIONS = {"basic_pitch": "basic-pitch", "torchcrepe": "torchcrepe",
                 "demucs": "demucs", "roformer": "audio-separator",
                 "beat_this": "beat-this", "transkun": "transkun", "muscriptor": "muscriptor",
                 "mr_mt3": "mt3-infer", "adtof": "adtof-pytorch"}


def run_provider(provider: str, payload: dict, report) -> dict:
    result = PROVIDERS[provider](payload, report)
    version = "1"
    if provider in DISTRIBUTIONS:
        version = importlib.metadata.version(DISTRIBUTIONS[provider])
    files = result.pop("model_files", [])
    checksums = {p: file_hash(Path(p)) for p in files if Path(p).is_file()}
    result["provenance"] = {"provider": provider, "version": version,
                            "model": result.get("model", PROVIDER_MODEL.get(provider, provider)),
                            "device": result.get("device", "cpu"), "model_sha256": checksums}
    for key in ("ensemble", "targeted", "coverage"):
        if key in result:
            result["provenance"][key] = result[key]
    if payload.get("models") and checksums:
        atomic_json(Path(payload["models"]) / "inventory" / (provider + ".json"), checksums)
    return result
