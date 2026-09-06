"""Audio → analysis → musical map → existing BPSR arrangement → export."""
from __future__ import annotations

import os
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .arrange import ArrangementSettings, arrange, load_drum_profile
from .export import export_arrangement, reopen, source_record
from .fusion import build_master, promote_targeted_repairs, uncertain_regions
from .music import BeatMap, MusicEvent
from .progress import PipelineProgress, ProgressEvent
from .protocol import Cancelled, RuntimeSetupError, StageError, WorkerClient, check_cancel, run_process
from .runtime import PROVIDER_RUNTIME, RUNTIME_LABELS, RuntimeManager, choose_separator, detect_hardware
from .storage import JobStore, atomic_json, cache_key, file_hash, file_lock, read_json

EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}


@dataclass
class ConversionSettings:
    stem_quality: str = "auto"
    device: str = "auto"
    install_models: bool = True
    cross_check: bool = True
    arrangement: ArrangementSettings = field(default_factory=ArrangementSettings)
    global_model: str = "auto"


class BandPipeline:
    def __init__(self, store: JobStore | None = None, runtimes: RuntimeManager | None = None,
                 client_factory=WorkerClient, ffmpeg: Path | None = None):
        self.store = store or JobStore()
        self.runtimes = runtimes or RuntimeManager()
        self.client_factory, self.ffmpeg = client_factory, ffmpeg

    def _prepare(self, original: Path, job: Path, cancel, report) -> tuple[Path, float]:
        from studio_youtube import _ffmpeg_executable
        ffmpeg = self.ffmpeg or _ffmpeg_executable()
        target = job / "prepared.wav"
        manifest = job / "prepared.json"
        preparation = {"sample_rate": 44100, "channels": 2, "format": "pcm_f32le", "version": 1}
        try:
            record = read_json(manifest)
            if record["settings"] == preparation and file_hash(target) == record["sha256"]:
                report("Preparing audio · using cached audio")
                return target, record["duration"]
        except (OSError, ValueError, KeyError):
            pass
        report("Preparing audio")
        temporary = job / "prepared.partial.wav"
        try:
            run_process([str(ffmpeg), "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(original),
                         "-map", "0:a:0", "-vn", "-ac", "2", "-ar", "44100", "-c:a", "pcm_f32le", str(temporary)],
                        stage="Preparing audio", cancel=cancel, progress=report, timeout=600)
            import soundfile as sf
            info = sf.info(str(temporary))
            if not 0 < info.duration <= 1800:
                raise StageError("Preparing audio", "Choose a song between 0 and 30 minutes long.")
            if info.samplerate != 44100 or info.channels != 2 or info.subtype != "FLOAT":
                raise StageError("Preparing audio", "The decoder returned an unexpected audio format.")
            os.replace(temporary, target)
            atomic_json(manifest, {"settings": preparation, "duration": info.duration,
                                   "frames": info.frames, "sha256": file_hash(target)})
            return target, info.duration
        finally:
            temporary.unlink(missing_ok=True)

    def _stage(self, client, job, provider, audio, payload, cancel, report, warnings, settings, hardware):
        runtime = PROVIDER_RUNTIME.get(provider)
        requested_device = "cuda" if settings.device != "cpu" and hardware.cuda else "cpu"
        # Check model availability/install independently for every specialist.
        if runtime and not self.runtimes.available(runtime, device=requested_device) and settings.install_models and runtime != "drums":
            self.runtimes.install(runtime, device=requested_device,
                                  cancel=cancel, progress=report)
        key = cache_key(file_hash(audio), self.runtimes.fingerprint(provider), payload, settings.device)
        folder = job / ("stems" if provider in {"demucs", "roformer"} else "transcription")
        cached = self.store.cached(folder, key)
        if cached:
            # Detect changed/corrupt local weights. Bundled Basic Pitch paths can
            # disappear between one-file EXE launches; the fixed package/model
            # version remains part of the cache key in that case.
            checksums = cached.get("provenance", {}).get("model_sha256", {})
            valid = all(not Path(p).exists() or file_hash(Path(p)) == digest for p,digest in checksums.items())
            if valid:
                report("Using cached " + provider.replace("_", " ") + " analysis")
                return cached
        output = folder / key
        output.mkdir(parents=True, exist_ok=True)
        arguments = {**payload, "audio": str(audio), "output": str(output), "models": str(self.runtimes.models),
                     "device": settings.device}
        try:
            result = client.call(provider, "infer", arguments, cancel=cancel, progress=report)
        except StageError:
            # CPU retry is useful for CUDA OOM/unsupported architectures. If the
            # stage still fails, its specialist fallback is handled by the caller.
            # Global/repair models are optional and exceptionally slow without
            # acceleration, so Auto/CUDA never turns either into a hidden CPU
            # retry. Explicit CPU remains available only for MR-MT3.
            if (settings.device == "cpu" or not hardware.cuda or provider not in PROVIDER_RUNTIME
                    or provider in {"muscriptor", "mr_mt3"}):
                raise
            report("Retrying this stage on CPU…")
            arguments["device"] = "cpu"
            result = client.call(provider, "infer", arguments, cancel=cancel, progress=report)
            result.setdefault("warnings", []).append(provider + " required a CPU retry.")
        files = []
        for path in list(result.get("stems", {}).values()) + [result.get("vocals"), result.get("instrumental")]:
            if path:
                resolved = Path(path).resolve()
                if not resolved.is_relative_to(output.resolve()) or not resolved.is_file():
                    raise StageError(provider, "The worker returned an invalid output path.")
                files.append(resolved)
        # Validate common events before a worker response becomes a reusable stage.
        for event in result.get("events", []):
            MusicEvent.from_dict(event)
        if "beat_map" in result:
            BeatMap(**result["beat_map"])
        self.store.commit_stage(folder, key, result, files)
        return result

    @staticmethod
    def _runtime_plan(settings: ConversionSettings, separator: str, hardware,
                      global_variant: str | None = None) -> list[str]:
        # Prepare preferred engines before touching the audio. This makes first
        # use a distinct, truthful phase and ensures dependency failures cannot
        # be mistaken for slow inference. Transkun is first so its small runtime
        # is validated before multi-GB separator/cross-check installs.
        plan = ["piano", "separator", "beat"]
        if global_variant:
            plan.append("global")
        if settings.cross_check and (settings.device == "cpu" or hardware.cuda):
            plan.append("mt3")
        if separator == "roformer":
            plan.append("hq")
        return plan

    def _prepare_runtimes(self, settings: ConversionSettings, hardware, separator: str,
                          global_variant: str | None, cancel, flow: PipelineProgress) -> None:
        required = self._runtime_plan(settings, separator, hardware, global_variant)
        device = "cuda" if settings.device != "cpu" and hardware.cuda else "cpu"
        missing = [name for name in required if not self.runtimes.available(name, device=device)]
        if not settings.install_models:
            flow.setup_ready("Runtime check complete; automatic installation is off")
            return
        if not missing:
            flow.setup_ready("Runtime and transcription components ready")
            return
        total = len(missing)
        for index, name in enumerate(missing):
            check_cancel(cancel)
            label = RUNTIME_LABELS.get(name, name)
            flow.setup(label, index, total, ProgressEvent(
                f"Preparing {label} runtime (first use only)…",
                activity="install", stage_fraction=0.0, indeterminate=True,
            ))
            self.runtimes.install(
                name,
                device=device,
                cancel=cancel,
                progress=lambda value, label=label, index=index: flow.setup(label, index, total, value),
            )
        flow.setup_ready("First-time transcription setup complete", first_time=True)

    def _global_model_variant(self, settings: ConversionSettings, hardware) -> str | None:
        if settings.global_model == "off" or settings.device == "cpu" or not hardware.cuda:
            return None
        if settings.global_model in {"medium", "large"}:
            return settings.global_model
        # Auto never springs a gated download/login failure on a normal user.
        # It activates Medium when accepted credentials or cached/local weights
        # make the operation ready to proceed.
        return "medium" if self.runtimes.muscriptor_model_access("medium") else None

    def convert(self, source: Path, settings: ConversionSettings | None = None, *, cancel=None, progress=None,
                source_metadata: dict | None = None) -> Path:
        settings = settings or ConversionSettings()
        settings.arrangement.validate()
        if settings.device not in {"auto", "cpu", "cuda"}:
            raise ValueError("Device must be Auto, CPU or CUDA")
        if settings.global_model not in {"auto", "off", "medium", "large"}:
            raise ValueError("Global model must be Auto, Off, Medium or Large")
        if source.suffix.lower() not in EXTENSIONS or not source.is_file():
            raise StageError("Preparing audio", "Choose an MP3, WAV, FLAC, M4A or OGG audio file.")
        if source.stat().st_size > 2 * 1024**3:
            raise StageError("Preparing audio", "This audio file is too large; choose a file below 2 GB.")
        flow = PipelineProgress(progress)
        check_cancel(cancel)
        source_info = source_record(source_metadata, source.stem)
        digest = file_hash(source)
        job = self.store.job(source, digest)
        warnings, provenance, primary, reference = [], {}, [], []
        hardware = detect_hardware()
        provenance["hardware"] = asdict(hardware)
        separator = choose_separator(settings.stem_quality, hardware,
                                     self.runtimes.available("hq") and (self.runtimes.models / "roformer").exists())
        global_variant = self._global_model_variant(settings, hardware)
        with file_lock(self.store.root / (job.name + ".lock")):
            atomic_json(job / "status.json", {"status": "running", "source_sha256": digest})
            try:
                self._prepare_runtimes(settings, hardware, separator, global_variant, cancel, flow)
                original = self.store.copy_source(job, source, digest)
                flow.stage("prepare_audio", activity="cpu")
                prepared, duration = self._prepare(
                    original, job, cancel,
                    lambda value: flow.detail("prepare_audio", value, activity="cpu"),
                )
                flow.complete("prepare_audio")
                from studio_youtube import _ffmpeg_executable
                client = self.client_factory(job / "requests", self.runtimes.command_for,
                                             self.runtimes.environment(self.ffmpeg or _ffmpeg_executable()))

                def provider_activity(provider):
                    if provider in {"basic_pitch", "drums_dsp", "beat_dsp"}:
                        return "cpu"
                    return "gpu" if settings.device != "cpu" and hardware.cuda else "cpu"

                def run(provider, audio, stage_id, **payload):
                    check_cancel(cancel)
                    activity = provider_activity(provider)
                    result = self._stage(
                        client, job, provider, audio, payload, cancel,
                        lambda value: flow.detail(stage_id, value, activity=activity),
                        warnings, settings, hardware,
                    )
                    provenance.setdefault("engines", []).append(result.get("provenance", {"provider": provider}))
                    warnings.extend(result.get("warnings", []))
                    return result

                def attempt(provider, audio, stage_id, fallback=None, **payload):
                    try:
                        return run(provider, audio, stage_id, **payload)
                    except RuntimeSetupError:
                        # A failed dependency installation is not an inference
                        # quality fallback. End the busy job and surface setup.
                        raise
                    except (StageError, OSError, ValueError, RuntimeError) as exc:
                        if isinstance(exc, Cancelled):
                            raise
                        if provider == "mr_mt3" and fallback is None:
                            reason = getattr(exc, "message", str(exc))
                            warnings.append(f"Independent musical cross-check unavailable: {reason}")
                        elif provider == "muscriptor" and fallback is None:
                            reason = getattr(exc, "message", str(exc))
                            warnings.append(f"MuScriptor global model unavailable: {reason}")
                        else:
                            warnings.append(f"{provider} unavailable: {exc}." + (f" Used {fallback}." if fallback else ""))
                        provenance.setdefault("fallbacks", []).append({"provider": provider, "replacement": fallback,
                                                                        "error": str(exc), "details": getattr(exc, "details", "")})
                        if fallback:
                            return run(fallback, audio, stage_id, **payload)
                        return {"events": [], "_stage_skipped": True}

                flow.stage("separate", activity=provider_activity(separator))
                vocal_hq = None
                separator_audio = prepared
                if separator == "roformer":
                    result = attempt("roformer", prepared, "separate")
                    if result.get("vocals"):
                        vocal_hq = Path(result["vocals"])
                        separator_audio = Path(result["instrumental"])
                    else:
                        warnings.append("HQ separation unavailable; used standard six-stem separation.")
                try:
                    use_ensemble = (settings.stem_quality != "standard" and settings.device != "cpu" and
                                    hardware.cuda)
                    separated = run("demucs", separator_audio, "separate", ensemble=use_ensemble)
                except RuntimeSetupError:
                    raise
                except (StageError, OSError, ValueError) as exc:
                    raise StageError("Separating stems", "The six-stem separator could not run. Open Advanced to install/repair it, then Retry.",
                                     str(exc) + "\n" + getattr(exc, "details", "")) from exc
                stems = {name: Path(path) for name,path in separated["stems"].items()}
                if vocal_hq:
                    stems["vocals"] = vocal_hq
                self._check_stem_timeline(stems, duration)
                separator_model = separated.get("provenance", {}).get("model", "htdemucs_6s")
                provenance["separator"] = {
                    "requested": settings.stem_quality,
                    "actual": "roformer+demucs" if vocal_hq else "demucs",
                    "model": separator_model,
                    "ensemble": bool(separated.get("ensemble")),
                    "timeline": "original, untrimmed",
                    "ownership": "mixture-consistent spectral masks",
                }
                provenance["stem_metrics"] = separated.get("metrics", {})
                flow.complete("separate")

                flow.stage("beat", activity=provider_activity("beat_this"))
                beat_result = attempt("beat_this", prepared, "beat", "beat_dsp")
                beats = BeatMap(**beat_result["beat_map"])
                flow.complete("beat")

                def add(result, source_name=None, target=None):
                    container = primary if target is None else target
                    for index, record in enumerate(result.get("events", [])):
                        e = MusicEvent.from_dict(record)
                        if source_name and e.source != source_name:
                            continue
                        if e.start >= duration:
                            continue
                        e.end = min(e.end, duration)
                        e.event_id = f"{e.engine}:{e.source}:{index}"
                        container.append(e)

                flow.stage("vocals", activity="cpu")
                add(run("basic_pitch", stems["vocals"], "vocals", source="vocals"))
                add(attempt("torchcrepe", stems["vocals"], "vocals", source="vocals"), target=reference)
                flow.complete("vocals")
                flow.stage("piano", activity=provider_activity("transkun"))
                add(attempt("transkun", stems["piano"], "piano", "basic_pitch", source="piano"))
                flow.complete("piano")
                flow.stage("guitar", activity="cpu")
                add(run("basic_pitch", stems["guitar"], "guitar", source="guitar"))
                flow.complete("guitar")
                flow.stage("bass", activity="cpu")
                add(run("basic_pitch", stems["bass"], "bass", source="bass"))
                add(attempt("torchcrepe", stems["bass"], "bass", source="bass"), target=reference)
                flow.complete("bass")
                flow.stage("other", activity="cpu")
                add(run("basic_pitch", stems["other"], "other", source="other"))
                flow.complete("other")
                flow.stage("drums", activity="cpu")
                drum_backend = "adtof" if self.runtimes.available("drums") else "drums_dsp"
                drum_result = (attempt("adtof", stems["drums"], "drums", "drums_dsp")
                               if drum_backend == "adtof" else run("drums_dsp", stems["drums"], "drums"))
                drum_backend = drum_result.get("provenance", {}).get("provider", drum_backend)
                add(drum_result)
                provenance["drum_backend"] = drum_backend
                flow.complete("drums")

                provenance["global_model"] = {
                    "requested": settings.global_model,
                    "actual": global_variant,
                    "role": "full-song instrument and note evidence",
                }
                if global_variant:
                    flow.stage(
                        "global_model",
                        activity=provider_activity("muscriptor"),
                        message=f"Running MuScriptor {global_variant.title()} global music model",
                    )
                    global_result = attempt(
                        "muscriptor", prepared, "global_model", model=global_variant,
                    )
                    add(global_result, target=reference)
                    if global_result.get("_stage_skipped"):
                        provenance["global_model"]["actual"] = None
                        flow.skip("global_model", "MuScriptor global model unavailable — using specialist evidence")
                    else:
                        provenance["global_model"]["events"] = len(global_result.get("events", []))
                        flow.complete("global_model", "MuScriptor global evidence ready")
                elif settings.global_model != "off" and (
                    settings.device == "cpu" or not hardware.cuda
                ):
                    reason = "MuScriptor requires working CUDA in Studio; continuing with specialist evidence."
                    if settings.global_model in {"medium", "large"}:
                        warnings.append(reason)
                    provenance["global_model"]["reason"] = reason
                    flow.skip("global_model", "MuScriptor needs CUDA — using specialist evidence")
                elif settings.global_model == "auto":
                    provenance["global_model"]["reason"] = "No cached/local weights or authenticated model access"
                    flow.skip("global_model", "Global model not configured — using specialist evidence")
                else:
                    flow.skip("global_model", "Global music model disabled")

                if settings.cross_check:
                    if settings.device != "cpu" and not hardware.cuda:
                        reason = (
                            "Independent musical cross-check skipped: Auto/CUDA mode did not detect an NVIDIA GPU. "
                            "Choose CPU in Advanced only if you accept a potentially very long run."
                        )
                        warnings.append(reason)
                        provenance.setdefault("fallbacks", []).append({
                            "provider": "mr_mt3", "replacement": None,
                            "error": reason, "details": "nvidia-smi did not report an available CUDA device",
                        })
                        flow.skip("cross_check", "Independent cross-check needs CUDA — continuing without it")
                    else:
                        regions = uncertain_regions(
                            primary, duration, provenance.get("stem_metrics", {}), reference=reference,
                        )
                        provenance["cross_check"] = {
                            "mode": "targeted_low_confidence",
                            "regions": regions,
                            "seconds": sum(region["end"]-region["start"] for region in regions),
                            "coverage_ratio": (sum(region["end"]-region["start"] for region in regions) /
                                               duration if duration else 0.0),
                        }
                        if not regions:
                            flow.skip("cross_check", "No low-confidence sections need the independent cross-check")
                        else:
                            flow.stage("cross_check", activity=provider_activity("mr_mt3"),
                                       message=f"Cross-checking {len(regions)} low-confidence section(s)")
                            cross_check = attempt("mr_mt3", prepared, "cross_check", segments=regions)
                            add(cross_check, target=reference)
                            if cross_check.get("_stage_skipped"):
                                flow.skip("cross_check", "Independent cross-check unavailable — continuing without it")
                            else:
                                repairs = promote_targeted_repairs(
                                    primary, reference, provenance.get("stem_metrics", {}),
                                )
                                primary.extend(repairs)
                                provenance["cross_check"]["repairs_added"] = len(repairs)
                                flow.complete("cross_check", "Low-confidence sections cross-checked")
                else:
                    warnings.append("Musical cross-check was disabled in Advanced.")
                    flow.skip("cross_check", "Musical cross-check disabled")
                flow.stage("fusion", activity="cpu")
                master = build_master(digest, duration, beats, primary, reference, provenance, warnings)
                atomic_json(job / "analysis" / "master.json", master.to_dict())
                if not master.events:
                    raise StageError("Building musical map", "No reliable musical events were found. Try another recording or separation quality.")
                flow.complete("fusion")
                check_cancel(cancel)
                flow.stage("arrange", activity="cpu")
                profile_path = self.runtimes.root / "profiles" / "bpsr_drums.json"
                profile = load_drum_profile(profile_path if profile_path.exists() else None)
                result = arrange(master, settings.arrangement, profile)
                if not profile["calibrated"]:
                    master.warnings.append("Drum pads use a provisional semantic mapping; edit Advanced → Drum mapping after calibration.")
                flow.complete("arrange")
                flow.stage("export", activity="disk")
                check_cancel(cancel)
                output = export_arrangement(job / "output", source_info.get("title", source.stem), master, result,
                                            settings.arrangement, job, source_info)
                atomic_json(job / "status.json", {"status": "done", "arrangement": str(output)})
                flow.complete("export", "Conversion complete")
                return output
            except Exception as exc:
                atomic_json(job / "status.json", {"status": "cancelled" if isinstance(exc, Cancelled) else "failed",
                                                  "error": str(exc), "details": getattr(exc, "details", "")})
                raise

    @staticmethod
    def _check_stem_timeline(stems: dict[str, Path], duration: float):
        import soundfile as sf
        if set(stems) != {"vocals", "piano", "guitar", "bass", "drums", "other"}:
            raise StageError("Separating stems", "The separator did not return all six instruments.")
        for name, path in stems.items():
            info = sf.info(str(path))
            if info.samplerate != 44100 or info.channels != 2 or abs(info.duration-duration) > 1/44100 + 1e-8:
                raise StageError("Separating stems", f"The {name} stem does not match the original song timeline.")

    def rearrange(self, manifest: Path, settings: ArrangementSettings, *, output: Path | None = None) -> Path:
        # This path requires no audio, model runtime, network, or surviving cache.
        profile_path = self.runtimes.root / "profiles" / "bpsr_drums.json"
        profile = load_drum_profile(profile_path) if profile_path.exists() else None
        return reopen(manifest, settings, output or manifest.parent.parent, profile)
