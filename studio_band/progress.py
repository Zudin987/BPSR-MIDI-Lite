"""Structured, backwards-compatible progress for the Audio -> Band pipeline."""
from __future__ import annotations

from collections import OrderedDict
from typing import Any, Callable


# Setup is intentionally a completed-work estimate, not a fabricated download
# percentage. Exact byte progress is carried separately when a downloader
# exposes Content-Length.
SETUP_END = 18.0
PIPELINE_STAGES = OrderedDict(
    (
        ("prepare_audio", (18.0, 23.0, "Preparing audio")),
        ("separate", (23.0, 40.0, "Separating stems")),
        ("beat", (40.0, 47.0, "Detecting beat and timing")),
        ("vocals", (47.0, 54.0, "Transcribing vocal melody")),
        ("piano", (54.0, 62.0, "Transcribing Piano")),
        ("guitar", (62.0, 69.0, "Transcribing Guitar")),
        ("bass", (69.0, 76.0, "Transcribing Bass")),
        ("other", (76.0, 81.0, "Transcribing other musical material")),
        ("drums", (81.0, 87.0, "Detecting Drums")),
        ("cross_check", (87.0, 93.0, "Cross-checking musical evidence")),
        ("fusion", (93.0, 96.0, "Building musical map")),
        ("arrange", (96.0, 99.0, "Arranging for BPSR")),
        ("export", (99.0, 100.0, "Exporting MIDI")),
    )
)


class ProgressEvent(str):
    """A string for old callbacks, with metadata for the Studio UI.

    Existing callers that print or compare progress continue to work because
    this is a ``str`` subclass. The GUI can additionally use stage, activity,
    byte counts and the weighted overall completion value.
    """

    def __new__(
        cls,
        message: str,
        *,
        stage_id: str = "",
        phase: str = "",
        activity: str = "",
        overall: float | None = None,
        stage_fraction: float | None = None,
        indeterminate: bool = True,
        bytes_done: int | None = None,
        bytes_total: int | None = None,
    ) -> "ProgressEvent":
        clean = str(message).strip()
        value = str.__new__(cls, clean)
        value.message = clean
        value.stage_id = str(stage_id)
        value.phase = str(phase)
        value.activity = str(activity)
        value.overall = None if overall is None else max(0.0, min(100.0, float(overall)))
        value.stage_fraction = (
            None if stage_fraction is None else max(0.0, min(1.0, float(stage_fraction)))
        )
        value.indeterminate = bool(indeterminate)
        value.bytes_done = None if bytes_done is None else max(0, int(bytes_done))
        value.bytes_total = None if bytes_total is None else max(0, int(bytes_total))
        return value

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "stage_id": self.stage_id,
            "phase": self.phase,
            "activity": self.activity,
            "overall": self.overall,
            "stage_fraction": self.stage_fraction,
            "indeterminate": self.indeterminate,
            "bytes_done": self.bytes_done,
            "bytes_total": self.bytes_total,
        }

    def changed(self, **values: Any) -> "ProgressEvent":
        current = self.to_dict()
        current.update(values)
        return ProgressEvent(**current)


def as_progress_event(value: Any) -> ProgressEvent:
    if isinstance(value, ProgressEvent):
        return value
    if isinstance(value, dict):
        fields = {
            key: value.get(key)
            for key in (
                "message",
                "stage_id",
                "phase",
                "activity",
                "overall",
                "stage_fraction",
                "indeterminate",
                "bytes_done",
                "bytes_total",
            )
            if key in value
        }
        fields.setdefault("message", "")
        return ProgressEvent(**fields)
    return ProgressEvent(str(value))


def emit_progress(callback: Callable[[str], None] | None, message: str, **metadata: Any) -> None:
    if callback is not None:
        callback(ProgressEvent(message, **metadata))


def _activity_for(event: ProgressEvent, fallback: str = "processing") -> str:
    if event.activity:
        return event.activity
    text = event.message.casefold()
    if "no setup activity" in text or "no worker activity" in text or "waiting" in text:
        return "waiting"
    if "download" in text:
        return "download"
    if "install" in text or "runtime" in text or "environment" in text:
        return "install"
    if "cached" in text or "cache" in text:
        return "cache"
    if "export" in text or "saving" in text:
        return "disk"
    return fallback


class PipelineProgress:
    """Map real pipeline boundaries to monotonic weighted overall progress."""

    def __init__(self, callback: Callable[[str], None] | None):
        self.callback = callback
        self.last_overall = 0.0
        self.current_stage = ""

    def _send(self, event: ProgressEvent) -> ProgressEvent:
        if event.overall is not None:
            overall = max(self.last_overall, event.overall)
            self.last_overall = overall
            if overall != event.overall:
                event = event.changed(overall=overall)
        self.current_stage = event.stage_id or self.current_stage
        if self.callback is not None:
            self.callback(event)
        return event

    def setup(self, runtime_label: str, index: int, total: int, value: Any) -> ProgressEvent:
        event = as_progress_event(value)
        count = max(1, int(total))
        fraction = event.stage_fraction if event.stage_fraction is not None else 0.0
        overall = SETUP_END * (max(0, int(index)) + fraction) / count
        message = event.message or f"Preparing {runtime_label} runtime"
        if _activity_for(event, "install") == "waiting" and message.startswith("No setup activity"):
            message = f"Preparing {runtime_label} runtime — {message[0].lower() + message[1:]}"
        return self._send(
            ProgressEvent(
                message,
                stage_id="runtime_setup",
                phase="First-time setup",
                activity=_activity_for(event, "install"),
                overall=overall,
                stage_fraction=event.stage_fraction,
                indeterminate=event.indeterminate,
                bytes_done=event.bytes_done,
                bytes_total=event.bytes_total,
            )
        )

    def setup_ready(self, message: str = "Transcription runtime ready") -> ProgressEvent:
        return self._send(
            ProgressEvent(
                message,
                stage_id="runtime_setup",
                phase="First-time setup",
                activity="cache",
                overall=SETUP_END,
                stage_fraction=1.0,
                indeterminate=False,
            )
        )

    def stage(
        self,
        stage_id: str,
        message: str | None = None,
        *,
        activity: str = "processing",
        indeterminate: bool = True,
    ) -> ProgressEvent:
        start, _end, default = PIPELINE_STAGES[stage_id]
        return self._send(
            ProgressEvent(
                message or default,
                stage_id=stage_id,
                phase="Analyzing song",
                activity=activity,
                overall=start,
                stage_fraction=0.0,
                indeterminate=indeterminate,
            )
        )

    def detail(self, stage_id: str, value: Any, *, activity: str = "processing") -> ProgressEvent:
        event = as_progress_event(value)
        start, end, default = PIPELINE_STAGES[stage_id]
        overall = start
        if event.stage_fraction is not None:
            overall = start + (end - start) * event.stage_fraction
        resolved_activity = _activity_for(event, activity)
        message = event.message or default
        if resolved_activity == "waiting" and message.startswith("No worker activity"):
            message = f"{default} — {message[0].lower() + message[1:]}"
        return self._send(
            ProgressEvent(
                message,
                stage_id=stage_id,
                phase="Analyzing song",
                activity=resolved_activity,
                overall=overall,
                stage_fraction=event.stage_fraction,
                indeterminate=event.indeterminate,
                bytes_done=event.bytes_done,
                bytes_total=event.bytes_total,
            )
        )

    def complete(self, stage_id: str, message: str | None = None) -> ProgressEvent:
        _start, end, default = PIPELINE_STAGES[stage_id]
        return self._send(
            ProgressEvent(
                message or default,
                stage_id=stage_id,
                phase="Analyzing song",
                activity="complete",
                overall=end,
                stage_fraction=1.0,
                indeterminate=False,
            )
        )


def format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def format_bytes(value: int) -> str:
    amount = float(max(0, value))
    for suffix in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or suffix == "TB":
            digits = 0 if suffix == "B" or amount >= 100 else 1
            return f"{amount:.{digits}f} {suffix}"
        amount /= 1024
    return f"{amount:.1f} TB"


def progress_line(event: ProgressEvent, elapsed: float) -> str:
    parts = [event.message.rstrip(".\u2026 ") or "Working"]
    if event.bytes_done is not None:
        transferred = format_bytes(event.bytes_done)
        if event.bytes_total:
            ratio = min(100.0, event.bytes_done * 100.0 / event.bytes_total)
            transferred += f" / {format_bytes(event.bytes_total)} ({ratio:.0f}%)"
        parts.append(transferred)
    if event.overall is not None:
        parts.append(f"{event.overall:.0f}%")
    parts.append(format_elapsed(elapsed))
    return " \u00b7 ".join(parts)


def progress_context(event: ProgressEvent) -> str:
    activity = {
        "download": "Downloading",
        "install": "Installing components",
        "cpu": "CPU processing",
        "gpu": "GPU processing",
        "waiting": "Waiting; checking worker health",
        "cache": "Using cached components",
        "disk": "Writing files",
        "complete": "Stage complete",
        "processing": "Processing",
    }.get(event.activity, event.activity.replace("_", " ").title() if event.activity else "Processing")
    if event.phase == "First-time setup":
        return f"First-time setup \u2014 {activity}. Downloaded components are cached for future songs."
    if event.phase:
        return f"{event.phase} \u2014 {activity}."
    return activity + "."
