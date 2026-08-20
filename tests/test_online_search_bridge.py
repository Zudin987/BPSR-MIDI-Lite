from __future__ import annotations

import pytest

import online_search_bridge as bridge
import online_sequencer as osq


def test_preview_parser_reads_current_online_sequencer_cards() -> None:
    page = """
    <div class="preview" title="Zelda - Lost Woods">
      <div class="image"></div>
      <div class="info">1,021 notes</div>
      <a href="/5725587"></a>
    </div>
    <div class="preview" title="Piano Cover">
      <div class="info">980 notes</div>
      <a href="/7000001"></a>
    </div>
    """

    results = bridge.parse_search_results(page)

    assert [(r.sequence_id, r.title, r.note_count) for r in results] == [
        (5725587, "Zelda - Lost Woods", 1021),
        (7000001, "Piano Cover", 980),
    ]


def test_preview_parser_deduplicates_sequence_ids() -> None:
    page = """
    <div class="preview" title="First"><div class="info">5 notes</div><a href="/123"></a></div>
    <div class="preview" title="Duplicate"><div class="info">5 notes</div><a href="/123"></a></div>
    """
    assert [item.sequence_id for item in bridge.parse_search_results(page)] == [123]


def test_direct_reference_never_uses_search_page(monkeypatch) -> None:
    monkeypatch.setattr(
        bridge,
        "_request_search_html",
        lambda *_args, **_kwargs: pytest.fail("direct sequence references must not search HTML"),
    )
    result = bridge.search_sequences("https://onlinesequencer.net/5529399")
    assert len(result) == 1
    assert result[0].sequence_id == 5529399


def test_title_search_retries_with_real_browser_session(monkeypatch) -> None:
    calls: list[bridge.BrowserSession | None] = []
    session = bridge.BrowserSession("Firefox", "Firefox/154.0", "cf_clearance=test")

    def fake_request(_query: str, supplied: bridge.BrowserSession | None = None) -> str:
        calls.append(supplied)
        if supplied is None:
            raise osq.OnlineSequencerError("browser verification required")
        return '<div class="preview" title="Song"><div class="info">42 notes</div><a href="/42"></a></div>'

    monkeypatch.setattr(bridge, "_request_search_html", fake_request)
    monkeypatch.setattr(bridge, "browser_sessions", lambda: [session])

    results = bridge.search_sequences("Song")

    assert calls == [None, session]
    assert [(item.sequence_id, item.title) for item in results] == [(42, "Song")]


def test_blocked_search_explains_one_time_verify_without_copying(monkeypatch) -> None:
    monkeypatch.setattr(
        bridge,
        "_request_search_html",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(osq.OnlineSequencerError("blocked")),
    )
    monkeypatch.setattr(bridge, "browser_sessions", lambda: [])

    with pytest.raises(osq.OnlineSequencerError) as error:
        bridge.search_sequences("song title")

    message = str(error.value)
    assert "Verify once" in message
    assert "do not need to copy" in message
