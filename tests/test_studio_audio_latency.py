from __future__ import annotations

from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

import studio_audio_latency as latency
from studio_audio_latency import (
    AudioLatencySample,
    AudioLatencySummary,
    detect_audio_onset,
    load_audio_latency_summary,
    save_audio_latency_summary,
    summarize_latency,
)


def test_synthetic_loopback_attack_is_detected_after_baseline() -> None:
    sample_rate = 48_000
    baseline_frames = round(sample_rate * 0.20)
    expected_delay_ms = 55.0
    onset = baseline_frames + round(sample_rate * expected_delay_ms / 1000.0)
    total = onset + round(sample_rate * 0.20)
    data = np.zeros((total, 2), dtype=np.float64)
    t = np.arange(total - onset, dtype=np.float64) / sample_rate
    tone = 0.12 * np.sin(2 * np.pi * 440.0 * t)
    data[onset:, 0] = tone
    data[onset:, 1] = tone

    result = detect_audio_onset(data, sample_rate, baseline_frames)
    assert result.latency_ms is not None
    assert abs(result.latency_ms - expected_delay_ms) <= 6.0
    assert result.peak_rms > result.threshold


def test_detector_rejects_unchanged_silence() -> None:
    data = np.zeros((24_000, 2), dtype=np.float64)
    result = detect_audio_onset(data, 48_000, 9_600)
    assert result.latency_ms is None


def test_latency_summary_reports_median_p95_jitter_and_failures() -> None:
    summary = summarize_latency(
        "keyboard",
        [
            AudioLatencySample(38.0, 0.01, 0.001, 0.2),
            AudioLatencySample(40.0, 0.01, 0.001, 0.2),
            AudioLatencySample(43.0, 0.01, 0.001, 0.2),
            AudioLatencySample(45.0, 0.01, 0.001, 0.2),
            AudioLatencySample(None, 0.01, 0.001, 0.0),
        ],
        "Speakers",
    )
    assert summary.p50_ms == 41.5
    assert summary.p95_ms == 45.0
    assert summary.jitter_ms == 3.5
    assert summary.failed_samples == 1
    assert summary.quality == "Stable"


def test_audio_latency_summary_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "audio_latency.json"
    monkeypatch.setattr(latency, "audio_latency_path", lambda: target)
    summary = AudioLatencySummary(
        instrument="guitar",
        samples_ms=(50.0, 52.0, 54.0),
        p50_ms=52.0,
        p95_ms=54.0,
        jitter_ms=2.0,
        failed_samples=0,
        speaker_name="Test Output",
        measured_at=1234.5,
    )
    save_audio_latency_summary(summary)
    loaded = load_audio_latency_summary("guitar")
    assert loaded == summary


def test_studio_launcher_installs_audio_latency_after_calibration_lab() -> None:
    source = Path("studio_launcher.py").read_text(encoding="utf-8")
    assert "from studio_audio_latency import install_studio_audio_latency" in source
    assert source.index("install_calibration_lab(app)") < source.index("install_studio_audio_latency(app)")


def test_studio_spec_bundles_soundcard_data_and_mediafoundation_backend() -> None:
    source = Path("BPSR-MIDI-Studio.spec").read_text(encoding="utf-8")
    assert 'collect_data_files("soundcard")' in source
    assert '"soundcard.mediafoundation"' in source
