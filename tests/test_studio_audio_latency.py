from __future__ import annotations

import threading
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

import studio_audio_latency as latency
from studio_audio_latency import (
    AudioLatencySample,
    AudioLatencySummary,
    MeasurementCancelled,
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


def test_cancelled_frame_collection_exits_before_touching_recorder() -> None:
    class Recorder:
        def record(self, **_kwargs):
            raise AssertionError("cancelled collection must not read the recorder")

    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(MeasurementCancelled):
        latency._collect_frames(Recorder(), 256, cancelled)


def test_measure_trial_releases_key_when_cancelled_during_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    class Recorder:
        def record(self, numframes=None):
            frames = 256 if numframes is None else int(numframes)
            return np.zeros((frames, 2), dtype=np.float64)

    class Sender:
        def __init__(self) -> None:
            self.down = False
            self.released = False

        def key_down(self, _key: str) -> None:
            self.down = True

        def key_up(self, _key: str) -> None:
            self.down = False
            self.released = True

    sender = Sender()
    cancelled = threading.Event()

    def cancel_on_wait(_timeout: float) -> bool:
        cancelled.set()
        return True

    monkeypatch.setattr(cancelled, "wait", cancel_on_wait)
    with pytest.raises(MeasurementCancelled):
        latency._measure_trial(Recorder(), sender, "a", 120, 48_000, cancelled)
    assert sender.down is False
    assert sender.released is True


def test_studio_worker_captures_tk_input_backend_before_thread_body() -> None:
    source = Path("studio_audio_latency.py").read_text(encoding="utf-8")
    start = source.index("def start_measurement")
    worker = source.index("def worker()", start)
    capture = source.index("input_backend = self._input_backend_code()", start)
    assert capture < worker
    worker_source = source[worker:]
    assert "input_backend=input_backend" in worker_source
    assert "self._input_backend_code()" not in worker_source


def test_studio_latency_ui_wires_f10_and_close_cancellation() -> None:
    source = Path("studio_audio_latency.py").read_text(encoding="utf-8")
    assert "def poll_f10" in source
    assert "_studio_latency_cancel_event.set()" in source
    assert "def on_close" in source
    assert "thread.join(timeout=1.5)" in source


def test_studio_launcher_installs_audio_latency_after_calibration_lab() -> None:
    source = Path("studio_launcher.py").read_text(encoding="utf-8")
    assert "from studio_audio_latency import install_studio_audio_latency" in source
    assert source.index("install_calibration_lab(app)") < source.index("install_studio_audio_latency(app)")


def test_studio_spec_bundles_soundcard_data_and_mediafoundation_backend() -> None:
    source = Path("BPSR-MIDI-Studio.spec").read_text(encoding="utf-8")
    assert 'collect_data_files("soundcard")' in source
    assert '"soundcard.mediafoundation"' in source
