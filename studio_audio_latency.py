from __future__ import annotations

import json
import math
import os
import queue
import statistics
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

import numpy as np

import win_input as wi

SAMPLE_RATE = 48_000
BLOCKSIZE = 1024
READ_FRAMES = 256
BASELINE_SECONDS = 0.35
CAPTURE_SECONDS = 0.85
TRIALS = 5


class MeasurementCancelled(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AudioLatencySample:
    latency_ms: float | None
    threshold: float
    baseline_rms: float
    peak_rms: float


@dataclass(frozen=True, slots=True)
class AudioLatencySummary:
    instrument: str
    samples_ms: tuple[float, ...]
    p50_ms: float
    p95_ms: float
    jitter_ms: float
    failed_samples: int
    speaker_name: str
    measured_at: float

    @property
    def quality(self) -> str:
        if len(self.samples_ms) < 3:
            return "Low confidence"
        if self.jitter_ms <= 8:
            return "Stable"
        if self.jitter_ms <= 20:
            return "Variable"
        return "High jitter"


def audio_latency_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home())) / "BPSR MIDI Lite"
    else:
        base = Path.home() / ".config" / "bpsr-midi-lite"
    base.mkdir(parents=True, exist_ok=True)
    return base / "bpsr_audio_latency.json"


def save_audio_latency_summary(summary: AudioLatencySummary) -> None:
    path = audio_latency_path()
    payload: dict[str, object] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            payload = {}
    payload[summary.instrument] = {
        "samples_ms": list(summary.samples_ms),
        "p50_ms": summary.p50_ms,
        "p95_ms": summary.p95_ms,
        "jitter_ms": summary.jitter_ms,
        "failed_samples": summary.failed_samples,
        "speaker_name": summary.speaker_name,
        "measured_at": summary.measured_at,
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def load_audio_latency_summary(instrument: str) -> AudioLatencySummary | None:
    path = audio_latency_path()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        item = raw.get(instrument) if isinstance(raw, dict) else None
        if not isinstance(item, dict):
            return None
        values = tuple(float(value) for value in item.get("samples_ms", []))
        return AudioLatencySummary(
            instrument=instrument,
            samples_ms=values,
            p50_ms=float(item.get("p50_ms", 0.0)),
            p95_ms=float(item.get("p95_ms", 0.0)),
            jitter_ms=float(item.get("jitter_ms", 0.0)),
            failed_samples=int(item.get("failed_samples", 0)),
            speaker_name=str(item.get("speaker_name", "Unknown")),
            measured_at=float(item.get("measured_at", 0.0)),
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _mono_level(data: np.ndarray) -> np.ndarray:
    values = np.asarray(data, dtype=np.float64)
    if values.ndim == 1:
        return np.abs(values)
    if values.ndim != 2 or values.shape[0] == 0:
        return np.empty(0, dtype=np.float64)
    # Windows/WASAPI has known single-channel issues in SoundCard. Record all
    # available channels, then use the strongest channel at each sample.
    return np.max(np.abs(values), axis=1)


def _moving_rms(values: np.ndarray, window: int) -> np.ndarray:
    if values.size == 0:
        return values
    window = max(1, min(int(window), int(values.size)))
    squared = values * values
    kernel = np.ones(window, dtype=np.float64) / window
    return np.sqrt(np.convolve(squared, kernel, mode="same"))


def detect_audio_onset(
    samples: np.ndarray,
    sample_rate: int,
    baseline_frames: int,
) -> AudioLatencySample:
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    mono = _mono_level(samples)
    if mono.size <= baseline_frames or baseline_frames < 32:
        return AudioLatencySample(None, 0.0, 0.0, float(mono.max()) if mono.size else 0.0)

    window = max(16, round(sample_rate * 0.004))
    envelope = _moving_rms(mono, window)
    baseline = envelope[:baseline_frames]
    median = float(np.median(baseline))
    p95 = float(np.percentile(baseline, 95))
    p99 = float(np.percentile(baseline, 99))
    mad = float(np.median(np.abs(baseline - median)))
    threshold = max(0.0015, p99 * 1.8, median + max(0.001, mad * 10.0), p95 + 0.001)
    after = envelope[baseline_frames:]
    if after.size == 0:
        return AudioLatencySample(None, threshold, median, float(envelope.max()))

    above = after > threshold
    # Demand a short sustained rise rather than one noisy sample. Four ms is
    # short enough for a note attack but rejects most single-frame glitches.
    required = max(2, round(sample_rate * 0.004))
    run = 0
    onset_index: int | None = None
    for index, is_above in enumerate(above):
        run = run + 1 if bool(is_above) else 0
        if run >= required:
            onset_index = index - required + 1
            break
    if onset_index is None:
        return AudioLatencySample(None, threshold, median, float(after.max()))

    latency_ms = onset_index * 1000.0 / sample_rate
    return AudioLatencySample(latency_ms, threshold, median, float(after.max()))


def summarize_latency(
    instrument: str,
    samples: list[AudioLatencySample],
    speaker_name: str,
) -> AudioLatencySummary:
    valid = sorted(sample.latency_ms for sample in samples if sample.latency_ms is not None)
    if not valid:
        return AudioLatencySummary(
            instrument=instrument,
            samples_ms=(),
            p50_ms=0.0,
            p95_ms=0.0,
            jitter_ms=0.0,
            failed_samples=len(samples),
            speaker_name=speaker_name,
            measured_at=time.time(),
        )
    p50 = float(statistics.median(valid))
    p95_index = max(0, min(len(valid) - 1, math.ceil(len(valid) * 0.95) - 1))
    p95 = float(valid[p95_index])
    jitter = float(p95 - p50)
    return AudioLatencySummary(
        instrument=instrument,
        samples_ms=tuple(float(value) for value in valid),
        p50_ms=p50,
        p95_ms=p95,
        jitter_ms=jitter,
        failed_samples=len(samples) - len(valid),
        speaker_name=speaker_name,
        measured_at=time.time(),
    )


def _check_cancel(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise MeasurementCancelled("Studio audio-latency measurement cancelled.")


def _collect_frames(
    recorder: Any,
    wanted: int,
    cancel_event: threading.Event | None = None,
) -> np.ndarray:
    chunks: list[np.ndarray] = []
    collected = 0
    empty_reads = 0
    while collected < wanted:
        _check_cancel(cancel_event)
        request = min(READ_FRAMES, wanted - collected)
        data = np.asarray(recorder.record(numframes=request))
        if data.size == 0 or data.shape[0] == 0:
            empty_reads += 1
            if empty_reads > 30:
                break
            if cancel_event is not None:
                if cancel_event.wait(0.003):
                    _check_cancel(cancel_event)
            else:
                time.sleep(0.003)
            continue
        empty_reads = 0
        chunks.append(data)
        collected += int(data.shape[0])
    if not chunks:
        return np.empty((0, 2), dtype=np.float64)
    return np.concatenate(chunks, axis=0)


def _measure_trial(
    recorder: Any,
    sender: wi.WindowsKeySender,
    key: str,
    hold_ms: int,
    sample_rate: int,
    cancel_event: threading.Event | None = None,
) -> AudioLatencySample:
    baseline_wanted = round(sample_rate * BASELINE_SECONDS)
    baseline = _collect_frames(recorder, baseline_wanted, cancel_event)
    _check_cancel(cancel_event)
    if baseline.shape[0] < max(128, baseline_wanted // 3):
        return AudioLatencySample(None, 0.0, 0.0, 0.0)

    # Flush whatever WASAPI already has buffered immediately before dispatch.
    try:
        pending = np.asarray(recorder.record(numframes=None))
        if pending.size and pending.shape[0]:
            baseline = np.concatenate((baseline, pending), axis=0)
    except Exception:
        pass
    _check_cancel(cancel_event)
    baseline_frames = int(baseline.shape[0])

    sender.key_down(key)
    try:
        hold_seconds = max(0.030, hold_ms / 1000.0)
        if cancel_event is not None:
            if cancel_event.wait(hold_seconds):
                _check_cancel(cancel_event)
        else:
            time.sleep(hold_seconds)
    finally:
        sender.key_up(key)
    _check_cancel(cancel_event)

    post = _collect_frames(recorder, round(sample_rate * CAPTURE_SECONDS), cancel_event)
    if post.size == 0:
        return AudioLatencySample(None, 0.0, 0.0, 0.0)
    combined = np.concatenate((baseline, post), axis=0)
    return detect_audio_onset(combined, sample_rate, baseline_frames)


def measure_game_audio_latency(
    instrument: str,
    *,
    input_backend: str = "scan",
    trials: int = TRIALS,
    hold_ms: int = 120,
    target_process_id: int | None = None,
    progress: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> AudioLatencySummary:
    if os.name != "nt":
        raise RuntimeError("Studio game-audio latency measurement is Windows-only.")
    if instrument not in {"keyboard", "guitar", "bass"}:
        raise ValueError("instrument must be keyboard, guitar, or bass")
    try:
        import soundcard as sc
    except ImportError as exc:
        raise RuntimeError("Studio loopback runtime is unavailable in this build.") from exc

    speaker = sc.default_speaker()
    if speaker is None:
        raise RuntimeError("Windows has no default output speaker to monitor.")
    try:
        loopback = sc.get_microphone(str(speaker.name), include_loopback=True)
    except Exception as exc:
        raise RuntimeError(
            "Could not open the default speaker as a WASAPI loopback input."
        ) from exc

    key = "q" if instrument == "bass" else "a"
    sender = wi.WindowsKeySender(input_backend)
    samples: list[AudioLatencySample] = []
    try:
        with loopback.recorder(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCKSIZE,
        ) as recorder:
            for index in range(max(1, int(trials))):
                _check_cancel(cancel_event)
                if target_process_id is not None and wi.foreground_process_id() != target_process_id:
                    raise RuntimeError("BPSR lost focus during the audio timing test.")
                if progress:
                    progress(f"Audio latency sample {index + 1}/{trials}…")
                sample = _measure_trial(
                    recorder,
                    sender,
                    key,
                    hold_ms,
                    SAMPLE_RATE,
                    cancel_event,
                )
                samples.append(sample)
                if cancel_event is not None:
                    if cancel_event.wait(0.20):
                        _check_cancel(cancel_event)
                else:
                    time.sleep(0.20)
    finally:
        sender.release_all()

    _check_cancel(cancel_event)
    summary = summarize_latency(instrument, samples, str(speaker.name))
    save_audio_latency_summary(summary)
    return summary


def summary_text(summary: AudioLatencySummary) -> str:
    if not summary.samples_ms:
        return (
            "No reliable instrument attack was detected. Make BPSR instrument audio loud, "
            "mute music/streams/Discord sounds, and try again in a quiet in-game area."
        )
    return (
        f"Observed input→loopback attack: p50 {summary.p50_ms:.1f} ms • "
        f"p95 {summary.p95_ms:.1f} ms • jitter {summary.jitter_ms:.1f} ms • "
        f"{len(summary.samples_ms)}/{len(summary.samples_ms) + summary.failed_samples} detected • "
        f"{summary.quality}. This is diagnostic only; it is not automatically subtracted from MIDI timing."
    )


def _install_ui(app_module: Any) -> None:
    app_class = app_module.App
    if getattr(app_class, "_studio_audio_latency_ui_installed", False):
        return
    original_build = app_class._build_ui
    original_instrument_changed = app_class._instrument_changed
    original_poll_f10 = app_class._poll_f10
    original_on_close = app_class._on_close

    def sync(self: Any) -> None:
        if not hasattr(self, "_studio_latency_var"):
            return
        saved = load_audio_latency_summary(self._instrument_code())
        self._studio_latency_var.set(
            summary_text(saved) if saved is not None else "No Studio audio-latency measurement saved for this instrument."
        )

    def pump_messages(self: Any) -> None:
        messages = getattr(self, "_studio_latency_messages", None)
        if messages is None:
            return
        try:
            while True:
                kind, payload = messages.get_nowait()
                if kind == "text":
                    self._studio_latency_var.set(str(payload))
                elif kind == "status":
                    self.status_var.set(str(payload))
                elif kind == "done":
                    self._studio_latency_running = False
                    self._studio_latency_button.configure(state="normal")
        except queue.Empty:
            pass
        try:
            self.after(80, lambda: pump_messages(self))
        except Exception:
            pass

    def build_ui(self: Any) -> None:
        original_build(self)
        panel = getattr(self, "_calibration_panel", None)
        if panel is None:
            return
        self._studio_latency_var = app_module.tk.StringVar(master=self)
        self._studio_latency_messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self._studio_latency_cancel_event = threading.Event()
        self._studio_latency_thread: threading.Thread | None = None
        self._studio_latency_running = False
        self._studio_latency_button = app_module.ttk.Button(
            panel,
            text="Measure game-audio latency (Studio)",
            command=lambda: start_measurement(self),
        )
        self._studio_latency_button.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
        app_module.ttk.Label(
            panel,
            textvariable=self._studio_latency_var,
            style="Hint.TLabel",
            wraplength=850,
            justify="left",
        ).grid(row=4, column=2, columnspan=5, sticky="w", padx=(10, 0), pady=(10, 0))
        app_module.ttk.Label(
            panel,
            text=(
                "For a clean measurement, mute BGM/streams/Discord sounds and use a quiet in-game area. "
                "F10 cancels this test. This uses Windows WASAPI loopback only; it does not inspect BPSR "
                "memory or network traffic."
            ),
            style="Hint.TLabel",
            wraplength=1050,
            justify="left",
        ).grid(row=5, column=0, columnspan=7, sticky="w", pady=(5, 0))
        sync(self)
        self.after(80, lambda: pump_messages(self))

    def instrument_changed(self: Any) -> None:
        original_instrument_changed(self)
        if not bool(getattr(self, "_studio_latency_running", False)):
            sync(self)

    def start_measurement(self: Any) -> None:
        if self.player.is_playing:
            self.status_var.set("Stop playback before measuring Studio game-audio latency.")
            return
        if bool(getattr(self, "_studio_latency_running", False)):
            self.status_var.set("Studio game-audio latency measurement is already running.")
            return

        # Capture every Tk-backed option on the main thread. The worker below
        # performs no Tk reads/writes; it communicates through a thread-safe queue.
        instrument = self._instrument_code()
        input_backend = self._input_backend_code()
        messages = self._studio_latency_messages
        cancel_event = self._studio_latency_cancel_event
        cancel_event.clear()
        self._studio_latency_running = True
        self._studio_latency_button.configure(state="disabled")
        self._studio_latency_var.set(
            "Starting in 3 seconds — focus BPSR now. Keep other desktop audio quiet. F10 cancels."
        )

        def worker() -> None:
            try:
                for remaining in (3, 2, 1):
                    messages.put(("text", f"Starting in {remaining}… focus BPSR and keep other audio quiet. F10 cancels."))
                    if cancel_event.wait(1.0):
                        raise MeasurementCancelled("Studio audio-latency measurement cancelled.")
                target_pid = wi.foreground_process_id()
                if target_pid is None or target_pid == os.getpid():
                    raise RuntimeError("BPSR was not focused when the latency test started.")

                def report(message: str) -> None:
                    messages.put(("text", message))

                result = measure_game_audio_latency(
                    instrument,
                    input_backend=input_backend,
                    target_process_id=target_pid,
                    progress=report,
                    cancel_event=cancel_event,
                )
                messages.put(("text", summary_text(result)))
                messages.put(("status", "Studio audio-latency measurement saved locally."))
            except MeasurementCancelled:
                messages.put(("text", "Studio game-audio latency measurement cancelled. All injected keys were released."))
                messages.put(("status", "Studio audio-latency measurement cancelled."))
            except Exception as exc:
                messages.put(("text", f"Measurement unavailable: {exc}"))
                messages.put(("status", "Studio audio-latency measurement did not complete."))
            finally:
                messages.put(("done", None))

        thread = threading.Thread(
            target=worker,
            daemon=True,
            name="bpsr-studio-audio-latency",
        )
        self._studio_latency_thread = thread
        thread.start()

    def poll_f10(self: Any) -> None:
        if bool(getattr(self, "_studio_latency_running", False)):
            pressed = app_module.f10_is_pressed()
            if pressed and not self._last_f10:
                self._studio_latency_cancel_event.set()
                self._studio_latency_messages.put(("text", "Cancelling Studio game-audio latency measurement…"))
        original_poll_f10(self)

    def on_close(self: Any) -> None:
        cancel_event = getattr(self, "_studio_latency_cancel_event", None)
        if cancel_event is not None:
            cancel_event.set()
        thread = getattr(self, "_studio_latency_thread", None)
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)
        original_on_close(self)

    app_class._build_ui = build_ui
    app_class._instrument_changed = instrument_changed
    app_class._poll_f10 = poll_f10
    app_class._on_close = on_close
    app_class._studio_audio_latency_ui_installed = True


def install_studio_audio_latency(app_module: Any) -> None:
    _install_ui(app_module)
