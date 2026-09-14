from __future__ import annotations

from studio_band import PIPELINE_VERSION, VERSION
from studio_band.music import MusicEvent
from studio_band.precision_judges import (
    _STATE,
    _annotate_guitar,
    _annotate_mega53,
    _annotate_yourmt3,
)
from studio_band.runtime import PROVIDER_RUNTIME, RUNTIMES


def _event(source: str, pitch: int = 64, confidence: float = .78) -> MusicEvent:
    return MusicEvent(
        source=source,
        role="HARMONY",
        start=1.0,
        end=1.4,
        pitch=pitch,
        velocity=82,
        confidence=confidence,
        engine="basic_pitch",
        tags=set(),
        evidence={},
    )


def test_guitar_reviewer_disagreement_is_annotated_not_replaced():
    event = _event("guitar", 64)
    _STATE.guitar_review = [{
        "start": .99,
        "end": 1.42,
        "pitch": 65,
        "confidence": .82,
    }]
    try:
        guarded = _annotate_guitar([event])
    finally:
        delattr(_STATE, "guitar_review")
    assert len(guarded) == 1
    assert guarded[0].pitch == 64
    assert guarded[0].confidence < event.confidence
    assert "guitar_review_disagreement" in guarded[0].tags


def test_yourmt3_disagreement_is_annotated_not_replaced():
    event = _event("piano", 64)
    _STATE.yourmt3_events = [{
        "source": "piano", "start": .99, "end": 1.42, "pitch": 65,
        "confidence": .86,
    }]
    try:
        guarded = _annotate_yourmt3([event])
    finally:
        delattr(_STATE, "yourmt3_events")
    assert len(guarded) == 1
    assert guarded[0].pitch == 64
    assert guarded[0].confidence < event.confidence
    assert "yourmt3_pitch_conflict" in guarded[0].tags


def test_mega53_ownership_conflict_is_annotated_not_reassigned():
    event = _event("piano", 64)
    _STATE.mega53_ownership = [{
        "start": .98, "end": 1.43, "pitch": 64, "source": "guitar", "confidence": .9,
    }]
    try:
        guarded = _annotate_mega53([event])
    finally:
        delattr(_STATE, "mega53_ownership")
    assert len(guarded) == 1
    assert guarded[0].pitch == 64
    assert guarded[0].confidence < event.confidence
    assert "mega53_ownership_conflict" in guarded[0].tags


def test_precision_judges_are_isolated_review_runtimes_and_keep_analysis_cache_contract():
    assert VERSION.endswith("hotfix9")
    assert PIPELINE_VERSION == "band-accurate-10"
    assert PROVIDER_RUNTIME["guitar_review"] == "guitar_review"
    assert PROVIDER_RUNTIME["yourmt3"] == "yourmt3"
    assert PROVIDER_RUNTIME["mega53"] == "mega53"
    assert all(name in RUNTIMES for name in ("guitar_review", "yourmt3", "mega53"))
