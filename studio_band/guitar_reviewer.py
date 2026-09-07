"""Dedicated guitar multi-pitch reviewer used only as corroborating evidence.

This adapter intentionally never creates MIDI notes.  It reproduces the published
HCQT+Mel feature path and six-fold multi-pitch ensemble from
ErenReyhanlioglu/Guitar-Transcription, then scores only guitar notes that the
normal BPSR pipeline already proposed.
"""
from __future__ import annotations

import gc
import hashlib
import math
from pathlib import Path
import urllib.request

GUITAR_SOURCE_REVISION = "9f8e31d2ed42c2f8d155d6164ea2fdb43e285482"
GUITAR_WEIGHTS_REVISION = "e2be2c66a71b76ced009afcd0f6bf837c0b9b8a3"
_WEIGHT_SIZE = 26_763_099
_WEIGHT_BLOBS = (
    "82094eecad83603b331b1bfbce0f0310f8942df8",
    "5a192f799d6cb73afd5b600328a4d5f951ba0388",
    "e4d0f841831e7557c538518e413ee43e42a94f41",
    "8863e11ecf88b655f488aa970fe463bfebe7d7fe",
    "267127f92748fa5783bd33148332209268c50ea8",
    "857e952bc68340279edb96e3c89850ab53117842",
)


def _git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def _weight_path(models: Path, fold: int, report=None) -> Path:
    root = models / "guitar-review"
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"fold_{fold}_model_best.pt"
    expected = _WEIGHT_BLOBS[fold - 1]
    if target.is_file() and target.stat().st_size == _WEIGHT_SIZE:
        try:
            if _git_blob_sha1(target.read_bytes()) == expected:
                return target
        except OSError:
            pass
    target.unlink(missing_ok=True)
    url = (
        "https://raw.githubusercontent.com/"
        "ErenReyhanlioglu/Guitar-Transcription-Weights/"
        f"{GUITAR_WEIGHTS_REVISION}/cnn_mtl_20251210_113013/"
        f"fold_{fold}/model_best.pt"
    )
    if report:
        report({
            "message": f"Downloading guitar reviewer fold {fold}/6…",
            "activity": "download",
            "stage_fraction": .08 + .04 * (fold - 1),
            "indeterminate": True,
        })
    partial = target.with_suffix(".partial")
    partial.unlink(missing_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "BPSR-MIDI-Studio"})
    with urllib.request.urlopen(request, timeout=60) as remote, partial.open("wb") as out:
        size = 0
        while chunk := remote.read(1024 * 1024):
            size += len(chunk)
            if size > _WEIGHT_SIZE + 1024:
                raise ValueError("Guitar reviewer weight download is unexpectedly large")
            out.write(chunk)
    data = partial.read_bytes()
    if len(data) != _WEIGHT_SIZE or _git_blob_sha1(data) != expected:
        partial.unlink(missing_ok=True)
        raise ValueError(f"Guitar reviewer fold {fold} checksum/size verification failed")
    partial.replace(target)
    return target


def _features(audio_path: Path):
    import librosa
    import numpy as np
    import soundfile as sf

    audio, sr = sf.read(str(audio_path), dtype="float32", always_2d=True)
    mono = np.asarray(audio.mean(axis=1), dtype="float32")
    if sr != 22050:
        mono = librosa.resample(mono, orig_sr=sr, target_sr=22050, res_type="soxr_hq")
        sr = 22050

    hop = 512
    bins = 144
    bpo = 36
    fmin = float(librosa.note_to_hz("E2"))
    alpha = 2.0 ** (1.0 / bpo) - 1.0
    gamma = 24.7 * alpha / 0.108
    hcqt = []
    for harmonic in (.5, 1.0, 2.0, 3.0, 4.0, 5.0):
        value = librosa.vqt(
            y=mono, sr=sr, hop_length=hop, fmin=fmin * harmonic,
            n_bins=bins, bins_per_octave=bpo, gamma=gamma,
        )
        value = librosa.amplitude_to_db(abs(value), ref=np.max)
        hcqt.append(np.asarray(value, dtype="float32"))
    frames = min(value.shape[-1] for value in hcqt)
    hcqt = np.stack([value[:, :frames] for value in hcqt], axis=0)

    mel = librosa.feature.melspectrogram(
        y=mono, sr=sr, n_mels=256, n_fft=2048, hop_length=hop,
        win_length=None, center=True, htk=False,
    )
    mel = librosa.power_to_db(mel, ref=np.max).astype("float32")[None, :, :frames]
    frames = min(frames, mel.shape[-1])
    return hcqt[..., :frames], mel[..., :frames], sr, hop


def _model():
    import torch
    from torch import nn

    class SEBlock(nn.Module):
        def __init__(self, channels):
            super().__init__()
            self.avg_pool = nn.AdaptiveAvgPool2d(1)
            self.fc = nn.Sequential(
                nn.Linear(channels, channels // 16, bias=False), nn.ReLU(inplace=True),
                nn.Linear(channels // 16, channels, bias=False), nn.Sigmoid(),
            )
        def forward(self, x):
            b, c, _, _ = x.shape
            y = self.fc(self.avg_pool(x).view(b, c)).view(b, c, 1, 1)
            return x * y.expand_as(x)

    class MultiScaleConvBlock(nn.Module):
        def __init__(self, in_channels, out_channels):
            super().__init__()
            kernels = ((3, 3), (5, 5), (1, 9))
            branches = []
            for kh, kw in kernels:
                branches.append(nn.Sequential(
                    nn.Conv2d(in_channels, out_channels, (kh, kw), padding=((kh-1)//2, (kw-1)//2)),
                    nn.BatchNorm2d(out_channels), nn.ReLU(),
                    nn.Conv2d(out_channels, out_channels, (kh, kw), padding=((kh-1)//2, (kw-1)//2)),
                    nn.BatchNorm2d(out_channels), nn.ReLU(),
                ))
            self.branches = nn.ModuleList(branches)
            self.fusion = nn.Sequential(
                nn.Conv2d(out_channels * len(kernels), out_channels, 1),
                nn.BatchNorm2d(out_channels), nn.ReLU(),
            )
            self.use_se = True
            self.se = SEBlock(out_channels)
            self.pool = nn.MaxPool2d((2, 2))
            self.dropout = nn.Dropout(.25)
        def forward(self, x):
            x = self.fusion(torch.cat([branch(x) for branch in self.branches], dim=1))
            x = self.se(x)
            return self.dropout(self.pool(x))

    class GuitarMTL(nn.Module):
        def __init__(self):
            super().__init__()
            def branch(channels):
                layers = []
                current = channels
                for out_ch in (32, 64, 128):
                    layers.append(MultiScaleConvBlock(current, out_ch))
                    current = out_ch
                return nn.Sequential(*layers)
            self.feature_branches = nn.ModuleDict({"hcqt": branch(6), "mel": branch(1)})
            self.projections = nn.ModuleDict({
                "hcqt": nn.Linear(128 * 18 * 2, 256),
                "mel": nn.Linear(128 * 32 * 2, 256),
            })
            bottleneck = 512
            self.heads = nn.ModuleDict({
                "multipitch": nn.Sequential(nn.Linear(bottleneck, 256), nn.ReLU(), nn.Dropout(.25), nn.Linear(256, 49)),
                "hand_position": nn.Sequential(nn.Linear(bottleneck, 128), nn.ReLU(), nn.Dropout(.25), nn.Linear(128, 5)),
                "string_activity": nn.Sequential(nn.Linear(bottleneck, 64), nn.ReLU(), nn.Dropout(.25), nn.Linear(64, 6)),
                "pitch_class": nn.Sequential(nn.Linear(bottleneck, 128), nn.ReLU(), nn.Dropout(.25), nn.Linear(128, 12)),
                "tablature": nn.Sequential(nn.Linear(512 + 49 + 5 + 6 + 12, 256), nn.ReLU(), nn.Dropout(.5), nn.Linear(256, 126)),
            })

        def multipitch(self, inputs):
            encoded = []
            for key in ("hcqt", "mel"):
                value = self.feature_branches[key](inputs[key]).flatten(1)
                encoded.append(self.projections[key](value))
            return self.heads["multipitch"](torch.cat(encoded, dim=1))

    return GuitarMTL()


def review_guitar_candidates(payload: dict, report=None) -> dict:
    """Return evidence scores for supplied guitar candidates; never generate notes."""
    import numpy as np
    import torch
    import torch.nn.functional as F

    candidates = [
        item for item in payload.get("candidates", [])
        if item.get("pitch") is not None and 40 <= int(item["pitch"]) <= 88
    ]
    if not candidates:
        return {"support": [], "model": "guitar-mtl-6fold", "review_only": True}

    device_name = str(payload.get("device", "auto")).lower()
    device = torch.device("cuda" if device_name != "cpu" and torch.cuda.is_available() else "cpu")
    hcqt, mel, sr, hop = _features(Path(payload["audio"]))
    frames = min(hcqt.shape[-1], mel.shape[-1])
    if frames <= 0:
        return {"support": [], "model": "guitar-mtl-6fold", "review_only": True}

    needed = set()
    candidate_frames = []
    for item in candidates:
        start = max(0.0, float(item["start"]) - .04)
        end = max(start + .04, min(float(item["end"]) + .04, float(item["start"]) + .42))
        left = max(0, int(math.floor(start * sr / hop)))
        right = min(frames, int(math.ceil(end * sr / hop)) + 1)
        indices = list(range(left, max(left + 1, right)))
        candidate_frames.append(indices)
        needed.update(indices)
    selected = sorted(index for index in needed if 0 <= index < frames)
    if not selected:
        return {"support": [], "model": "guitar-mtl-6fold", "review_only": True}
    row = {frame: index for index, frame in enumerate(selected)}

    hcqt_tensor = torch.from_numpy(hcqt)
    mel_tensor = torch.from_numpy(mel)
    hcqt_windows = F.pad(hcqt_tensor, (9, 9)).unfold(-1, 19, 1).permute(2, 0, 1, 3)
    mel_windows = F.pad(mel_tensor, (9, 9)).unfold(-1, 19, 1).permute(2, 0, 1, 3)
    probabilities = torch.zeros((len(selected), 49), dtype=torch.float32)

    weights = [_weight_path(Path(payload["models"]), fold, report) for fold in range(1, 7)]
    index_tensor = torch.tensor(selected, dtype=torch.long)
    for fold, path in enumerate(weights, 1):
        if report:
            report({
                "message": f"Reviewing guitar notes · specialist fold {fold}/6",
                "activity": "gpu" if device.type == "cuda" else "cpu",
                "stage_fraction": .32 + .10 * (fold - 1),
                "indeterminate": False,
            })
        model = _model().to(device)
        state = torch.load(str(path), map_location="cpu", weights_only=True)
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        model.load_state_dict(state, strict=True)
        model.eval()
        chunks = []
        with torch.inference_mode():
            for begin in range(0, len(selected), 512):
                ids = index_tensor[begin:begin+512]
                inputs = {
                    "hcqt": hcqt_windows.index_select(0, ids).contiguous().to(device),
                    "mel": mel_windows.index_select(0, ids).contiguous().to(device),
                }
                chunks.append(torch.sigmoid(model.multipitch(inputs)).cpu())
        probabilities += torch.cat(chunks, dim=0) / 6.0
        del model, state, chunks
        gc.collect()
        if device.type == "cuda":
            torch.cuda.empty_cache()

    result = []
    for item, indices in zip(candidates, candidate_frames):
        values = [
            float(probabilities[row[index], int(item["pitch"]) - 40])
            for index in indices if index in row
        ]
        if not values:
            continue
        ordered = sorted(values, reverse=True)
        top = ordered[: min(3, len(ordered))]
        score = .65 * max(values) + .35 * (sum(top) / len(top))
        result.append({
            "source": "guitar", "pitch": int(item["pitch"]),
            "start": float(item["start"]), "end": float(item["end"]),
            "support": round(max(0.0, min(1.0, score)), 5),
            "frames": len(values),
        })
    return {
        "support": result,
        "device": device.type,
        "model": "Guitar-Transcription HCQT+Mel six-fold multi-pitch ensemble",
        "review_only": True,
        "source_revision": GUITAR_SOURCE_REVISION,
        "weights_revision": GUITAR_WEIGHTS_REVISION,
        "model_files": [str(path) for path in weights],
    }
