from __future__ import annotations

from dataclasses import replace

from studio_band import PIPELINE_VERSION, VERSION
from studio_band import precision_judges
from studio_band.music import MusicEvent
from studio_band.runtime import PROVIDER_RUNTIME, RUNTIMES


def _guitar_event(confidence: float = .72) -> dict:
    return {
        "source": "guitar", "role": "HARMONY", "start": 1.0, "end": 1.30,
        "pitch": 64, "velocity": 80, "confidence": confidence,
        "engine": "basic_pitch", "tags": [], "event_id": "g1",
        "original_confidence": confidence, "evidence": {},
    }


def test_guitar_reviewer_only_annotates_existing_notes():
    result = {"events": [_guitar_event()]}
    review = {
        "support": [{"source": "guitar", "pitch": 64, "start": 1.01, "end": 1.3, "support": .84}],
        "model": "test reviewer", "source_revision": "src", "weights_revision": "weights",
    }
    guarded = precision_judges._annotate_guitar_result(result, review)
    assert len(guarded["events"]) == 1
    assert guarded["events"][0]["pitch"] == 64
    assert "guitar_specialist_support" in guarded["events"][0]["tags"]
    assert guarded["events"][0]["confidence"] > .72


def test_guitar_reviewer_conflict_downweights_but_does_not_generate_or_delete():
    result = {"events": [_guitar_event(.70)]}
    review = {
        "support": [{"source": "guitar", "pitch": 64, "start": 1.0, "end": 1.3, "support": .08}],
        "model": "test reviewer",
    }
    guarded = precision_judges._annotate_guitar_result(result, review)
    assert len(guarded["events"]) == 1
    assert guarded["events"][0]["confidence"] < .70
    assert "guitar_specialist_conflict" in guarded["events"][0]["tags"]


def test_mega53_ownership_only_reweights_existing_event():
    event = MusicEvent.from_dict(_guitar_event(.66))
    precision_judges._STATE.mega53_ownership = [{
        "source": "guitar", "pitch": 64, "start": 1.0, "end": 1.3,
        "preferred": "piano", "guitar_vs_piano_db": -8.0,
    }]
    try:
        guarded = precision_judges._annotate_mega53([event])
    finally:
        delattr(precision_judges._STATE, "mega53_ownership")
    assert len(guarded) == 1
    assert guarded[0].pitch == 64
    assert guarded[0].confidence < event.confidence
    assert "mega53_ownership_conflict" in guarded[0].tags


def test_precision_judges_are_isolated_review_runtimes_and_invalidate_old_cache():
    assert VERSION.endswith("hotfix7")
    assert PIPELINE_VERSION == "band-accurate-9"
    assert PROVIDER_RUNTIME["guitar_review"] == "guitar_review"
    assert PROVIDER_RUNTIME["yourmt3"] == "yourmt3"
    assert PROVIDER_RUNTIME["mega53"] == "mega53"
    assert all(name in RUNTIMES for name in ("guitar_review", "yourmt3", "mega53"))