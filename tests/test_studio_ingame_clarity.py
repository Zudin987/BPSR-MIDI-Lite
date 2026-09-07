from __future__ import annotations

from types import SimpleNamespace

from studio_band.gameplay_clarity import clarify_part, choose_other_phrase_owner
from studio_band.gameplay_clarity_patch import _collapse_other_duplicates
from studio_band.music import BeatMap, MasterSong, MusicEvent


def event(
    pitch: int,
    start: float,
    *,
    end: float | None = None,
    role: str = "HARMONY",
    source: str = "piano",
    velocity: int = 78,
    event_id: str = "n",
) -> MusicEvent:
    return MusicEvent(
        source=source,
        role=role,
        start=start,
        end=end if end is not None else start + 0.45,
        pitch=pitch,
        velocity=velocity,
        confidence=0.88,
        engine="fixture",
        event_id=event_id,
    )


def test_dense_piano_chords_reduce_accompaniment_but_keep_melody() -> None:
    events = []
    for index in range(11):
        start = index * 0.10
        events.extend([
            event(72 + index % 3, start, role="MAIN_MELODY", velocity=100, event_id=f"m{index}"),
            event(60, start, event_id=f"h{index}a"),
            event(64, start, event_id=f"h{index}b"),
            event(67, start, event_id=f"h{index}c"),
        ])

    kept, removed, metrics = clarify_part(events, "piano", 4)

    assert {f"m{index}" for index in range(11)} <= {item.event_id for item in kept}
    assert metrics["ingame_clarity_removed"] > 0
    assert any(item["reason"] == "ingame_dense_chord" for item in removed)
    middle = [item for item in kept if abs(item.start - 0.5) <= 0.001]
    assert len(middle) <= 2


def test_moderately_busy_background_drops_decoration_before_harmony() -> None:
    events = []
    for index in range(10):
        start = index * 0.14
        events.extend([
            event(60 + index % 3, start, role="HARMONY", event_id=f"h{index}"),
            event(72 + index % 2, start, role="DECORATION", velocity=70, event_id=f"d{index}"),
        ])

    kept, removed, metrics = clarify_part(events, "piano", 4)

    assert metrics["ingame_clarity_removed"] > 0
    assert any(item["reason"] == "ingame_background_detail" for item in removed)
    middle = [item for item in kept if 0.40 <= item.start <= 0.90]
    assert any(item.role == "HARMONY" for item in middle)
    assert sum(item.role == "DECORATION" for item in middle) < sum(
        item.role == "HARMONY" for item in middle
    )


def test_extreme_soft_background_pressure_can_remove_whole_attacks() -> None:
    events = [
        event(60 + index % 4, index * 0.07, role="HARMONY", velocity=82, event_id=f"h{index}")
        for index in range(16)
    ]

    kept, removed, metrics = clarify_part(events, "piano", 4)

    assert len(kept) < len(events)
    assert metrics["ingame_clarity_removed"] == len(events) - len(kept)
    assert any(item["reason"] == "ingame_accompaniment_attack_pressure" for item in removed)


def test_dense_rhythm_tails_are_gated_before_the_next_attack() -> None:
    events = [
        event(60 + index % 4, index * 0.10, role="RHYTHM", end=index * 0.10 + 0.50,
              velocity=90, event_id=f"r{index}")
        for index in range(12)
    ]

    kept, _removed, metrics = clarify_part(events, "guitar", 3)

    assert metrics["ingame_tails_shortened"] > 0
    assert any("ingame_clarity_gated" in item.tags for item in kept)
    dense = [item for item in kept if 0.35 <= item.start <= 0.75]
    assert dense
    assert max(item.end - item.start for item in dense) <= 0.185


def test_sparse_passage_is_not_flattened() -> None:
    events = [
        event(60, 0.0, end=0.6, event_id="a"),
        event(64, 1.0, end=1.7, event_id="b"),
        event(67, 2.0, end=2.8, event_id="c"),
    ]
    kept, removed, metrics = clarify_part(events, "piano", 4)
    assert [(item.event_id, item.start, item.end) for item in kept] == [
        (item.event_id, item.start, item.end) for item in events
    ]
    assert removed == []
    assert metrics == {"ingame_clarity_removed": 0, "ingame_tails_shortened": 0}


def test_shared_other_phrase_gets_one_owner() -> None:
    chordal = SimpleNamespace(
        scores={"keyboard": 0.68, "guitar": 0.70},
        features=SimpleNamespace(chord_ratio=0.70, melodicness=0.30),
    )
    melodic = SimpleNamespace(
        scores={"keyboard": 0.72, "guitar": 0.71},
        features=SimpleNamespace(chord_ratio=0.10, melodicness=0.90),
    )
    assert choose_other_phrase_owner(chordal, "shared") == "guitar"
    assert choose_other_phrase_owner(melodic, "shared") == "keyboard"
    assert choose_other_phrase_owner(chordal, "bass") == "bass"


def test_duplicate_other_accompaniment_is_removed_from_second_band_part() -> None:
    source = event(64, 0.5, source="other", event_id="other-1")
    master = MasterSong(
        "a" * 64,
        2.0,
        BeatMap(120, [0.0, 0.5, 1.0, 1.5], [], "fixture", 0.9),
        [source],
    )
    piano_copy = event(64, 0.5, source="other", event_id="other-1")
    guitar_copy = event(64, 0.5, source="other", event_id="other-1")
    result = {
        "parts": {"piano": [piano_copy], "guitar": [guitar_copy], "bass": [], "drums": []},
        "summary": {
            "piano": {"notes": 1, "simplified": 0},
            "guitar": {"notes": 1, "simplified": 0},
        },
        "removed": [],
    }

    count = _collapse_other_duplicates(master, result)

    assert count == 1
    assert len(result["parts"]["piano"]) + len(result["parts"]["guitar"]) == 1
    assert result["parts"]["guitar"]
    assert result["removed"][0]["reason"] == "ingame_duplicate_accompaniment_owner"
