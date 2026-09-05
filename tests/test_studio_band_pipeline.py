"""Exercise the full orchestrator with deterministic synthetic provider boundaries."""
from pathlib import Path

import pytest

from studio_band.arrange import ArrangementSettings
from studio_band.music import MusicEvent
from studio_band.pipeline import BandPipeline, ConversionSettings
from studio_band.protocol import Cancelled, StageError
from studio_band.runtime import RuntimeManager
from studio_band.storage import JobStore, read_json


class FixtureRuntimes(RuntimeManager):
    def available(self, name):
        return name != "drums"

    def fingerprint(self, provider):
        return "fixture-v1:" + provider


class FixtureClient:
    calls = []
    fail = set()

    def __init__(self, *args):
        pass

    def call(self, provider, operation, payload, **kwargs):
        self.calls.append((provider, payload.get("source")))
        if provider in self.fail:
            raise StageError(provider, "Synthetic missing model")
        common = {"provenance": {"provider": provider, "version": "fixture", "device": "cpu"}}
        if provider == "demucs":
            folder = Path(payload["output"])
            stems = {}
            for name in ("vocals", "piano", "guitar", "bass", "drums", "other"):
                target = folder / (name+".wav")
                target.write_bytes(b"Synthetic isolated audio: " + name.encode())
                stems[name] = str(target)
            return {**common, "stems": stems}
        if provider in {"beat_this", "beat_dsp"}:
            return {**common, "beat_map": {"bpm": 120, "beats": [0, .5, 1, 1.5, 2], "downbeats": [0], "engine": provider, "confidence": .8}}
        source = payload.get("source", "drums" if provider == "drums_dsp" else "piano")
        if provider == "mr_mt3":
            source = "guitar"
        pitch = {"vocals": 74, "piano": 60, "guitar": 64, "bass": 36, "other": 67, "drums": None}[source]
        role = "KICK" if source == "drums" else "MAIN_MELODY" if source == "vocals" else "BASS" if source == "bass" else "HARMONY"
        event = MusicEvent(source, role, 1, 1.5, pitch, 80, .85, provider)
        return {**common, "events": [event.to_dict()]}


class FixturePipeline(BandPipeline):
    def _prepare(self, original, job, cancel, report):
        path = job / "prepared.wav"
        path.write_bytes(b"Synthetic prepared audio")
        return path, 3.0

    @staticmethod
    def _check_stem_timeline(stems, duration):
        assert len(stems) == 6


def pipeline(tmp_path):
    FixtureClient.calls, FixtureClient.fail = [], set()
    return FixturePipeline(JobStore(tmp_path / "cache"), FixtureRuntimes(tmp_path / "runtime"), FixtureClient,
                           ffmpeg=Path("synthetic-ffmpeg"))


def test_complete_pipeline_outputs_all_files_and_reuses_expensive_work(tmp_path):
    source = tmp_path / "song.mp3"
    source.write_bytes(b"legal synthetic fixture")
    converter = pipeline(tmp_path)
    output = converter.convert(source)
    record = read_json(output)
    assert set(record["files"]) == {"piano", "guitar", "bass", "drums", "full"}
    assert record["source"] == {"input_mode": "manual", "title": "song"}
    assert {p for p,_ in FixtureClient.calls} >= {"demucs", "transkun", "basic_pitch", "beat_this", "drums_dsp", "mr_mt3"}
    calls = list(FixtureClient.calls)
    converter.convert(source, ConversionSettings(arrangement=ArrangementSettings(main_melody="guitar")))
    assert FixtureClient.calls == calls
    reopened = converter.rearrange(output, ArrangementSettings(main_melody="guitar"))
    assert FixtureClient.calls == calls
    assert read_json(reopened)["melody_assignment"]["part"] == "guitar"


def test_provider_metadata_names_output_without_exposing_cached_filename(tmp_path):
    source = tmp_path / ("a" * 64 + ".flac")
    source.write_bytes(b"legal synthetic fixture")
    converter = pipeline(tmp_path)
    output = converter.convert(source, source_metadata={
        "input_mode": "provider", "provider": "bandcamp_collection", "provider_id": "owned-7",
        "title": "Actual Song", "artist": "Artist", "password": "must-not-leak",
    })
    record = read_json(output)
    assert record["title"] == "Actual Song" and output.parent.name == "Actual Song"
    assert record["source"]["provider_id"] == "owned-7"
    assert "must-not-leak" not in output.read_text(encoding="utf-8")


def test_missing_specialists_use_recorded_fallbacks(tmp_path):
    source = tmp_path / "song.wav"
    source.write_bytes(b"synthetic")
    converter = pipeline(tmp_path)
    FixtureClient.fail = {"transkun", "beat_this", "mr_mt3"}
    output = converter.convert(source, ConversionSettings(install_models=False))
    record = read_json(output)
    fallback = record["providers"]["fallbacks"]
    assert any(f["provider"] == "transkun" and f["replacement"] == "basic_pitch" for f in fallback)
    assert any(f["provider"] == "beat_this" and f["replacement"] == "beat_dsp" for f in fallback)
    assert any(f["provider"] == "mr_mt3" and f["replacement"] is None for f in fallback)
    assert len(record["parts"]["piano"]) > 0


def test_separator_failure_is_actionable_and_does_not_fake_stems(tmp_path):
    source = tmp_path / "song.wav"
    source.write_bytes(b"synthetic")
    converter = pipeline(tmp_path)
    FixtureClient.fail = {"demucs"}
    with pytest.raises(StageError, match="six-stem separator"):
        converter.convert(source)
    assert not list(tmp_path.rglob("* - Full Band.mid"))


def test_cancelled_job_does_not_publish_output(tmp_path):
    import threading
    source = tmp_path / "song.wav"
    source.write_bytes(b"synthetic")
    converter = pipeline(tmp_path)
    cancel = threading.Event()
    def progress(stage):
        if stage == "Transcribing Guitar":
            cancel.set()
    with pytest.raises(Cancelled):
        converter.convert(source, cancel=cancel, progress=progress)
    assert not list(tmp_path.rglob("* - Full Band.mid"))
    assert list(tmp_path.rglob("complete.json"))  # successful expensive stages survive
