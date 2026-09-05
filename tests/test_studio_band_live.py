"""Opt-in model smoke gates for Windows CI; ordinary Lite tests need no AI."""
import os
from pathlib import Path

import pytest


@pytest.mark.skipif(os.environ.get("BPSR_STUDIO_LIVE") != "1", reason="requires downloaded Studio runtimes")
def test_real_audio_pipeline(tmp_path):
    from studio_band.pipeline import BandPipeline, ConversionSettings
    from studio_band.storage import read_json
    from studio_synthetic_audio import make_song
    source = tmp_path / "Original synthetic band.wav"
    make_song(source)
    reports = Path("model-smoke-report")
    reports.mkdir(exist_ok=True)
    try:
        path = BandPipeline().convert(source, ConversionSettings(device="cpu"), progress=print)
    except Exception as exc:
        import json
        import traceback
        (reports / "failure.json").write_text(json.dumps({"error": str(exc), "details": getattr(exc, "details", ""),
                                                        "traceback": traceback.format_exc()}, indent=2), encoding="utf-8")
        raise
    record = read_json(path)
    assert len(record["parts"]["piano"])+len(record["parts"]["guitar"]) > 0
    assert record["providers"]["separator"]["actual"] == "demucs"
    assert record["source_audio_sha256"]
    (reports / "actual-providers.json").write_text(__import__("json").dumps(record["providers"], indent=2), encoding="utf-8")
    (reports / "quality-notes.json").write_text(__import__("json").dumps(record["warnings"], indent=2), encoding="utf-8")
    for provider in ("demucs", "transkun", "beat_this", "mr_mt3"):
        assert any(e["provider"] == provider for e in record["providers"]["engines"]), f"Preferred model failed: {provider}; see report"
