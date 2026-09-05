"""Real inference adapters, imported only in workers. No models are vendored."""
from __future__ import annotations

import importlib.metadata
import inspect
import math
import os
import statistics
from pathlib import Path

from .music import MusicEvent
from .runtime import HQ_MODEL, PROVIDER_MODEL
from .storage import atomic_json, file_hash

GM_DRUMS = {
    35: "KICK", 36: "KICK", 37: "SNARE", 38: "SNARE", 40: "SNARE",
    42: "CLOSED_HAT", 44: "CLOSED_HAT", 46: "OPEN_HAT",
    49: "CRASH", 52: "CRASH", 55: "CRASH", 57: "CRASH",
    51: "RIDE", 53: "RIDE", 59: "RIDE",
    41: "TOM", 43: "TOM", 45: "TOM", 47: "TOM", 48: "TOM", 50: "TOM",
}


def device_for(requested: str) -> str:
    import torch
    if requested != "cpu" and torch.cuda.is_available():
        # An installed CUDA wheel may predate the GPU architecture. Test a real
        # kernel instead of treating nvidia-smi/is_available as sufficient.
        try:
            (torch.ones(8, device="cuda") * 2).sum().item()
            return "cuda"
        except RuntimeError:
            pass
    return "cpu"


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
    from basic_pitch.inference import predict
    from studio_youtube import _basic_pitch_model
    source = payload["source"]
    # Bass limits do not share the broad piano/song range. Keep the original
    # register here: BPSR fitting belongs after the musical map.
    limits = {"bass": (30.87, 246.94, 100.0), "guitar": (73.42, 1318.51, 85.0),
              "vocals": (65.41, 1396.91, 90.0), "piano": (27.5, 4186.01, 70.0),
              "other": (65.41, 2093.0, 120.0)}
    low, high, minimum = limits[source]
    report("Listening for " + source + " notes…")
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
    return {"events": events, "device": "cpu", "model_files": [str(_basic_pitch_model())]}


def demucs(payload: dict, report) -> dict:
    import numpy as np
    import soundfile as sf
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model
    device = device_for(payload.get("device", "auto"))
    torch.manual_seed(0)
    report("Loading the six-instrument separator…")
    model = get_model("htdemucs_6s")
    model.eval()
    audio, sr = _audio(payload["audio"])
    if sr != model.samplerate or audio.shape[1] != model.audio_channels:
        raise ValueError("Separator expects the prepared stereo 44.1 kHz audio")
    waveform = torch.from_numpy(audio.T.copy())
    ref = waveform.mean(0)
    mean, scale = ref.mean(), ref.std()
    if float(scale) < 1e-8:
        separated = torch.zeros((len(model.sources), *waveform.shape))
    else:
        normalized = (waveform - mean) / scale
        report("Separating vocals, piano, guitar, bass and drums…")
        with torch.inference_mode():
            separated = apply_model(model, normalized[None], device=device, shifts=1, split=True,
                                    overlap=0.25, progress=False, num_workers=0)[0]
        separated = separated.cpu() * scale + mean
    target = Path(payload["output"])
    target.mkdir(parents=True, exist_ok=True)
    stems, metrics = {}, {}
    for name, tensor in zip(model.sources, separated):
        path = target / (name + ".wav")
        samples = tensor.numpy().T
        sf.write(str(path), samples, sr, subtype="FLOAT")
        stems[name] = str(path)
        metrics[name] = {"rms": float(np.sqrt(np.mean(samples.astype("float64")**2))),
                         "purity": None, "confidence_prior": 0.72}
    if set(stems) != {"vocals", "piano", "guitar", "bass", "drums", "other"}:
        raise ValueError("Demucs did not return the expected six stems")
    weights = list((Path(os.environ["TORCH_HOME"]) / "hub" / "checkpoints").glob("5c90dfd2*"))
    return {"stems": stems, "metrics": metrics, "device": device, "model_files": [str(x) for x in weights]}


def roformer(payload: dict, report) -> dict:
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
    report("Loading the HQ vocal separator (separate model download on first use)…")
    separator = Separator(model_file_dir=str(models), output_dir=str(target), output_format="WAV",
                          sample_rate=44100, use_soundfile=True, normalization_threshold=0.99,
                          mdxc_params={"segment_size": 256, "override_model_segment_size": False, "batch_size": 1, "overlap": 8})
    separator.load_model(model_filename=HQ_MODEL)
    outputs = separator.separate(payload["audio"], custom_output_names={"Vocals": "hq_vocals", "Instrumental": "hq_instrumental"})
    paths = [Path(x) if Path(x).is_absolute() else target / x for x in outputs]
    vocals = next((p for p in paths if "hq_vocals" in p.name), None)
    instrumental = next((p for p in paths if "hq_instrumental" in p.name), None)
    if not vocals or not instrumental or not vocals.exists() or not instrumental.exists():
        raise ValueError("HQ separator did not return vocals and instrumental audio")
    # A vocal RoFormer is not a six-stem model. The orchestrator runs Demucs on
    # this instrumental file, then uses this cleaner vocal stem for melody.
    return {"vocals": str(vocals), "instrumental": str(instrumental), "device": device,
            "model_files": [str(p) for p in models.iterdir() if p.is_file()]}


def beat_this(payload: dict, report) -> dict:
    from beat_this.inference import File2Beats
    device = device_for(payload.get("device", "auto"))
    report("Detecting the song's master beat and downbeats…")
    tracker = File2Beats(checkpoint_path="final0", device=device, dbn=False)
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
    report("Loading the piano specialist…")
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
    report("Transcribing piano performance…")
    with torch.inference_mode():
        notes = model.transcribe(torch.from_numpy(np.asarray(audio, dtype="float32")).to(device),
                                 stepInSecond=None, segmentSizeInSecond=None, discardSecondHalf=False)
    target = Path(payload["output"]) / "transkun.mid"
    target.parent.mkdir(parents=True, exist_ok=True)
    writeMidi(notes).write(str(target))
    return {"events": _events_from_midi(target, "transkun", "piano"), "device": device,
            "model_files": [str(weight), str(config)]}


def mr_mt3(payload: dict, report) -> dict:
    import soxr
    from mt3_infer import load_model
    device = device_for(payload.get("device", "auto"))
    report("Loading the independent musical cross-check…")
    model = load_model("mr_mt3", device=device, auto_download=True)
    audio, sr = _audio(payload["audio"])
    audio = audio.mean(axis=1)
    if sr != 16000:
        audio = soxr.resample(audio, sr, 16000)
    midi = model.transcribe(audio, sr=16000)
    target = Path(payload["output"]) / "mr-mt3.mid"
    target.parent.mkdir(parents=True, exist_ok=True)
    midi.save(str(target))
    weights = list(Path(os.environ["MT3_CHECKPOINT_DIR"]).rglob("mt3.pth"))
    return {"events": _events_from_midi(target, "mr_mt3"), "device": device,
            "model_files": [str(x) for x in weights]}


def adtof(payload: dict, report) -> dict:
    from adtof_pytorch import transcribe_to_midi
    device = device_for(payload.get("device", "auto"))
    target = Path(payload["output"]) / "adtof.mid"
    target.parent.mkdir(parents=True, exist_ok=True)
    report("Transcribing drum hits with the optional drum model…")
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
    report("Detecting drum attacks with the conservative fallback…")
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


PROVIDERS = {"basic_pitch": basic_pitch, "demucs": demucs, "roformer": roformer,
             "beat_this": beat_this, "transkun": transkun, "mr_mt3": mr_mt3,
             "adtof": adtof, "drums_dsp": drums_dsp, "beat_dsp": beat_dsp}
DISTRIBUTIONS = {"basic_pitch": "basic-pitch", "demucs": "demucs", "roformer": "audio-separator",
                 "beat_this": "beat-this", "transkun": "transkun", "mr_mt3": "mt3-infer", "adtof": "adtof-pytorch"}


def run_provider(provider: str, payload: dict, report) -> dict:
    result = PROVIDERS[provider](payload, report)
    version = "1"
    if provider in DISTRIBUTIONS:
        version = importlib.metadata.version(DISTRIBUTIONS[provider])
    files = result.pop("model_files", [])
    checksums = {p: file_hash(Path(p)) for p in files if Path(p).is_file()}
    result["provenance"] = {"provider": provider, "version": version, "model": PROVIDER_MODEL.get(provider, provider),
                            "device": result.get("device", "cpu"), "model_sha256": checksums}
    if payload.get("models") and checksums:
        atomic_json(Path(payload["models"]) / "inventory" / (provider + ".json"), checksums)
    return result
