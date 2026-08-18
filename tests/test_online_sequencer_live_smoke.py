from __future__ import annotations

import re
from pathlib import Path

from midi_engine import PlanOptions, build_plan
from online_sequencer import (
    MAX_SEARCH_BYTES,
    SEARCH_URL,
    _request_bytes,
    fetch_sequence_to_cache,
    parse_search_results,
)


def _debug_search_markup(page: str) -> None:
    print("ONLINE_SEARCH_PAGE_LENGTH", len(page))
    lowered = page.casefold()
    for needle in ("zelda", "notes", "sequence", "data-id", "onclick", "href"):
        positions = [match.start() for match in re.finditer(re.escape(needle), lowered)][:8]
        print("NEEDLE", needle, "COUNT_SHOWN", len(positions))
        for pos in positions:
            start = max(0, pos - 260)
            end = min(len(page), pos + 520)
            snippet = re.sub(r"\s+", " ", page[start:end])
            print("SNIPPET", needle, snippet[:900])


def test_live_online_sequencer_search_fetch_and_plan(tmp_path: Path) -> None:
    # Temporary pre-release smoke/debug test. It will be removed before merge so
    # normal project CI never depends on third-party service availability.
    # This commit also retriggers CI after the one-run search-card migration step
    # was added to the trusted base workflow.
    raw = _request_bytes(
        SEARCH_URL.format(query="zelda"),
        timeout=8.0,
        max_bytes=MAX_SEARCH_BYTES,
    )
    page = raw.decode("utf-8", errors="replace")
    results = parse_search_results(page, limit=3)
    if not results:
        _debug_search_markup(page)
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
