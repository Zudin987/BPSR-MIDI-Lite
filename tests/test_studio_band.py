from __future__ import annotations

import ast
import json
import os
import shutil
import sys
import threading
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import mido
import pytest

from studio_band.arrange import (ArrangementSettings, arrange, clean_drums, fit_contour,
                                 limit_sustained, load_drum_profile, melody_assignment, simplify_chords)
from studio_band.export import copy_export, export_arrangement, reopen, safe_name, write_midi
from studio_band.fusion import bass_contour, fuse, melody_contour, soft_align
from studio_band.music import BeatMap, MasterSong, MusicEvent
from studio_band.pipeline import BandPipeline, ConversionSettings
from studio_band.preview import preview_messages
from studio_band.progress import ProgressEvent
from studio_band.protocol import Cancelled, StageError, WorkerClient, run_process
from studio_band.runtime import Hardware, RuntimeManager, choose_separator
from studio_band.storage import JobStore, atomic_json, cache_key, file_hash, file_lock, read_json


def note(pitch=60, start=1.0, end=1.5, source="piano", role="HARMONY", confidence=.8, engine="specialist", event_id="n"):
    return MusicEvent(source, role, start, end, pitch, 85, confidence, engine, event_id=event_id)


def song(events):
    return MasterSong("a"*64, 5.0, BeatMap(120, [0, .5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5], [0, 2, 4], "test", .9), events)


@pytest.mark.parametrize("change", [{"start": float("nan")}, {"end": float("inf")}, {"start": -1}, {"end": .5}, {"pitch": 128}, {"confidence": 1.1}, {"pitch": None}, {"role": "TYPO"}])
def test_invalid_worker_events_are_rejected(change):
    values = note().to_dict()
    values.update(change)
    with pytest.raises(ValueError):
        MusicEvent.from_dict(values)


def test_event_and_master_json_round_trip_preserves_evidence():
    event = note()
    event.tags = {"riff", "uncertain"}
    event.evidence = {"amplitude": .87, "engines": ["first", "second"]}
    master = song([event])
    assert MasterSong.from_dict(json.loads(json.dumps(master.to_dict()))).to_dict() == master.to_dict()


def test_beat_map_rejects_unordered_or_nan_times():
    for beats in ([1, 0], [1, 1], [float("nan")]):
        with pytest.raises(ValueError):
            BeatMap(beats=beats)


def test_fusion_support_raises_confidence_without_unioning_false_notes():
    primary = [note(confidence=.65), note(pitch=102, source="guitar", confidence=.37, event_id="bad")]
    reference = [note(confidence=.8, engine="mr_mt3"), note(pitch=62, engine="mr_mt3")]
    result, removed = fuse(primary, reference, BeatMap())
    assert len(result) == 1
    assert result[0].confidence > .65
    assert result[0].original_confidence == .65
    assert result[0].evidence["agreement_engines"] == ["mr_mt3"]
    assert removed[0]["event"]["event_id"] == "bad"


def test_same_engine_duplicates_do_not_vote_and_missing_reference_is_not_veto():
    primary = note(confidence=.9)
    result, _ = fuse([primary], [replace(primary)]*20, BeatMap())
    unsupported, _ = fuse([primary], [], BeatMap())
    assert result[0].confidence <= unsupported[0].confidence
    assert result[0].confidence > .8


def test_timing_fusion_preserves_swing_and_grace_notes():
    beats = BeatMap(120, [0, .5, 1, 1.5], [], "beat_this", .8)
    offbeat = note(start=.331, end=.45)
    assert soft_align(offbeat, [], beats).start == .331
    grace = note(start=.493, end=.53)
    assert soft_align(grace, [], beats).start == .493
    near = note(start=1.019)
    aligned = soft_align(near, [note(start=1.008, engine="other")], beats)
    assert 1.0 < aligned.start < 1.019
    assert abs(aligned.start-near.start) <= .015


def test_vocal_contour_keeps_melody_and_cleans_weak_octave_glitch():
    events = [note(60, 0, .4, "vocals", confidence=.9), note(72, .4, .8, "vocals", confidence=.5, event_id="split"),
              note(61, .4, .5, "vocals", confidence=.2, event_id="breath"), note(67, 1, 1.4, "vocals", confidence=.95)]
    notes, removed = melody_contour(events)
    assert notes[0].pitch == 60
    assert all(e.role == "MAIN_MELODY" for e in notes)
    assert any(r["reason"] == "vocal_duplicate_or_harmonic" for r in removed)
    assert notes[-1].pitch == 67


def test_bass_rejects_upper_harmonic_and_remains_monophonic():
    events = [note(36, 1, 2, "bass", confidence=.8), note(48, 1, 1.9, "bass", confidence=.9),
              note(38, 1.5, 2.3, "bass", event_id="move")]
    notes, removed = bass_contour(events)
    assert [e.pitch for e in notes] == [36, 38]
    assert notes[0].end <= notes[1].start
    assert len(removed) == 1


def test_melody_assignment_avoids_busy_riff_and_override_wins():
    melody = [note(76, source="vocals", role="MAIN_MELODY")]
    parts = {"piano": [], "guitar": [note(64, role="RIFF") for _ in range(7)]}
    assert melody_assignment(melody, parts, ArrangementSettings())["part"] == "piano"
    assert melody_assignment(melody, parts, ArrangementSettings(main_melody="guitar"))["part"] == "guitar"


def test_chord_reduction_protects_inner_melody_and_chord_identity():
    chord = [note(p, event_id=str(p)) for p in (48, 55, 60, 64, 67, 71, 76)]
    chord.append(note(65, role="MAIN_MELODY", event_id="voice"))
    selected, removed = simplify_chords(chord, 4, "piano")
    assert len(selected) == 4
    assert "voice" in {e.event_id for e in selected}
    assert len({e.pitch%12 for e in selected}) == 4
    assert len(removed) == 4


def test_sustained_pressure_evicts_accompaniment_for_melody():
    events = [note(60, 0, 3, role="DECORATION", event_id="fill"), note(64, 0, 3, event_id="third"),
              note(67, 1, 2, role="MAIN_MELODY", event_id="voice")]
    selected, _ = limit_sustained(events, 2, .024)
    assert any(e.event_id == "voice" for e in selected)
    assert next(e for e in selected if e.event_id == "fill").end == 1
    for t in (0, .5, 1, 1.5, 2.1):
        assert sum(e.start <= t < e.end for e in selected) <= 2


def test_range_fitting_uses_octaves_and_preserves_bass_motion():
    events = [note(p, i*.5, i*.5+.3, "bass", event_id=str(i)) for i,p in enumerate((16, 18, 21, 23))]
    fitted = fit_contour(events, 28, 59)
    assert all(28 <= e.pitch <= 59 for e in fitted)
    assert all((a.pitch-b.pitch)%12 == 0 for a,b in zip(fitted, events))
    assert [b.pitch-a.pitch for a,b in zip(fitted, fitted[1:])] == [2, 3, 2]


def test_drum_cleanup_is_semantic_and_never_requires_octave_modes():
    profile = load_drum_profile()
    hits = [note(None, t, t+.07, "drums", "KICK", event_id=str(t)) for t in (1, 1.009, 1.015, 1.5)]
    result, removed = clean_drums(hits, profile)
    assert len(result) == 2 and len(removed) == 2
    assert all(60 <= e.pitch <= 83 for e in result)
    assert not any(profile[k] for k in ("high_octave", "low_octave", "page_switching"))


def test_drum_profile_invalid_pads_are_blocked(tmp_path):
    profile = load_drum_profile()
    profile["mapping"]["KICK"] = 84
    path = tmp_path / "drums.json"
    atomic_json(path, profile)
    with pytest.raises(ValueError, match="invalid pad"):
        load_drum_profile(path)


def test_full_arrangement_shares_other_harmony_and_keeps_vocal_owner():
    events = [note(p, source="other", event_id=f"other{p}") for p in (60,64,67)]
    events += [note(76, source="vocals", role="MAIN_MELODY", event_id="voice"), note(36, source="bass", role="BASS", event_id="bass")]
    result = arrange(song(events), ArrangementSettings(), load_drum_profile())
    owner = result["melody_assignment"]["part"]
    assert any(e.event_id == "voice" for e in result["parts"][owner])
    assert result["parts"]["piano"] and result["parts"]["guitar"] and result["parts"]["bass"]
    assert all(e.evidence.get("page", 1) == 1 for part in result["parts"].values() for e in part)


def test_exports_align_variable_tempo_and_keep_leading_silence(tmp_path):
    beats = BeatMap(120, [.4, .9, 1.45, 2.05, 2.55], [.4], "beat_this", .9)
    events = [note(60, 1.019, 1.38), note(64, 2.07, 2.4, event_id="second")]
    path = tmp_path / "song.mid"
    write_midi(path, {"piano": events, "guitar": events}, beats, 3)
    now, starts = 0.0, []
    for msg in mido.MidiFile(path):
        now += msg.time
        if msg.type == "note_on" and msg.velocity:
            starts.append(now)
    assert starts == pytest.approx([1.019, 1.019, 2.07, 2.07], abs=.002)
    assert now == pytest.approx(3, abs=.002)


def test_export_roundtrip_and_rearrangement_require_no_audio_or_workers(tmp_path):
    master = song([note(), note(72, source="vocals", role="MAIN_MELODY", event_id="v")])
    settings = ArrangementSettings()
    source = {"input_mode": "provider", "provider": "bandcamp_collection", "provider_id": "owned-1",
              "title": "My Song", "artist": "Artist", "acquisition": "owned_collection_download"}
    output = export_arrangement(tmp_path, "My Song", master, arrange(master, settings, load_drum_profile()),
                                settings, source_metadata=source)
    record = read_json(output)
    assert len(list(output.parent.glob("*.mid"))) == 5
    assert record["source_audio_sha256"] == "a"*64
    assert record["master_song"] == master.to_dict()
    moved = copy_export(output, tmp_path / "saved")
    shutil.rmtree(output.parent)
    opened = reopen(moved / output.name, ArrangementSettings(main_melody="guitar"), tmp_path / "new")
    assert read_json(opened)["melody_assignment"]["part"] == "guitar"
    assert read_json(opened)["master_song"] == record["master_song"]
    assert read_json(opened)["source"] == record["source"]


def test_generated_full_band_is_compatible_with_band_arranger_v4(tmp_path):
    import band_arranger
    import band_musical_sharing as v4
    import playback_adaptive as adaptive
    events = [note(60, event_id="p"), note(64, source="guitar", event_id="g"),
              note(36, source="bass", role="BASS", event_id="b"), note(None, source="drums", role="KICK", event_id="d")]
    master = song(events)
    arranged = arrange(master, ArrangementSettings(), load_drum_profile())
    path = tmp_path / "full.mid"
    write_midi(path, arranged["parts"], master.beat_map, master.duration)
    notes, *_ = me_extract(path)
    metadata = adaptive._match_metadata(notes, adaptive._collect_candidates(path))
    old = v4._original_split
    try:
        v4._original_split = band_arranger.split_band_notes
        split = v4.split_band_notes_shared(notes, metadata)
    finally:
        v4._original_split = old
    assert all(split[p] for p in ("keyboard", "guitar", "bass", "drums"))
    assert all(60 <= n.pitch <= 83 for n in split["drums"])


def me_extract(path):
    import midi_engine
    return midi_engine._extract_notes_and_pedal(path, False)


def test_cache_corruption_invalidates_stage_and_arrangement_options_are_separate(tmp_path):
    store = JobStore(tmp_path)
    key = cache_key("audio", "model", {"onset": .5})
    folder = tmp_path / "stems"
    audio = folder / key / "piano.wav"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"synthetic fixture")
    store.commit_stage(folder, key, {"stems": {"piano": str(audio)}}, [audio])
    assert store.cached(folder, key)
    audio.write_bytes(b"corrupt")
    assert store.cached(folder, key) is None
    assert key != cache_key("audio", "model-v2", {"onset": .5})


def test_active_jobs_are_not_cleaned_up(tmp_path):
    store = JobStore(tmp_path)
    source = tmp_path / "song.wav"
    source.write_bytes(b"synthetic")
    job = store.job(source, file_hash(source))
    with file_lock(tmp_path / (job.name + ".lock")):
        assert store.cleanup(days=-1) == 0
        assert job.exists()
    assert store.cleanup(days=-1) == 1


def test_worker_protocol_rejects_missing_and_mismatched_responses(tmp_path):
    script = tmp_path / "wrong.py"
    script.write_text("import json,sys\njson.dump({'protocol':1,'id':'wrong','status':'ok','result':{}},open(sys.argv[2],'w'))\n")
    client = WorkerClient(tmp_path / "requests", lambda _: [sys.executable, str(script)])
    with pytest.raises(StageError, match="incompatible"):
        client.call("x", "infer", {})


def test_worker_error_keeps_response_trace_and_process_stderr(tmp_path):
    script = tmp_path / "failed_worker.py"
    script.write_text(
        "import json,sys\n"
        "request=json.load(open(sys.argv[1]))\n"
        "sys.stderr.write('dependency warning from stderr\\n')\n"
        "json.dump({'protocol':1,'id':request['id'],'status':'error','error':"
        "{'message':'inference failed','details':'worker traceback'}},open(sys.argv[2],'w'))\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )
    client = WorkerClient(tmp_path / "requests", lambda _: [sys.executable, str(script)])
    with pytest.raises(StageError, match="inference failed") as failure:
        client.call("x", "infer", {})
    assert "worker traceback" in failure.value.details
    assert "dependency warning from stderr" in failure.value.details


def test_real_worker_entrypoint_capabilities_and_error_protocol(tmp_path):
    script = Path("studio_band_worker.py").resolve()
    client = WorkerClient(tmp_path, lambda _: [sys.executable, str(script)])
    assert client.call("basic_pitch", "capabilities", {})["provider"] == "basic_pitch"
    with pytest.raises(StageError, match="Unknown"):
        client.call("nonexistent", "infer", {})


def test_cancellation_terminates_real_subprocess():
    cancel = threading.Event()
    timer = threading.Timer(.15, cancel.set)
    timer.start()
    try:
        with pytest.raises(Cancelled):
            run_process([sys.executable, "-c", "import time; time.sleep(30)"], stage="test", cancel=cancel)
    finally:
        timer.cancel()


def test_nonzero_subprocess_retains_stderr_and_returns_immediately():
    with pytest.raises(StageError) as failure:
        run_process(
            [sys.executable, "-c", "import sys; print('setup stdout'); sys.stderr.write('ncls needs MSVC\\n'); raise SystemExit(7)"],
            stage="Runtime setup",
            timeout=5,
        )
    assert "setup stdout" in failure.value.details
    assert "[stderr]" in failure.value.details
    assert "ncls needs MSVC" in failure.value.details


def test_successful_subprocess_returns_unadorned_stdout():
    output = run_process(
        [sys.executable, "-c", "import sys; print('machine-readable'); sys.stderr.write('warning only\\n')"],
        stage="test",
        timeout=5,
    )
    assert output == "machine-readable\n"


def test_live_subprocess_emits_nonfatal_stall_warning():
    updates = []
    run_process(
        [sys.executable, "-c", "import time; time.sleep(.25)"],
        stage="Runtime setup",
        progress=updates.append,
        timeout=2,
        stall_warning_after=.05,
    )
    assert any("no new progress report" in update for update in updates)
    assert any("setup worker process is still running" in update for update in updates)
    assert any(isinstance(update, ProgressEvent) and update.activity == "waiting" for update in updates)


def test_stall_warning_preserves_last_real_operation_and_device(tmp_path):
    progress_path = tmp_path / "progress.json"
    script = (
        "import json,sys,time; "
        "json.dump({'message':'Cross-checking musical evidence on CUDA…','activity':'cuda',"
        "'stage_fraction':0.2},open(sys.argv[1],'w')); time.sleep(.25)"
    )
    updates = []
    run_process(
        [sys.executable, "-c", script, str(progress_path)],
        stage="infer",
        progress=updates.append,
        progress_path=progress_path,
        timeout=2,
        stall_warning_after=.05,
    )
    warning = next(update for update in updates if update.activity == "waiting")
    assert warning.startswith("Cross-checking musical evidence on CUDA — no new progress report")
    assert "worker process is still running" in warning
    assert warning.stage_fraction == .2
    assert warning.last_reported_activity == "cuda"


def test_file_worker_progress_preserves_structured_metadata(tmp_path):
    progress_path = tmp_path / "progress.json"
    script = (
        "import json,sys,time; "
        "json.dump({'message':'Downloading model','activity':'download','stage_fraction':0.25,"
        "'bytes_done':10,'bytes_total':40},open(sys.argv[1],'w')); time.sleep(.2)"
    )
    updates = []
    run_process(
        [sys.executable, "-c", script, str(progress_path)],
        stage="infer", progress=updates.append, progress_path=progress_path, timeout=2,
    )
    event = next(update for update in updates if "Downloading model" in update)
    assert isinstance(event, ProgressEvent)
    assert event.activity == "download" and event.stage_fraction == .25
    assert event.bytes_done == 10 and event.bytes_total == 40


def test_cpu_selection_when_cuda_is_absent(monkeypatch):
    from studio_band.providers import device_for
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)))
    assert device_for("auto") == "cpu"
    assert device_for("cuda") == "cpu"
    with pytest.raises(RuntimeError, match="CUDA acceleration could not start"):
        device_for("auto", allow_cpu_fallback=False)


def test_incompatible_cuda_kernel_can_never_silently_become_mt3_cpu(monkeypatch):
    from studio_band.providers import device_for

    def incompatible(*_args, **_kwargs):
        raise RuntimeError("no kernel image is available for execution on the device")

    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: True, synchronize=lambda: None),
        ones=incompatible,
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    assert device_for("auto") == "cpu"
    with pytest.raises(RuntimeError, match="no kernel image"):
        device_for("auto", allow_cpu_fallback=False)


def test_mt3_reports_real_preprocess_inference_and_decode_boundaries(tmp_path, monkeypatch):
    import numpy as np
    import studio_band.providers as providers

    class FakeTensor:
        def __mul__(self, _value):
            return self

        def sum(self):
            return self

        def item(self):
            return 16

    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: True, synchronize=lambda: None),
        ones=lambda *_args, **_kwargs: FakeTensor(),
    )
    calls = []

    class FakeMidi:
        def save(self, path):
            Path(path).write_bytes(b"synthetic midi")

    class FakeModel:
        def preprocess(self, audio, sample_rate):
            calls.append(("preprocess", len(audio), sample_rate))
            return {"features": True}

        def forward(self, features):
            calls.append(("forward", features))
            return {"tokens": True}

        def decode(self, outputs):
            calls.append(("decode", outputs))
            return FakeMidi()

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "soxr", SimpleNamespace(resample=lambda audio, *_args: audio))
    monkeypatch.setitem(sys.modules, "mt3_infer", SimpleNamespace(load_model=lambda *_args, **_kwargs: FakeModel()))
    monkeypatch.setattr(providers, "_audio", lambda _path: (np.zeros((320, 2), dtype="float32"), 16000))
    monkeypatch.setattr(providers, "_events_from_midi", lambda *_args: [])
    monkeypatch.setenv("MT3_CHECKPOINT_DIR", str(tmp_path / "models"))
    updates = []

    result = providers.mr_mt3(
        {"audio": str(tmp_path / "song.wav"), "output": str(tmp_path / "output"), "device": "auto"},
        updates.append,
    )

    assert [call[0] for call in calls] == ["preprocess", "forward", "decode"]
    assert result["device"] == "cuda"
    messages = [update.message for update in updates]
    assert any("Preparing audio features" in message for message in messages)
    assert any("Cross-checking musical evidence on CUDA" in message for message in messages)
    assert any("Decoding the independent musical cross-check" in message for message in messages)
    fractions = [update.stage_fraction for update in updates]
    assert fractions == [0.05, 0.20, 0.45, 0.90]


def test_auto_quality_checks_models_vram_and_ram():
    assert choose_separator("auto", Hardware(True, 8, 32), True) == "roformer"
    assert choose_separator("auto", Hardware(True, 4, 32), True) == "demucs"
    assert choose_separator("auto", Hardware(True, 8, 8), True) == "demucs"
    assert choose_separator("auto", Hardware(True, 8, 32), False) == "demucs"


def test_missing_runtime_gives_actionable_error(tmp_path):
    with pytest.raises(StageError, match="runtime is missing"):
        RuntimeManager(tmp_path).command_for("transkun")


def test_windows_transkun_policy_pins_binary_cp311_compatible_ncls():
    policy = RuntimeManager.install_policy("piano", platform_name="nt")
    assert policy == {"constraints": ["ncls==0.0.68"], "binary_only": ["ncls"]}
    assert RuntimeManager.install_policy("piano", platform_name="posix") == {
        "constraints": [], "binary_only": [],
    }


def test_windows_transkun_install_uses_constraint_binary_only_and_validation(tmp_path, monkeypatch):
    import studio_band.runtime as runtime_module

    manager = RuntimeManager(tmp_path)
    monkeypatch.setattr(manager, "available", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(manager, "_uv", lambda *_args, **_kwargs: Path("uv"))
    monkeypatch.setattr(
        manager,
        "install_policy",
        lambda name: RuntimeManager.install_policy(name, platform_name="nt"),
    )
    commands = []

    def fake_run(command, **_kwargs):
        commands.append([str(value) for value in command])
        if "venv" in command:
            python = manager.python("piano")
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_bytes(b"synthetic python")
        if "freeze" in command:
            return "[stdout]\ntranskun==2.0.1\nncls==0.0.68\n"
        return ""

    monkeypatch.setattr(runtime_module, "run_process", fake_run)
    manager.install("piano", device="cuda")

    install = next(command for command in commands if "transkun==2.0.1" in command)
    constraint_index = install.index("--constraints") + 1
    constraint = Path(install[constraint_index])
    assert constraint.read_text(encoding="utf-8") == "ncls==0.0.68\n"
    assert install[install.index("--only-binary") + 1] == "ncls"
    assert "--strict" in install
    assert not any("ncls==0.0.70" in value for command in commands for value in command)
    validation = next(command[-1] for command in commands if len(command) >= 3 and command[-2] == "-c")
    assert "import ncls, transkun" in validation and "0.0.68" in validation
    record = read_json(manager.runtime_root / "piano" / "studio-runtime.json")
    assert record["constraints"] == ["ncls==0.0.68"]
    assert record["binary_only"] == ["ncls"] and record["validated"] is True


def test_mt3_cuda_runtime_is_one_cu128_transaction_with_real_kernel_validation(tmp_path, monkeypatch):
    import studio_band.runtime as runtime_module

    manager = RuntimeManager(tmp_path)
    monkeypatch.setattr(manager, "available", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(manager, "_uv", lambda *_args, **_kwargs: Path("uv"))
    commands = []

    def fake_run(command, **_kwargs):
        command = [str(value) for value in command]
        commands.append(command)
        if "venv" in command:
            python = manager.python("mt3")
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_bytes(b"synthetic python")
        if "freeze" in command:
            return "mt3-infer==0.2.0\ntorch==2.7.1+cu128\ntorchaudio==2.7.1+cu128\ntorchvision==0.22.1+cu128\n"
        return ""

    monkeypatch.setattr(runtime_module, "run_process", fake_run)
    manager.install("mt3", device="cuda")

    installs = [command for command in commands if "pip" in command and "install" in command]
    assert len(installs) == 1
    install = installs[0]
    assert install[install.index("--torch-backend") + 1] == "cu128"
    assert {"torch==2.7.1", "torchaudio==2.7.1", "torchvision==0.22.1"} <= set(install)
    validation = next(command[-1] for command in commands if len(command) >= 3 and command[-2] == "-c")
    assert "torch.version.cuda" in validation
    assert "torch.cuda.is_available()" in validation
    assert "torch.cuda.synchronize()" in validation
    record = read_json(manager.runtime_root / "mt3" / "studio-runtime.json")
    assert record["device_install"] == "cuda"
    assert record["torch_backend"] == "cu128" and record["validated"] is True


def test_mt3_runtime_cache_requires_requested_compute_backend(tmp_path):
    import studio_band.runtime as runtime_module

    manager = RuntimeManager(tmp_path)
    python = manager.python("mt3")
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_bytes(b"synthetic python")
    manifest = python.parent.parent / "studio-runtime.json"
    base = {
        "requirements": runtime_module.RUNTIMES["mt3"],
        "constraints": [],
        "binary_only": [],
        "validated": True,
    }
    atomic_json(manifest, {**base, "device_install": "cpu", "torch_backend": "cpu"})
    assert manager.available("mt3", device="cpu")
    assert not manager.available("mt3", device="cuda")

    atomic_json(manifest, {**base, "device_install": "cuda", "torch_backend": "cu128"})
    assert manager.available("mt3", device="cuda")
    assert manager.available("mt3", device="cpu")  # CUDA wheels can execute on CPU.

    atomic_json(manifest, {**base, "device_install": "cuda"})
    assert not manager.available("mt3"), "legacy unverified CUDA installs must be migrated"


def test_runtime_exposes_bundled_ffmpeg_under_standard_name(tmp_path, monkeypatch):
    executable = tmp_path / "imageio-ffmpeg-versioned.exe"
    executable.write_bytes(b"original synthetic executable fixture")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "must not alter third-party runtime behavior")
    monkeypatch.setenv("BPSR_APPLE_MUSIC_TOKEN", "apple-secret")
    monkeypatch.setenv("BPSR_MASSIVEMUSIC_CONSUMER_SECRET", "massive-secret")
    monkeypatch.setenv("BPSR_BANDCAMP_PASSWORD", "bandcamp-secret")
    monkeypatch.setenv("BPSR_MUSIC_STOREFRONT", "ID")
    environment = RuntimeManager(tmp_path / "managed").environment(executable)
    import os
    alias = Path(environment["PATH"].split(os.pathsep)[0]) / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    assert alias.read_bytes() == executable.read_bytes()
    assert "PYTEST_CURRENT_TEST" not in environment
    assert "BPSR_APPLE_MUSIC_TOKEN" not in environment
    assert "BPSR_MASSIVEMUSIC_CONSUMER_SECRET" not in environment
    assert "BPSR_BANDCAMP_PASSWORD" not in environment
    assert environment["BPSR_MUSIC_STOREFRONT"] == "ID"


def test_preview_mutes_parts_and_uses_gm_drums_without_game_input():
    record = {"parts": {"piano": [note().to_dict()], "drums": [note(61, source="drums", role="KICK").to_dict()]}, "drum_profile": load_drum_profile()}
    messages = preview_messages(record, {"drums"})
    ons = [m for _,m in messages if m & 0xF0 == 0x90]
    assert len(ons) == 1
    assert (ons[0] >> 8) & 0x7F == 36
    assert ons[0] & 0x0F == 9


@pytest.mark.parametrize("title", ["CON", "a/b:c?d", "..", "LPT1"])
def test_export_names_are_safe_on_windows(title):
    name = safe_name(title)
    assert name and name not in {"CON", "LPT1", ".."}
    assert not any(c in name for c in '/\\:?')


def test_lite_has_no_transitive_studio_or_ai_imports():
    forbidden = {"studio_band", "studio_band_ui", "torch", "demucs", "basic_pitch", "onnxruntime", "imageio_ffmpeg", "transkun", "mt3_infer", "beat_this", "audio_separator", "yt_dlp", "tkinterdnd2"}
    pending, visited = [Path("modern_launcher.py")], set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = [n.name for n in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            for name in names:
                root = name.split(".")[0]
                assert root not in forbidden, f"{path} imports {root}"
                dependency = Path(root+".py")
                if dependency.exists():
                    pending.append(dependency)
    assert "basic-pitch" not in Path("requirements.txt").read_text()


def test_frozen_worker_dispatch_precedes_gui_import():
    launcher = Path("studio_launcher.py").read_text()
    assert launcher.index('sys.argv[1] == "--studio-worker"') < launcher.index("import app")
    spec = Path("BPSR-MIDI-Studio.spec").read_text()
    assert '"studio_band_worker.py"' in spec and '"bpsr_drums.json"' in spec
