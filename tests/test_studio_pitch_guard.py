from __future__ import annotations

from studio_band.music import MusicEvent
from studio_band.pitch_guard import guard_events


def note(pitch, start, end, *, source="guitar", confidence=.7, engine="basic_pitch", event_id="n"):
    return MusicEvent(
        source, "BASS" if source == "bass" else "MAIN_MELODY" if source == "vocals" else "HARMONY",
        start, end, pitch, 80, confidence, engine, event_id=event_id,
    )


def test_pitch_guard_rejects_unsupported_weak_basic_pitch_note():
    event = note(64, 1.0, 1.2, confidence=.42)
    kept, rejected = guard_events([event])
    assert not kept
    assert rejected[0]["reason"] == "unsupported_basic_pitch_activation"


def test_pitch_guard_keeps_independently_supported_weak_note():
    event = note(64, 1.0, 1.2, confidence=.42)
    event.evidence["agreement_engines"] = ["muscriptor"]
    kept, rejected = guard_events([event])
    assert kept == [event]
    assert not rejected


def test_pitch_guard_corrects_isolated_bass_octave_spike():
    events = [
        note(36, 0.0, .3, source="bass", confidence=.85, engine="torchcrepe", event_id="a"),
        note(48, .35, .55, source="bass", confidence=.64, engine="torchcrepe", event_id="bad"),
        note(37, .7, 1.0, source="bass", confidence=.84, engine="torchcrepe", event_id="b"),
    ]
    kept, rejected = guard_events(events)
    repaired = next(event for event in kept if event.event_id == "bad")
    assert repaired.pitch in {36, 37}
    assert "local_octave_glitch_corrected" in repaired.tags
    assert not rejected


def test_pitch_guard_rejects_isolated_polyphonic_register_spike():
    events = [
        note(60, 0.0, .25, source="piano", confidence=.84, engine="transkun", event_id="a"),
        note(84, .3, .42, source="piano", confidence=.72, engine="transkun", event_id="bad"),
        note(62, .6, .9, source="piano", confidence=.84, engine="transkun", event_id="b"),
    ]
    kept, rejected = guard_events(events)
    assert "bad" not in {event.event_id for event in kept}
    assert any(item["reason"] == "isolated_polyphonic_pitch_outlier" for item in rejected)


def test_pitch_guard_does_not_delete_wide_chord():
    events = [
        note(60, 0.0, .3, source="piano", confidence=.84, engine="transkun", event_id="pre"),
        note(48, .35, .8, source="piano", confidence=.74, engine="transkun", event_id="c1"),
        note(60, .35, .8, source="piano", confidence=.74, engine="transkun", event_id="c2"),
        note(72, .35, .8, source="piano", confidence=.74, engine="transkun", event_id="c3"),
        note(62, .9, 1.2, source="piano", confidence=.84, engine="transkun", event_id="post"),
    ]
    kept, rejected = guard_events(events)
    assert {"c1", "c2", "c3"}.issubset({event.event_id for event in kept})
    assert not rejected
