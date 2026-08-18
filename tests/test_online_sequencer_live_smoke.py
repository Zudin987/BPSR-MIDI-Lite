from __future__ import annotations

from pathlib import Path

from midi_engine import PlanOptions, build_plan
from online_sequencer import fetch_sequence_to_cache, search_sequences


def test_live_online_sequencer_search_fetch_and_plan(tmp_path: Path) -> None:
    # Temporary pre-release smoke test. It will be removed before merge so
    # normal project CI never depends on third-party service availability.
    results = search_sequences("zelda", limit=3)
    assert results, "Online Sequencer title search returned no parseable results"

    first = results[0]
    cached = fetch_sequence_to_cache(
        first.sequence_id,
        title=first.title,
        author=first.author,
        root=tmp_path / "cache",
        force=True,
    )
    assert cached.path.exists()
    assert cached.path.stat().st_size > 0
    assert cached.note_count > 0

    plan = build_plan(
        cached.path,
        PlanOptions(
            instrument="keyboard",
            mode="stable",
            unlock_tier="tier4",
            mapping_method="transpose",
            max_notes_per_chord=12,
            ignore_percussion=True,
        ),
    )
    assert plan.note_count > 0
    assert plan.page_switches == 0
