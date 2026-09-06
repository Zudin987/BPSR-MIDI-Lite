"""Model-independent musical evidence, in seconds on the original audio clock."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = 1
SOURCES = {"vocals", "piano", "guitar", "bass", "drums", "other"}
DRUM_ROLES = {"KICK", "SNARE", "CLOSED_HAT", "OPEN_HAT", "CRASH", "RIDE", "TOM", "PERCUSSION"}
ROLES = DRUM_ROLES | {
    "MAIN_MELODY", "MELODY", "RIFF", "HARMONY", "BASS", "RHYTHM", "DECORATION",
}


def finite(value: float, label: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


@dataclass(slots=True)
class MusicEvent:
    source: str
    role: str
    start: float
    end: float
    pitch: int | None
    velocity: int = 80
    confidence: float = 0.5
    engine: str = "unknown"
    tags: set[str] = field(default_factory=set)
    event_id: str = ""
    original_confidence: float | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.start = finite(self.start, "start")
        self.end = finite(self.end, "end")
        self.confidence = finite(self.confidence, "confidence")
        if self.source not in SOURCES or self.role not in ROLES:
            raise ValueError(f"Unknown musical source/role: {self.source}/{self.role}")
        if not 0 <= self.start < self.end or not 0 <= self.confidence <= 1:
            raise ValueError("Invalid event timing or confidence")
        if not isinstance(self.velocity, int) or not 1 <= self.velocity <= 127:
            raise ValueError("Velocity must be an integer in 1..127")
        if self.pitch is not None and (not isinstance(self.pitch, int) or not 0 <= self.pitch <= 127):
            raise ValueError("Pitch must be an integer in 0..127")
        if self.pitch is None and self.role not in DRUM_ROLES:
            raise ValueError("Pitched events require a pitch")
        if self.original_confidence is None:
            self.original_confidence = self.confidence
        if not 0 <= finite(self.original_confidence, "original confidence") <= 1:
            raise ValueError("Invalid original confidence")
        self.tags = set(self.tags)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["tags"] = sorted(self.tags)
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> MusicEvent:
        return cls(**value)


@dataclass(slots=True)
class BeatMap:
    bpm: float | None = None
    beats: list[float] = field(default_factory=list)
    downbeats: list[float] = field(default_factory=list)
    engine: str = "unavailable"
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if self.bpm is not None and not 1 <= finite(self.bpm, "BPM") <= 1000:
            raise ValueError("Invalid BPM")
        for name in ("beats", "downbeats"):
            values = [finite(x, name) for x in getattr(self, name)]
            if any(x < 0 for x in values) or any(b <= a for a, b in zip(values, values[1:])):
                raise ValueError(f"{name} must be strictly increasing and nonnegative")
            setattr(self, name, values)
        if not 0 <= finite(self.confidence, "beat confidence") <= 1:
            raise ValueError("Invalid beat confidence")


@dataclass(slots=True)
class MasterSong:
    source_sha256: str
    duration: float
    beat_map: BeatMap
    events: list[MusicEvent]
    provenance: dict[str, Any] = field(default_factory=dict)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "source_sha256": self.source_sha256, "duration": self.duration,
            "beat_map": asdict(self.beat_map), "events": [e.to_dict() for e in self.events],
            "provenance": self.provenance, "rejected": self.rejected, "warnings": self.warnings,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> MasterSong:
        if value.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported musical map version")
        duration = finite(value["duration"], "duration")
        if duration <= 0:
            raise ValueError("Audio duration must be positive")
        events = [MusicEvent.from_dict(e) for e in value["events"]]
        if any(e.end > duration + 0.1 for e in events):
            raise ValueError("Musical events extend beyond the audio timeline")
        return cls(value["source_sha256"], duration, BeatMap(**value["beat_map"]), events,
                   value.get("provenance", {}), value.get("rejected", []), value.get("warnings", []))
