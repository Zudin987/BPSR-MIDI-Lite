"""Aligned MIDI parts and a self-contained arrangement that can be reopened."""
from __future__ import annotations

import bisect
import json
import re
import shutil
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .arrange import ArrangementSettings, PARTS, arrange
from .music import BeatMap, MasterSong, MusicEvent
from .storage import atomic_json, read_json

PPQ = 960
PART_NAMES = {"piano": "Piano", "guitar": "Guitar", "bass": "Bass", "drums": "Drum"}
PROGRAMS = {"piano": 0, "guitar": 24, "bass": 33, "drums": 0}
CHANNELS = {"piano": 0, "guitar": 1, "bass": 2, "drums": 9}
SOURCE_FIELDS = {"input_mode", "provider", "provider_id", "title", "artist", "album",
                 "duration_seconds", "isrc", "release_date", "store_url", "acquisition", "audio_sha256"}


def safe_name(title: str) -> str:
    result = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")[:90] or "Song"
    if result.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1,10)), *(f"LPT{i}" for i in range(1,10))}:
        result = "Song_" + result
    return result


def source_record(value: dict | None, fallback_title: str = "") -> dict:
    """Keep useful acquisition provenance without paths, credentials or arbitrary data."""
    source = value if isinstance(value, dict) else {}
    result = {"input_mode": "provider" if source.get("input_mode") == "provider" else "manual"}
    for key in SOURCE_FIELDS - {"input_mode"}:
        item = source.get(key)
        if item is None:
            continue
        if key == "duration_seconds":
            try:
                number = float(item)
            except (TypeError, ValueError):
                continue
            if 0 <= number <= 1800:
                result[key] = number
            continue
        text = " ".join(str(item).split())[:1000 if key == "store_url" else 240]
        if text:
            result[key] = text
    if "title" not in result and fallback_title:
        result["title"] = " ".join(str(fallback_title).split())[:240]
    return result


class MidiClock:
    def __init__(self, beats: BeatMap):
        # A tempo map is for MIDI transport; an unknown analysis BPM remains
        # None in the manifest. Tick conversion never discards leading silence.
        initial = int(round(60_000_000/(beats.bpm or 120)))
        points = [(0.0, max(1, min(0xffffff, initial)))]
        if beats.confidence >= .65:
            for start, end in zip(beats.beats, beats.beats[1:]):
                tempo = max(1, min(0xffffff, round((end-start)*1_000_000)))
                if start == 0:
                    points[0] = (0.0, tempo)
                else:
                    points.append((start, tempo))
        self.points = points
        self.starts = [p[0] for p in points]
        self.ticks = [0.0]
        for (start, tempo), (next_start, _) in zip(points, points[1:]):
            self.ticks.append(self.ticks[-1] + (next_start-start)*1_000_000/tempo*PPQ)

    def tick(self, seconds: float) -> int:
        index = max(0, bisect.bisect_right(self.starts, seconds)-1)
        start, tempo = self.points[index]
        return round(self.ticks[index]+(seconds-start)*1_000_000/tempo*PPQ)


def write_midi(path: Path, parts: dict[str, list[MusicEvent]], beats: BeatMap, duration: float) -> None:
    import mido
    clock = MidiClock(beats)
    midi = mido.MidiFile(type=1, ticks_per_beat=PPQ)
    tempo_track = mido.MidiTrack()
    midi.tracks.append(tempo_track)
    tempo_track.append(mido.MetaMessage("track_name", name="BPSR master timeline"))
    previous = 0
    for (start, tempo) in clock.points:
        tick = clock.tick(start)
        tempo_track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=tick-previous))
        previous = tick
    tempo_track.append(mido.MetaMessage("end_of_track", time=max(0, clock.tick(duration)-previous)))
    for part in PARTS:
        if part not in parts:
            continue
        track = mido.MidiTrack()
        midi.tracks.append(track)
        # Band Arranger v4 already locks "melody" to Piano and GM guitar/bass
        # programs to their authored roles. No new contract needed in Lite.
        label = "Piano melody and accompaniment" if part == "piano" else PART_NAMES[part]
        track.append(mido.MetaMessage("track_name", name=label))
        track.append(mido.Message("program_change", channel=CHANNELS[part], program=PROGRAMS[part]))
        events = []
        for event in parts[part]:
            if event.pitch is None:
                raise ValueError("Export requires a fitted pitch or mapped drum pad")
            on = max(0, clock.tick(event.start))
            off = max(on+1, clock.tick(event.end))
            events.extend([(on, 1, mido.Message("note_on", channel=CHANNELS[part], note=event.pitch, velocity=event.velocity)),
                           (off, 0, mido.Message("note_off", channel=CHANNELS[part], note=event.pitch, velocity=0))])
        previous = 0
        for tick, _, message in sorted(events, key=lambda x: (x[0], x[1], x[2].note)):
            message.time = tick-previous
            track.append(message)
            previous = tick
        track.append(mido.MetaMessage("end_of_track", time=max(0, clock.tick(duration)-previous)))
    path.parent.mkdir(parents=True, exist_ok=True)
    midi.save(str(path))


def export_arrangement(target: Path, title: str, master: MasterSong, arrangement: dict,
                       settings: ArrangementSettings, job: Path | None = None,
                       source_metadata: dict | None = None) -> Path:
    name = safe_name(title)
    target.mkdir(parents=True, exist_ok=True)
    staging = target / (".export_" + uuid.uuid4().hex)
    staging.mkdir()
    destination = target / name
    if destination.exists():
        destination = target / (name + "_" + uuid.uuid4().hex[:8])
    try:
        parts = arrangement["parts"]
        filenames = {part: f"{name} - {PART_NAMES[part]}.mid" for part in PARTS}
        filenames["full"] = f"{name} - Full Band.mid"
        for part in PARTS:
            write_midi(staging / filenames[part], {part: parts[part]}, master.beat_map, master.duration)
        write_midi(staging / filenames["full"], parts, master.beat_map, master.duration)
        record = {
            "schema_version": 1, "title": title, "source_audio_sha256": master.source_sha256,
            "source": source_record(source_metadata, title),
            "created_utc": datetime.now(timezone.utc).isoformat(), "settings": asdict(settings),
            "bpm": master.beat_map.bpm, "beat_map": asdict(master.beat_map),
            "melody_assignment": arrangement["melody_assignment"], "summary": arrangement["summary"],
            "providers": master.provenance, "warnings": master.warnings,
            "parts": {p: [e.to_dict() for e in events] for p, events in parts.items()},
            "removed_notes": arrangement["removed"], "drum_profile": arrangement["drum_profile"],
            "bpsr_arranger_version": arrangement["arranger_version"], "band_arranger_contract": 4,
            "master_song": master.to_dict(), "cache_job": str(job) if job else None,
            "files": filenames,
        }
        atomic_json(staging / f"{name} - Arrangement.json", record)
        staging.rename(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return destination / f"{name} - Arrangement.json"


def reopen(path: Path, settings: ArrangementSettings, output: Path, drum_profile: dict | None = None) -> Path:
    record = read_json(path)
    if record.get("schema_version") != 1:
        raise ValueError("Unsupported arrangement version")
    master = MasterSong.from_dict(record["master_song"])
    result = arrange(master, settings, drum_profile or record["drum_profile"])
    return export_arrangement(output, record["title"], master, result, settings,
                              source_metadata=record.get("source"))


def copy_export(path: Path, folder: Path) -> Path:
    record = read_json(path)
    destination = folder / safe_name(record["title"])
    if destination.exists():
        destination = folder / (destination.name + "_" + uuid.uuid4().hex[:8])
    destination.mkdir(parents=True)
    try:
        for filename in [*record["files"].values(), path.name]:
            if Path(filename).name != filename:
                raise ValueError("Invalid export filename")
            shutil.copy2(path.parent / filename, destination / filename)
    except Exception:
        shutil.rmtree(destination)
        raise
    return destination
