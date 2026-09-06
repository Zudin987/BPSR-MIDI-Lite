"""Opt-in model smoke gates for Windows CI; ordinary Lite tests need no AI."""
import os
import json
import math
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(os.environ.get("BPSR_STUDIO_LIVE") != "1", reason="requires downloaded Studio runtimes")
def test_real_audio_pipeline(tmp_path):
    from studio_band.pipeline import BandPipeline, ConversionSettings
    from studio_band.runtime import RuntimeManager
    from studio_band.storage import read_json
    from studio_synthetic_audio import make_song, reference_events
    from studio_band.benchmark import transcription_benchmark
    source = tmp_path / "Original synthetic band.wav"
    make_song(source)
    reports = Path("model-smoke-report")
    reports.mkdir(exist_ok=True)
    runtime = RuntimeManager()
    if os.environ.get("BPSR_STUDIO_CLEAN_RUNTIME") == "1":
        assert not runtime.python("piano").exists(), "clean first-use Transkun runtime was already populated"
    try:
        path = BandPipeline(runtimes=runtime).convert(source, ConversionSettings(device="cpu"), progress=print)
    except Exception as exc:
        import traceback
        (reports / "failure.json").write_text(json.dumps({"error": str(exc), "details": getattr(exc, "details", ""),
                                                        "traceback": traceback.format_exc()}, indent=2), encoding="utf-8")
        raise
    record = read_json(path)
    assert len(record["parts"]["piano"])+len(record["parts"]["guitar"]) > 0
    assert record["providers"]["separator"]["actual"] == "demucs"
    assert record["source_audio_sha256"]
    (reports / "actual-providers.json").write_text(json.dumps(record["providers"], indent=2), encoding="utf-8")
    (reports / "quality-notes.json").write_text(json.dumps(record["warnings"], indent=2), encoding="utf-8")
    benchmark = transcription_benchmark(reference_events(), record["master_song"]["events"])
    assert benchmark["sources"] and all(math.isfinite(value) for value in benchmark["macro"].values())
    (reports / "mir-eval-benchmark.json").write_text(json.dumps(benchmark, indent=2), encoding="utf-8")
    for provider in ("demucs", "torchcrepe", "transkun", "beat_this", "mr_mt3"):
        assert any(e["provider"] == provider for e in record["providers"]["engines"]), f"Preferred model failed: {provider}; see report"
    for metric in record["providers"]["stem_metrics"].values():
        assert metric["spectral_purity"] is not None
        assert 0 <= metric["spectral_confidence"] <= 1

    # This is the exact clean external-runtime path used by the frozen Studio.
    # --only-binary ncls makes a compiler impossible even though hosted runners
    # happen to contain Visual Studio; the import and real inference above prove
    # that the selected CPython 3.11 Windows wheel works with Transkun 2.0.1.
    piano_record = read_json(runtime.runtime_root / "piano" / "studio-runtime.json")
    assert piano_record["constraints"] == ["ncls==0.0.68"]
    assert piano_record["binary_only"] == ["ncls"] and piano_record["validated"] is True
    assert "ncls==0.0.68" in piano_record["packages"]
    assert "ncls==0.0.70" not in piano_record["packages"]
    check = (
        "import importlib.metadata as m,json,ncls,pathlib,sys,transkun; "
        "files=[str(x) for x in (m.distribution('ncls').files or [])]; "
        "print(json.dumps({'python':sys.version.split()[0],'transkun':m.version('transkun'),"
        "'ncls':m.version('ncls'),'extension_files':[x for x in files if x.lower().endswith('.pyd')]}))"
    )
    versions = json.loads(subprocess.check_output(
        [str(runtime.python("piano")), "-c", check], text=True, timeout=120,
        env=runtime.environment(),
    ))
    assert versions["python"].startswith("3.11.")
    assert versions["transkun"] == "2.0.1" and versions["ncls"] == "0.0.68"
    assert versions["extension_files"], "ncls Windows extension from the wheel was not installed"
    (reports / "transkun-clean-runtime.json").write_text(json.dumps({
        "versions": versions,
        "constraints": piano_record["constraints"],
        "binary_only": piano_record["binary_only"],
        "compiler_required": False,
        "real_transkun_inference": True,
    }, indent=2), encoding="utf-8")

    mt3_record = read_json(runtime.runtime_root / "mt3" / "studio-runtime.json")
    assert mt3_record["torch_backend"] == "cpu" and mt3_record["validated"] is True
    assert "torch==2.11.0+cpu" in mt3_record["packages"]
    assert "torchaudio==2.11.0+cpu" in mt3_record["packages"]
    assert "torchvision==0.26.0+cpu" in mt3_record["packages"]
    separator_record = read_json(runtime.runtime_root / "separator" / "studio-runtime.json")
    assert separator_record["torch_backend"] == "cpu" and separator_record["validated"] is True
    assert "torchcrepe==0.0.24" in separator_record["packages"]
    assert "torch==2.11.0+cpu" in separator_record["packages"]
    assert record["providers"]["cross_check"]["mode"] == "targeted_low_confidence"
    assert record["providers"]["cross_check"]["coverage_ratio"] <= 1.0


@pytest.mark.skipif(
    os.environ.get("BPSR_STUDIO_LIVE") != "1" or os.name != "nt",
    reason="Windows clean-runtime wheel resolution gate",
)
def test_windows_mt3_cuda_wheels_resolve_from_official_backend(tmp_path):
    """Resolve the exact GPU stack without requiring a GPU on the hosted runner."""
    from studio_band.runtime import RUNTIMES, RuntimeManager

    runtime = RuntimeManager()
    uv = runtime._uv()
    target = tmp_path / "cuda-resolution"
    subprocess.check_call(
        [str(uv), "venv", "--python", "3.11", "--managed-python", str(target)],
        env=runtime.environment(),
    )
    python = target / "Scripts" / "python.exe"
    resolved = subprocess.run(
        [str(uv), "pip", "install", "--dry-run", "--python", str(python),
         *RUNTIMES["mt3"], "--torch-backend", "cu128", "--strict"],
        env=runtime.environment(), text=True, capture_output=True, timeout=900, check=True,
    )
    plan = resolved.stdout + "\n" + resolved.stderr
    for requirement in (
        "torch==2.11.0+cu128",
        "torchaudio==2.11.0+cu128",
        "torchvision==0.26.0+cu128",
    ):
        assert requirement in plan
    separator = subprocess.run(
        [str(uv), "pip", "install", "--dry-run", "--python", str(python),
         *RUNTIMES["separator"], "--torch-backend", "cu128", "--strict"],
        env=runtime.environment(), text=True, capture_output=True, timeout=900, check=True,
    )
    separator_plan = separator.stdout + "\n" + separator.stderr
    for requirement in ("torch==2.11.0+cu128", "torchaudio==2.11.0+cu128", "torchcrepe==0.0.24"):
        assert requirement in separator_plan
    reports = Path("model-smoke-report")
    reports.mkdir(exist_ok=True)
    (reports / "mt3-windows-cuda-resolution.txt").write_text(plan, encoding="utf-8")
    (reports / "separator-windows-cuda-resolution.txt").write_text(separator_plan, encoding="utf-8")


@pytest.mark.skipif(os.environ.get("BPSR_STUDIO_HQ_LIVE") != "1", reason="requires the additional HQ model")
def test_real_hq_separation(tmp_path):
    import json
    import soundfile as sf
    from studio_band.protocol import WorkerClient
    from studio_band.runtime import RuntimeManager
    from studio_youtube import _ffmpeg_executable
    from studio_synthetic_audio import make_song
    source = tmp_path / "Original HQ fixture.wav"
    make_song(source)
    runtime = RuntimeManager()
    reports = Path("hq-smoke-report")
    reports.mkdir(exist_ok=True)
    try:
        runtime.install("hq", device="cpu", progress=print)
        client = WorkerClient(tmp_path / "requests", runtime.command_for, runtime.environment(_ffmpeg_executable()))
        result = client.call("roformer", "infer", {"audio": str(source), "output": str(tmp_path / "stems"),
                             "models": str(runtime.models), "device": "cpu"}, progress=print, timeout=3600)
        (reports / "provider.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        original = sf.info(source)
        for name in ("vocals", "instrumental"):
            info = sf.info(result[name])
            assert info.samplerate == original.samplerate and abs(info.frames-original.frames) <= 1
        assert result["provenance"]["model_sha256"]
    except Exception as exc:
        (reports / "failure.json").write_text(json.dumps({"error": str(exc), "details": getattr(exc, "details", "")}, indent=2), encoding="utf-8")
        raise
