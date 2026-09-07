"""Fast, precision-first Audio -> Band cleanup.

Normal conversion stays on the fast Demucs path. Expensive models are reserved
for a few suspicious Piano/Guitar regions, and a final model-free sieve combines
audio evidence, local harmony, phrase continuity and beat timing.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
import threading

_APPLIED = False
_STATE = threading.local()

MAX_GUITAR_CANDIDATES = 18
MAX_REVIEW_REGIONS = 3
MAX_REVIEW_SECONDS = 12.0
MAX_SEQUENCE_REVIEW_SECONDS = 6.0


def _pc_distance(a: int, b: int) -> int:
    value = abs((a % 12) - (b % 12))
    return min(value, 12 - value)


def _onset_groups(events, tolerance: float = .045):
    groups = []
    for event in sorted(events, key=lambda item: (float(item.start), item.pitch or -1)):
        if not groups or float(event.start) - float(groups[-1][0].start) > tolerance:
            groups.append([])
        groups[-1].append(event)
    return groups


def _record_groups(records: list[dict], tolerance: float = .045):
    groups = []
    for item in sorted(records, key=lambda row: (float(row.get("start", 0.0)), int(row.get("pitch") or -1))):
        if not groups or float(item.get("start", 0.0)) - float(groups[-1][0].get("start", 0.0)) > tolerance:
            groups.append([])
        groups[-1].append(item)
    return groups


def _median_pitch(group) -> float | None:
    values = []
    for item in group:
        pitch = item.pitch if hasattr(item, "pitch") else item.get("pitch")
        if pitch is not None:
            values.append(int(pitch))
    values.sort()
    if not values:
        return None
    mid = len(values) // 2
    return float(values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2.0)


def _raw_confidence(event) -> float:
    value = getattr(event, "original_confidence", None)
    return float(event.confidence if value is None else value)


def _strong_support(event) -> bool:
    if event.tags & {"independent_agreement", "targeted_repair",
                     "guitar_specialist_support", "mega53_ownership_support"}:
        return True
    return any(event.evidence.get(key) for key in ("beta9_support_engines", "agreement_engines"))


def _beat_off_grid(beat_map, timestamp: float) -> bool:
    try:
        from .pitch_guard import _beat_grid_context
        context = _beat_grid_context(beat_map, timestamp)
    except Exception:
        return False
    return bool(context and context.get("off_grid"))


def _pitch_histogram(events):
    result = [0.0] * 12
    for event in events:
        if event.pitch is None or event.source == "drums" or event.confidence < .58:
            continue
        duration = max(.04, min(.80, event.end - event.start))
        weight = duration * (.35 + .65 * event.confidence)
        if event.source in {"bass", "vocals"}:
            weight *= .75
        result[event.pitch % 12] += weight
    return result


def _global_scale(histogram):
    peak = max(histogram, default=0.0)
    if peak <= 0:
        return set()
    ranked = sorted(range(12), key=lambda pc: histogram[pc], reverse=True)
    return {pc for pc in ranked[:7] if histogram[pc] >= peak * .08}


def _local_context(all_events, event, seconds: float = 1.35):
    nearby = [
        other for other in all_events
        if other is not event and other.pitch is not None and other.source != "drums"
        and abs(other.start - event.start) <= seconds and other.confidence >= .58
    ]
    return nearby, {other.pitch % 12 for other in nearby}


def _same_pc_repeat(source_events, event, seconds: float = 2.5):
    return any(
        other is not event and other.pitch is not None
        and other.pitch % 12 == event.pitch % 12
        and abs(other.start - event.start) <= seconds
        for other in source_events
    )


def _neighbor_jump(groups, index: int, event):
    if index <= 0 or index + 1 >= len(groups):
        return False, None
    previous, following = groups[index - 1], groups[index + 1]
    if event.start - previous[0].start > .95 or following[0].start - event.start > .95:
        return False, None
    left, right = _median_pitch(previous), _median_pitch(following)
    if left is None or right is None or abs(left - right) > 7:
        return False, None
    anchor = (left + right) / 2.0
    return abs(event.pitch - anchor) >= 8, anchor


def _audio_flags(event):
    evidence = event.evidence.get("audio_note_validation") or {}
    if not evidence:
        return {"available": False, "weak": False, "very_weak": False,
                "mixture_absent": False, "harmonic_only": False, "ownership_conflict": False}
    target = float(evidence.get("target_snr_db", 99.0))
    fundamental = float(evidence.get("fundamental_snr_db", 99.0))
    mix_snr = float(evidence.get("mixture_snr_db", 99.0))
    share = float(evidence.get("target_share", 1.0))
    dominance = float(evidence.get("dominance_db", 99.0))
    return {
        "available": True,
        "weak": target < 4.5 or fundamental < 1.0 or share < .25 or dominance < -4.5,
        "very_weak": (target < 1.5 and mix_snr < 3.0) or share < .12 or dominance < -9.0,
        "mixture_absent": mix_snr < 2.5 and target < 8.0,
        "harmonic_only": target >= 3.5 and fundamental < 0.0 and share < .30,
        "ownership_conflict": share < .18 or dominance < -7.0,
        "target_snr_db": round(target, 3), "fundamental_snr_db": round(fundamental, 3),
        "mixture_snr_db": round(mix_snr, 3), "target_share": round(share, 5),
        "dominance_db": round(dominance, 3),
    }


def _reject_record(event, reason: str, evidence: dict):
    record = event.to_dict()
    record["evidence"] = {**record.get("evidence", {}), "fast_precision": evidence}
    return {"event": record, "reason": reason}


def sieve_master(master):
    """Reject only multi-signal Piano/Guitar outliers; never filter by key alone."""
    all_events = list(master.events)
    targets = [e for e in all_events if e.source in {"piano", "guitar"} and e.pitch is not None]
    if not targets:
        master.provenance["fast_precision_sieve"] = {"version": 1, "checked": 0, "removed": 0}
        return master

    scale = _global_scale(_pitch_histogram(all_events))
    by_source = defaultdict(list)
    for event in targets:
        by_source[event.source].append(event)

    removed_ids, rejected = set(), []
    weakened = checked = 0
    for source, source_events in by_source.items():
        groups = _onset_groups(source_events)
        lookup = {id(event): index for index, group in enumerate(groups) for event in group}
        for event in source_events:
            checked += 1
            group = groups[lookup[id(event)]]
            if len(group) != 1:
                continue

            _nearby, local_pcs = _local_context(all_events, event)
            repeat = _same_pc_repeat(source_events, event)
            pc = event.pitch % 12
            global_rare = bool(scale) and pc not in scale
            nearest_pc = min((_pc_distance(pc, item) for item in local_pcs), default=6)
            tonal_orphan = pc not in local_pcs and not repeat and (nearest_pc >= 2 or global_rare)
            jump, anchor = _neighbor_jump(groups, lookup[id(event)], event)
            off_grid = _beat_off_grid(master.beat_map, event.start)
            audio = _audio_flags(event)
            duration = event.end - event.start
            raw = _raw_confidence(event)
            model_weak = (
                (source == "guitar" and event.engine == "basic_pitch" and raw < .78)
                or (source == "piano" and event.engine == "transkun" and event.confidence < .82)
                or raw < .72
            )
            short = duration < (.40 if source == "guitar" else .32)
            supported = _strong_support(event)
            evidence = {
                "pitch_class": pc, "local_pitch_classes": sorted(local_pcs),
                "global_scale_classes": sorted(scale), "same_pitch_class_nearby": repeat,
                "global_rare": global_rare, "nearest_local_pc_distance": nearest_pc,
                "neighbor_register_jump": jump, "neighbor_anchor": anchor,
                "off_sixteenth_grid": off_grid, "short": short,
                "raw_confidence": round(raw, 4), "independent_support": supported,
                "audio": {k: v for k, v in audio.items() if k != "available"},
            }

            reason = None
            if supported:
                if audio["very_weak"] and tonal_orphan and jump and off_grid and raw < .90:
                    reason = "supported_note_fails_audio_phrase_and_rhythm"
            else:
                if (audio["very_weak"] and tonal_orphan
                        and (jump or off_grid or global_rare or short or model_weak)):
                    reason = "audio_grounded_tonal_orphan"
                elif (audio["mixture_absent"] and tonal_orphan and (short or model_weak)):
                    reason = "pitch_missing_from_original_mix"
                elif (audio["ownership_conflict"] and tonal_orphan and (short or model_weak)):
                    reason = "foreign_pitch_owned_by_other_stem"
                elif (audio["weak"] and tonal_orphan and off_grid
                      and (short or model_weak) and (jump or global_rare)):
                    reason = "off_key_off_rhythm_weak_note"
                elif audio["harmonic_only"] and jump and not repeat and (short or model_weak):
                    reason = "harmonic_without_local_fundamental"
                elif (not audio["available"] and tonal_orphan and global_rare and jump
                      and off_grid and short and model_weak):
                    reason = "sequence_only_extreme_orphan"

            if reason:
                removed_ids.add(id(event))
                rejected.append(_reject_record(event, reason, evidence))
                continue

            if (not supported and tonal_orphan and audio["weak"]
                    and (jump or off_grid) and event.confidence < .88):
                weakened += 1
                event.confidence = max(0.0, event.confidence * .90)
                event.tags.add("fast_precision_suspect")
                event.evidence["fast_precision"] = evidence

    master.events = sorted(
        [event for event in master.events if id(event) not in removed_ids],
        key=lambda event: (event.start, event.source, event.pitch or 0),
    )
    master.rejected.extend(rejected)
    reasons = Counter(item["reason"] for item in rejected)
    master.provenance["fast_precision_sieve"] = {
        "version": 1, "checked": checked, "removed": len(rejected), "weakened": weakened,
        "reasons": dict(sorted(reasons.items())),
        "policy": "audio + local harmony + phrase + rhythm; key context is never a sole rejection rule",
    }
    return master


def _suspicious_records(records: list[dict], source: str, limit: int = MAX_GUITAR_CANDIDATES):
    rows = [dict(item) for item in records if item.get("source") == source and item.get("pitch") is not None]
    groups = _record_groups(rows)
    scored = []
    for index, group in enumerate(groups):
        if len(group) != 1:
            continue
        item = group[0]
        confidence = float(item.get("original_confidence", item.get("confidence", .5)))
        duration = max(0.0, float(item.get("end", 0.0)) - float(item.get("start", 0.0)))
        score = max(0.0, .82 - confidence) * 2.2
        if duration < .36:
            score += min(.35, (.36 - duration) * 1.25)
        if 0 < index < len(groups) - 1:
            previous, following = groups[index - 1], groups[index + 1]
            if (float(item["start"]) - float(previous[0]["start"]) <= .95
                    and float(following[0]["start"]) - float(item["start"]) <= .95):
                left, right = _median_pitch(previous), _median_pitch(following)
                if left is not None and right is not None and abs(left - right) <= 7:
                    distance = abs(int(item["pitch"]) - (left + right) / 2.0)
                    if distance >= 8:
                        score += min(.65, .16 + (distance - 8) * .05)
        if source == "guitar" and str(item.get("engine", "")) == "basic_pitch":
            score += .08
        if score >= .20:
            item["_review_score"] = round(score, 4)
            scored.append(item)
    return sorted(scored, key=lambda item: (-float(item["_review_score"]), float(item["start"])))[:limit]


def _review_regions(candidates: list[dict], duration: float, *, max_regions: int = MAX_REVIEW_REGIONS,
                    max_seconds: float = MAX_REVIEW_SECONDS):
    if not candidates or duration <= 0:
        return []
    raw = []
    for item in sorted(candidates, key=lambda row: (-float(row.get("_review_score", 0.0)), float(row["start"]))):
        center = float(item["start"])
        start = max(0.0, center - 1.35)
        end = min(duration, max(center + 1.65, float(item.get("end", center)) + .80))
        raw.append({"start": start, "end": end, "score": float(item.get("_review_score", .25)),
                    "reasons": ["fast_precision_candidate"]})
        if len(raw) >= max_regions * 2:
            break

    merged = []
    for region in sorted(raw, key=lambda row: row["start"]):
        if merged and region["start"] <= merged[-1]["end"] + .25:
            merged[-1]["end"] = max(merged[-1]["end"], region["end"])
            merged[-1]["score"] = max(merged[-1]["score"], region["score"])
        else:
            merged.append(dict(region))

    kept, budget = [], max_seconds
    for region in sorted(merged, key=lambda row: (-row["score"], row["start"])):
        if len(kept) >= max_regions or budget <= .25:
            break
        length = region["end"] - region["start"]
        if length > budget:
            region = dict(region)
            region["end"] = region["start"] + budget
            length = budget
        if length >= .25:
            kept.append(region)
            budget -= length
    return sorted(kept, key=lambda row: row["start"])


def review_guitar_candidates_targeted(payload: dict, report=None):
    """Run the existing six-fold model on <=12 s of candidate neighborhoods."""
    import numpy as np
    import soundfile as sf
    from .guitar_reviewer import review_guitar_candidates

    candidates = [dict(item) for item in payload.get("candidates", []) if item.get("pitch") is not None]
    if not candidates:
        return {"support": [], "model": "guitar-mtl-6fold-targeted", "review_only": True}

    source_path = Path(payload["audio"])
    with sf.SoundFile(str(source_path), "r") as source:
        sample_rate = int(source.samplerate)
        duration = len(source) / float(sample_rate)
        regions = list(payload.get("segments") or _review_regions(candidates, duration))
        if not regions:
            return {"support": [], "model": "guitar-mtl-6fold-targeted", "review_only": True}
        clips, mappings = [], []
        concat_time = 0.0
        gap_seconds = .18
        gap = np.zeros((max(1, round(gap_seconds * sample_rate)), int(source.channels)), dtype="float32")
        for region in regions:
            start = max(0.0, float(region["start"]))
            end = min(duration, float(region["end"]))
            if end <= start:
                continue
            source.seek(round(start * sample_rate))
            clip = source.read(max(1, round((end - start) * sample_rate)), dtype="float32", always_2d=True)
            if not len(clip):
                continue
            clip_seconds = len(clip) / sample_rate
            mappings.append({"original_start": start, "original_end": end,
                             "concat_start": concat_time, "concat_end": concat_time + clip_seconds})
            clips.extend([clip, gap])
            concat_time += clip_seconds + gap_seconds

    if not mappings:
        return {"support": [], "model": "guitar-mtl-6fold-targeted", "review_only": True}

    remapped, remap_index = [], []
    for item in candidates:
        for mapping in mappings:
            if mapping["original_start"] - .03 <= float(item["start"]) <= mapping["original_end"] + .03:
                copy = dict(item)
                offset = mapping["concat_start"] - mapping["original_start"]
                copy["start"] = float(item["start"]) + offset
                copy["end"] = float(item.get("end", item["start"])) + offset
                remapped.append(copy)
                remap_index.append((copy, item))
                break
    if not remapped:
        return {"support": [], "model": "guitar-mtl-6fold-targeted", "review_only": True}

    output = Path(payload["output"])
    output.mkdir(parents=True, exist_ok=True)
    clip_path = output / "targeted_guitar_review.wav"
    sf.write(str(clip_path), np.concatenate(clips[:-1], axis=0), sample_rate, subtype="FLOAT")
    nested = review_guitar_candidates({**payload, "audio": str(clip_path), "candidates": remapped}, report)

    support = []
    for row in nested.get("support", []):
        matches = [
            pair for pair in remap_index
            if int(pair[0]["pitch"]) == int(row["pitch"])
            and abs(float(pair[0]["start"]) - float(row["start"])) <= .08
        ]
        if not matches:
            continue
        _remapped_item, original_item = min(
            matches, key=lambda pair: abs(float(pair[0]["start"]) - float(row["start"]))
        )
        fixed = dict(row)
        fixed["start"] = float(original_item["start"])
        fixed["end"] = float(original_item.get("end", original_item["start"]))
        support.append(fixed)

    nested["support"] = support
    nested["targeted"] = True
    nested["targeted_seconds"] = round(sum(m["original_end"] - m["original_start"] for m in mappings), 3)
    nested["full_song_features"] = False
    return nested


def _patch_providers(providers):
    providers._legacy.PROVIDERS["guitar_review"] = review_guitar_candidates_targeted
    providers.PROVIDERS = providers._legacy.PROVIDERS


def _patch_separator(runtime, pipeline):
    original = runtime.choose_separator

    def choose_separator(quality, hardware, hq_available):
        if str(quality).lower() == "auto":
            return "demucs"
        return original(quality, hardware, hq_available)

    # Pipeline imported the chooser by value. Keep the public runtime helper
    # backward-compatible for tests/tools, but make actual conversions deterministic.
    pipeline.choose_separator = choose_separator


def _patch_runtime_plan(pipeline):
    original = pipeline.BandPipeline._runtime_plan

    def runtime_plan(settings, separator, hardware, global_variant=None):
        plan = list(original(settings, separator, hardware, global_variant))
        if (not settings.cross_check and settings.device != "cpu" and hardware.cuda
                and "guitar_review" not in plan):
            plan.append("guitar_review")
        return plan

    pipeline.BandPipeline._runtime_plan = staticmethod(runtime_plan)


def _patch_convert_mode(pipeline):
    original = pipeline.BandPipeline.convert

    def convert(self, source, settings=None, **kwargs):
        if settings is not None and str(settings.stem_quality).lower() == "auto":
            settings = replace(settings, stem_quality="standard")
        return original(self, source, settings, **kwargs)

    pipeline.BandPipeline.convert = convert


def _audio_duration(path: Path, fallback: float = 0.0) -> float:
    try:
        import soundfile as sf
        with sf.SoundFile(str(path)) as source:
            return max(fallback, len(source) / float(source.samplerate))
    except Exception:
        return fallback


def _patch_pipeline(pipeline, precision):
    original_stage = pipeline.BandPipeline._stage
    original_build_master = pipeline.build_master

    def stage(self, client, job, provider, audio, payload, cancel, report, warnings, settings, hardware):
        result = original_stage(
            self, client, job, provider, audio, payload, cancel, report, warnings, settings, hardware
        )
        if not hasattr(_STATE, "context"):
            _STATE.context = {
                "self": self, "client": client, "job": job, "cancel": cancel,
                "report": report, "settings": settings, "hardware": hardware,
            }

        fast_mode = not settings.cross_check
        cuda = settings.device != "cpu" and hardware.cuda

        if provider == "transkun" and result.get("events"):
            records = [dict(item) for item in result.get("events", [])]
            if fast_mode and cuda and self.runtimes.available("aria", device="cuda"):
                suspicious = _suspicious_records(records, "piano", limit=10)
                regions = _review_regions(
                    suspicious, _audio_duration(Path(audio), max((float(x.get("end", 0.0)) for x in records), default=0.0)),
                    max_regions=2, max_seconds=8.0,
                )
                if regions:
                    try:
                        extra = original_stage(
                            self, client, job, "aria_amt", audio, {"segments": regions},
                            cancel, report, warnings, settings, hardware,
                        )
                    except Exception as exc:
                        if isinstance(exc, pipeline.Cancelled):
                            raise
                        warnings.append(f"Fast targeted Aria-AMT review unavailable: {exc}")
                    else:
                        result.setdefault("events", []).extend(extra.get("events", []))
                        result.setdefault("provenance", {})["fast_aria_review"] = {
                            "regions": regions,
                            "seconds": round(sum(r["end"] - r["start"] for r in regions), 3),
                            "events": len(extra.get("events", [])),
                            "reuse_only": True,
                        }

        elif provider == "basic_pitch" and str(payload.get("source", "")) == "guitar" and result.get("events"):
            records = [dict(item) for item in result.get("events", [])]
            if fast_mode and cuda:
                suspicious = _suspicious_records(records, "guitar")
                regions = _review_regions(
                    suspicious, _audio_duration(Path(audio), max((float(x.get("end", 0.0)) for x in records), default=0.0))
                )
                if suspicious and regions:
                    try:
                        review = original_stage(
                            self, client, job, "guitar_review", audio,
                            {"candidates": suspicious, "segments": regions},
                            cancel, report, warnings, settings, hardware,
                        )
                    except Exception as exc:
                        if isinstance(exc, pipeline.Cancelled):
                            raise
                        warnings.append(f"Fast targeted guitar review unavailable: {exc}")
                    else:
                        result = precision._annotate_guitar_result(result, review)
                        result.setdefault("provenance", {})["fast_guitar_review"] = {
                            "candidates": len(suspicious), "regions": len(regions),
                            "seconds": review.get("targeted_seconds"), "full_song_features": False,
                        }
        return result

    def build_master(digest, duration, beats, primary, reference, provenance, warnings):
        context = getattr(_STATE, "context", None)
        reference = list(reference)
        provenance = dict(provenance)
        try:
            if context:
                settings, hardware = context["settings"], context["hardware"]
                if not settings.cross_check and settings.device != "cpu" and hardware.cuda:
                    self = context["self"]
                    records = [event.to_dict() for event in primary
                               if event.source in {"piano", "guitar"} and event.pitch is not None]
                    suspicious = (
                        _suspicious_records(records, "piano", limit=6)
                        + _suspicious_records(records, "guitar", limit=6)
                    )
                    high_risk = sorted(
                        [item for item in suspicious if float(item.get("_review_score", 0.0)) >= .55],
                        key=lambda row: -float(row.get("_review_score", 0.0)),
                    )[:4]
                    if high_risk and self.runtimes.available("yourmt3", device="cuda"):
                        regions = _review_regions(
                            high_risk, duration, max_regions=2,
                            max_seconds=MAX_SEQUENCE_REVIEW_SECONDS,
                        )
                        if regions:
                            try:
                                extra = original_stage(
                                    self, context["client"], context["job"], "yourmt3",
                                    Path(context["job"]) / "prepared.wav", {"segments": regions},
                                    context["cancel"], context["report"], warnings, settings, hardware,
                                )
                            except Exception as exc:
                                if isinstance(exc, pipeline.Cancelled):
                                    raise
                                warnings.append(f"Fast targeted YourMT3+ review unavailable: {exc}")
                            else:
                                added = precision._append_reference_records(reference, extra.get("events", []))
                                provenance.setdefault("fast_precision_review", {})["yourmt3"] = {
                                    "regions": regions,
                                    "seconds": round(sum(r["end"] - r["start"] for r in regions), 3),
                                    "events": added, "reuse_only": True,
                                }

            master = original_build_master(
                digest, duration, beats, primary, reference, provenance, warnings
            )
            return sieve_master(master)
        finally:
            for name in ("context",):
                if hasattr(_STATE, name):
                    delattr(_STATE, name)

    pipeline.BandPipeline._stage = stage
    pipeline.build_master = build_master


def apply_fast_precision() -> None:
    global _APPLIED
    if _APPLIED:
        return
    from . import pipeline, providers, runtime
    from . import precision_judges as precision

    _patch_providers(providers)
    _patch_separator(runtime, pipeline)
    _patch_runtime_plan(pipeline)
    _patch_convert_mode(pipeline)
    _patch_pipeline(pipeline, precision)

    original_setup_ui = precision.install_precision_setup_ui
    if not getattr(original_setup_ui, "_bpsr_fast_precision", False):
        def install_precision_setup_ui():
            original_setup_ui()
            from studio_fast_precision_ui import install_fast_precision_ui
            install_fast_precision_ui()
        install_precision_setup_ui._bpsr_fast_precision = True
        precision.install_precision_setup_ui = install_precision_setup_ui

    _APPLIED = True
