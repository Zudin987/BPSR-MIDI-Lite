"""beta.9 precision-review layer: prove notes instead of generating more notes."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import threading

from .guitar_reviewer import review_guitar_candidates
from .external_judges import yourmt3_review, mega53_ownership

_APPLIED = False
_STATE = threading.local()

GUITAR_RUNTIME = ["torch==2.11.0", "numpy==2.3.3", "librosa==0.11.0", "soundfile==0.13.1", "soxr==1.0.0"]
YOURMT3_RUNTIME = [
    "torch==2.11.0", "torchaudio==2.11.0", "numpy==1.26.4", "mido==1.3.3",
    "lightning>=2.2.1,<2.7", "deprecated>=1.2", "librosa==0.11.0", "einops==0.8.1",
    "transformers==4.45.1", "wandb>=0.17", "huggingface-hub>=0.35,<1", "mir_eval>=0.7",
    "python-dotenv>=1.0", "soundfile==0.13.1",
]
MEGA53_RUNTIME = [
    "torch==2.11.0", "numpy==1.26.4", "librosa==0.11.0", "soundfile==0.13.1",
    "pyyaml>=6", "ml-collections>=0.1.1", "omegaconf==2.2.3", "beartype==0.14.1",
    "rotary-embedding-torch==0.3.5", "einops==0.8.1", "tqdm>=4.64",
]


def _patch_runtimes(runtime) -> None:
    additions = {
        "guitar_review": (GUITAR_RUNTIME, {"cpu": "cpu", "cuda": "cu128"}, "Guitar specialist reviewer",
                          "import torch, librosa, soundfile, numpy; assert torch.__version__.split('+')[0] == '2.11.0'"),
        "yourmt3": (YOURMT3_RUNTIME, {"cuda": "cu128"}, "YourMT3+ targeted judge",
                    "import torch, torchaudio, lightning, transformers, huggingface_hub; assert torch.__version__.split('+')[0] == '2.11.0'; assert transformers.__version__ == '4.45.1'"),
        "mega53": (MEGA53_RUNTIME, {"cuda": "cu128"}, "Mega53 ownership judge",
                   "import torch, librosa, soundfile, omegaconf, ml_collections, beartype, einops; assert torch.__version__.split('+')[0] == '2.11.0'"),
    }
    for name, (requirements, backends, label, validation) in additions.items():
        runtime.RUNTIMES[name] = requirements
        runtime.RUNTIME_TORCH_BACKENDS[name] = backends
        runtime.RUNTIME_LABELS[name] = label
        runtime.RUNTIME_VALIDATION[name] = validation
    runtime.PROVIDER_RUNTIME.update({"guitar_review": "guitar_review", "yourmt3": "yourmt3", "mega53": "mega53"})
    runtime.PROVIDER_MODEL.update({
        "guitar_review": "Guitar-Transcription-6fold@e2be2c66",
        "yourmt3": "YourMT3+-PTF-MoE-Multi@e45ebd7",
        "mega53": "MVSep-Mega53-v1.0.21",
    })

    original_install = runtime.RuntimeManager.install
    if not getattr(original_install, "_bpsr_precision_runtime_guard", False):
        def install(self, name: str, *, device: str = "cpu", cancel=None, progress=None, repair: bool = False) -> None:
            requested = device
            if requested == "auto":
                requested = "cuda" if runtime.detect_hardware().cuda else "cpu"
            if name in {"yourmt3", "mega53"} and requested != "cuda":
                raise runtime.RuntimeSetupError(
                    name, f"{runtime.RUNTIME_LABELS.get(name, name)} requires a working NVIDIA CUDA device.",
                    "This precision reviewer is optional and is never run as a hidden CPU job.",
                )
            if name == "mega53" and runtime.detect_hardware().vram_gb < 14.0:
                raise runtime.RuntimeSetupError(
                    name, "Mega53 ownership review requires at least 14 GB detected NVIDIA VRAM.",
                    "The 53-stem model is intentionally skipped on smaller GPUs instead of risking an out-of-memory failure.",
                )
            return original_install(self, name, device=requested, cancel=cancel, progress=progress, repair=repair)
        install._bpsr_precision_runtime_guard = True
        runtime.RuntimeManager.install = install


def _patch_providers(providers) -> None:
    legacy = providers._legacy
    legacy.PROVIDERS["guitar_review"] = review_guitar_candidates
    legacy.PROVIDERS["yourmt3"] = yourmt3_review
    legacy.PROVIDERS["mega53"] = mega53_ownership
    providers.PROVIDERS = legacy.PROVIDERS


def _candidate_records(events) -> list[dict]:
    records = []
    for item in events or []:
        source, pitch = item.get("source"), item.get("pitch")
        if source not in {"piano", "guitar"} or pitch is None:
            continue
        records.append({
            "source": source, "pitch": int(pitch), "start": float(item["start"]), "end": float(item["end"]),
            "confidence": float(item.get("confidence", .5)), "engine": str(item.get("engine", "")),
        })
    return records


def _match_support(event: dict, support: list[dict], tolerance: float = .07):
    pitch = event.get("pitch")
    if pitch is None:
        return None
    matches = [item for item in support if int(item.get("pitch", -999)) == int(pitch)
               and abs(float(item.get("start", 9999)) - float(event["start"])) <= tolerance]
    return max(matches, key=lambda item: float(item.get("support", 0.0)), default=None)


def _annotate_guitar_result(result: dict, support_result: dict) -> dict:
    support = list(support_result.get("support") or [])
    if not support:
        return result
    updated = dict(result)
    events = []
    for record in result.get("events", []):
        item = dict(record)
        if item.get("source") != "guitar":
            events.append(item); continue
        match = _match_support(item, support)
        if not match:
            events.append(item); continue
        score = float(match["support"])
        evidence = dict(item.get("evidence") or {})
        evidence.update({"guitar_specialist_support": score, "guitar_specialist_model": support_result.get("model"),
                         "guitar_specialist_review_only": True})
        tags = set(item.get("tags") or [])
        confidence = float(item.get("confidence", .5))
        if score >= .58:
            tags.add("guitar_specialist_support")
            confidence += (1.0 - confidence) * min(.10, .04 + .08 * (score - .58))
        elif score <= .16:
            tags.add("guitar_specialist_conflict"); confidence *= .84
        elif score < .30:
            tags.add("weak_guitar_specialist_support"); confidence *= .94
        item.update({"confidence": max(0.0, min(.99, confidence)), "tags": sorted(tags), "evidence": evidence})
        events.append(item)
    updated["events"] = events
    updated.setdefault("provenance", {})["guitar_specialist"] = {
        "model": support_result.get("model"), "reviewed": len(support), "review_only": True,
        "source_revision": support_result.get("source_revision"), "weights_revision": support_result.get("weights_revision"),
    }
    return updated


def _ownership_match(event, records: list[dict]):
    if event.pitch is None or event.source not in {"piano", "guitar"}:
        return None
    matches = [item for item in records if item.get("source") == event.source
               and int(item.get("pitch", -999)) == event.pitch
               and abs(float(item.get("start", 9999)) - event.start) <= .08]
    return min(matches, key=lambda item: abs(float(item["start"]) - event.start), default=None)


def _annotate_mega53(primary):
    ownership = list(getattr(_STATE, "mega53_ownership", []) or [])
    if not ownership:
        return primary
    result = []
    for event in primary:
        match = _ownership_match(event, ownership)
        if not match:
            result.append(event); continue
        preferred, margin = str(match.get("preferred", "ambiguous")), float(match.get("guitar_vs_piano_db", 0.0))
        evidence, tags, confidence = {**event.evidence, "mega53_ownership": match}, set(event.tags), event.confidence
        if preferred == event.source and abs(margin) >= 2.0:
            tags.add("mega53_ownership_support")
            confidence += (1.0 - confidence) * min(.07, .02 + abs(margin) * .004)
        elif preferred in {"piano", "guitar"} and preferred != event.source and abs(margin) >= 4.0:
            tags.add("mega53_ownership_conflict")
            confidence *= max(.76, .92 - min(12.0, abs(margin)) * .01)
        result.append(replace(event, confidence=max(0.0, min(.99, confidence)), tags=tags, evidence=evidence))
    return result


def _append_reference_records(reference, records) -> int:
    from .music import MusicEvent
    added = 0
    for index, record in enumerate(records or []):
        try:
            event = MusicEvent.from_dict(record)
        except (TypeError, ValueError, KeyError):
            continue
        event.event_id = f"{event.engine}:{event.source}:precision:{index}"
        reference.append(event); added += 1
    return added


def _run_deferred_judges(reference, provenance, warnings):
    """Run heavyweight reviewers even when MR-MT3 itself failed."""
    context, regions = getattr(_STATE, "review_context", None), list(getattr(_STATE, "review_regions", []) or [])
    if not context or not regions:
        return
    original_stage, self, client, job = context["stage"], context["self"], context["client"], context["job"]
    cancel, report, settings, hardware = context["cancel"], context["report"], context["settings"], context["hardware"]
    p = dict(provenance.get("precision_judges") or {})
    try:
        extra = original_stage(self, client, job, "yourmt3", Path(job) / "prepared.wav", {"segments": regions},
                               cancel, report, warnings, settings, hardware)
    except Exception as exc:
        if isinstance(exc, context["cancelled_type"]): raise
        warnings.append(f"YourMT3+ targeted judge unavailable: {exc}")
        p["yourmt3"] = {"available": False, "review_only": True, "reason": str(exc)}
    else:
        count = _append_reference_records(reference, extra.get("events", []))
        p["yourmt3"] = {"available": True, "events": count, "model": extra.get("model"), "review_only": True}
        warnings.extend(extra.get("warnings", []))

    candidates = list(getattr(_STATE, "piano_candidates", []) or []) + list(getattr(_STATE, "guitar_candidates", []) or [])
    _STATE.mega53_ownership = []
    if hardware.vram_gb < 14.0:
        p["mega53"] = {"skipped": True, "review_only": True, "reason": "requires at least 14 GB detected VRAM"}
    elif not candidates:
        p["mega53"] = {"skipped": True, "review_only": True, "reason": "no piano/guitar candidates"}
    else:
        try:
            extra = original_stage(self, client, job, "mega53", Path(job) / "prepared.wav",
                                   {"segments": regions, "candidates": candidates}, cancel, report, warnings, settings, hardware)
        except Exception as exc:
            if isinstance(exc, context["cancelled_type"]): raise
            warnings.append(f"Mega53 ownership judge unavailable: {exc}")
            p["mega53"] = {"available": False, "review_only": True, "reason": str(exc)}
        else:
            _STATE.mega53_ownership = list(extra.get("ownership") or [])
            p["mega53"] = {"available": True, "ownership_records": len(_STATE.mega53_ownership),
                           "model": extra.get("model"), "review_only": True}
            warnings.extend(extra.get("warnings", []))
    p["policy"] = "review existing notes; do not create notes"
    provenance["precision_judges"] = p


def _patch_pipeline(pipeline) -> None:
    original_stage, original_build_master = pipeline.BandPipeline._stage, pipeline.build_master

    def stage(self, client, job, provider, audio, payload, cancel, report, warnings, settings, hardware):
        quality = bool(settings.cross_check and settings.device != "cpu" and hardware.cuda)
        if provider == "mr_mt3" and quality and payload.get("segments"):
            _STATE.review_regions = list(payload.get("segments") or [])[:3]
            _STATE.review_context = {"stage": original_stage, "self": self, "client": client, "job": job,
                                     "cancel": cancel, "report": report, "settings": settings, "hardware": hardware,
                                     "cancelled_type": pipeline.Cancelled}
        result = original_stage(self, client, job, provider, audio, payload, cancel, report, warnings, settings, hardware)
        if provider == "transkun":
            _STATE.piano_candidates = _candidate_records(result.get("events", [])); _STATE.mega53_ownership = []
        elif provider == "basic_pitch" and str(payload.get("source", "")) == "guitar":
            _STATE.guitar_candidates = _candidate_records(result.get("events", []))
            if quality and result.get("events"):
                try:
                    review = original_stage(self, client, job, "guitar_review", audio,
                                            {"candidates": _candidate_records(result.get("events", []))},
                                            cancel, report, warnings, settings, hardware)
                except Exception as exc:
                    if isinstance(exc, pipeline.Cancelled): raise
                    warnings.append(f"Dedicated guitar review unavailable: {exc}")
                    result.setdefault("warnings", []).append("Dedicated guitar reviewer unavailable; existing guitar transcription retained.")
                else:
                    result = _annotate_guitar_result(result, review); warnings.extend(review.get("warnings", []))
        return result

    def build_master(digest, duration, beats, primary, reference, provenance, warnings):
        provenance, reference = dict(provenance), list(reference)
        try:
            _run_deferred_judges(reference, provenance, warnings)
            annotated = _annotate_mega53(primary)
            p = dict(provenance.get("precision_judges") or {})
            p.setdefault("guitar_specialist", {"reviewed_candidates": len(getattr(_STATE, "guitar_candidates", []) or []), "review_only": True})
            p["mega53_ownership_records"] = len(getattr(_STATE, "mega53_ownership", []) or [])
            p["policy"] = "review existing notes; do not create notes"
            provenance["precision_judges"] = p
            return original_build_master(digest, duration, beats, annotated, reference, provenance, warnings)
        finally:
            for key in ("piano_candidates", "guitar_candidates", "mega53_ownership", "review_regions", "review_context"):
                if hasattr(_STATE, key): delattr(_STATE, key)

    pipeline.BandPipeline._stage, pipeline.build_master = stage, build_master


def _patch_audio_guard(audio_guard) -> None:
    original_support = audio_guard._strong_support
    def strong_support(event):
        return bool(event.tags & {"guitar_specialist_support", "mega53_ownership_support"}) or original_support(event)
    audio_guard._strong_support = strong_support


def _patch_setup_ui() -> None:
    try:
        import studio_band_advanced_setup as setup
    except ImportError:
        return
    setup._COMPONENTS.update({
        "guitar_review": ("Guitar specialist", "Six-fold GuitarSet HCQT+Mel reviewer; proves existing guitar notes only", "Quality"),
        "yourmt3": ("Targeted music judge", "YourMT3+ on uncertain sections; independent reference evidence only", "Max quality"),
        "mega53": ("Piano/guitar ownership", "Mega53 53-stem evidence on uncertain sections; 14 GB+ NVIDIA VRAM", "High-VRAM"),
    })
    original_plan = setup._recommended_plan
    if not getattr(original_plan, "_bpsr_precision_setup", False):
        def recommended_plan(tab, hardware):
            plan, device = list(original_plan(tab, hardware)), setup._effective_device(tab, hardware)
            if tab.cross_check.get() and device == "cuda":
                if "guitar_review" in setup.RUNTIMES: plan.append("guitar_review")
                if "yourmt3" in setup.RUNTIMES: plan.append("yourmt3")
                if hardware.vram_gb >= 14.0 and "mega53" in setup.RUNTIMES: plan.append("mega53")
            return list(dict.fromkeys(plan))
        recommended_plan._bpsr_precision_setup = True
        setup._recommended_plan = recommended_plan
    original_status = setup._component_status
    if not getattr(original_status, "_bpsr_precision_setup", False):
        def component_status(tab, key, hardware):
            if key in {"yourmt3", "mega53"} and not hardware.cuda: return "NVIDIA only"
            if key == "mega53" and hardware.vram_gb < 14.0: return "14 GB VRAM"
            if key in {"guitar_review", "yourmt3", "mega53"}:
                if tab.pipeline.runtimes.available(key): return "Ready"
                return "Needs setup" if tab.cross_check.get() else "Optional"
            return original_status(tab, key, hardware)
        component_status._bpsr_precision_setup = True
        setup._component_status = component_status


def apply_precision_judges() -> None:
    global _APPLIED
    if _APPLIED: return
    from . import audio_note_guard, pipeline, providers, runtime
    _patch_runtimes(runtime); _patch_providers(providers); _patch_audio_guard(audio_note_guard); _patch_pipeline(pipeline); _patch_setup_ui()
    _APPLIED = True
