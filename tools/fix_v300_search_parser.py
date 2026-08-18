from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


path = Path("online_sequencer.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    "from dataclasses import dataclass\nfrom pathlib import Path",
    "from dataclasses import dataclass\nfrom html.parser import HTMLParser\nfrom pathlib import Path",
    "HTMLParser import",
)

marker = '''class OnlineSequencerError(RuntimeError):
    """A friendly failure from the optional Online Sequencer integration."""
'''
parser_class = '''class _PreviewSearchParser(HTMLParser):
    """Read current Online Sequencer ``div.preview`` result cards.

    Current public search cards put the sequence title on the card's ``title``
    attribute and use an empty ``<a href=\"/123\"></a>`` as the clickable
    target. HTMLParser is intentionally used instead of one large regex so
    harmless nested markup changes do not break result extraction.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[tuple[int, str, int | None]] = []
        self._card_title = ""
        self._card_sequence_id: int | None = None
        self._card_depth = 0
        self._info_depth: int | None = None
        self._info_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.casefold(): (value or "") for name, value in attrs}
        tag = tag.casefold()

        if self._card_depth == 0:
            classes = {item.casefold() for item in values.get("class", "").split()}
            if tag == "div" and "preview" in classes:
                self._card_title = " ".join(values.get("title", "").split())
                self._card_sequence_id = None
                self._card_depth = 1
                self._info_depth = None
                self._info_parts = []
            return

        if tag == "div":
            self._card_depth += 1
            classes = {item.casefold() for item in values.get("class", "").split()}
            if "info" in classes:
                self._info_depth = self._card_depth
        elif tag == "a":
            match = re.fullmatch(r"/(\\d+)/?", values.get("href", "").strip())
            if match:
                self._card_sequence_id = int(match.group(1))

    def handle_data(self, data: str) -> None:
        if self._card_depth and self._info_depth is not None:
            self._info_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._card_depth == 0 or tag.casefold() != "div":
            return
        if self._info_depth == self._card_depth:
            self._info_depth = None
        self._card_depth -= 1
        if self._card_depth != 0:
            return

        if self._card_sequence_id is not None and self._card_title:
            info = " ".join("".join(self._info_parts).split())
            match = _NOTE_COUNT_RE.search(info)
            note_count = int(match.group(1).replace(",", "")) if match else None
            self.cards.append((self._card_sequence_id, self._card_title, note_count))

        self._card_title = ""
        self._card_sequence_id = None
        self._info_depth = None
        self._info_parts = []


class OnlineSequencerError(RuntimeError):
    """A friendly failure from the optional Online Sequencer integration."""
'''
text = replace_once(text, marker, parser_class, "preview parser class")

old_function = '''def parse_search_results(page_html: str, limit: int = MAX_SEARCH_RESULTS) -> list[SearchResult]:
    """Parse public sequence cards without depending on one CSS class name."""
    results: list[SearchResult] = []
    seen: set[int] = set()

    for match in _SEQUENCE_LINK_RE.finditer(page_html):
        sequence_id = int(match.group(1))
        if sequence_id in seen:
            continue
        title = _clean_text(match.group(2))
        if not title or title.casefold() in {"play", "open", "sequence"}:
            continue

        # Metadata sits close to the sequence link on the public browser page.
        # Keep this deliberately best-effort; title + ID are sufficient to use
        # a result even if Online Sequencer changes the surrounding markup.
        nearby = page_html[match.end() : match.end() + 1200]
        author_match = _AUTHOR_RE.search(nearby)
        author = _clean_text(author_match.group(1)) if author_match else ""
        count_match = _NOTE_COUNT_RE.search(_clean_text(nearby))
        note_count = int(count_match.group(1).replace(",", "")) if count_match else None

        seen.add(sequence_id)
        results.append(SearchResult(sequence_id, title[:160], author[:80], note_count))
        if len(results) >= max(1, int(limit)):
            break

    return results
'''
new_function = '''def parse_search_results(page_html: str, limit: int = MAX_SEARCH_RESULTS) -> list[SearchResult]:
    """Parse the current public preview cards, with a legacy-anchor fallback."""
    maximum = max(1, int(limit))
    parser = _PreviewSearchParser()
    try:
        parser.feed(page_html)
        parser.close()
    except Exception:  # HTMLParser is best-effort; legacy fallback remains below.
        parser.cards = []

    results: list[SearchResult] = []
    seen: set[int] = set()
    for sequence_id, title, note_count in parser.cards:
        if sequence_id in seen:
            continue
        clean_title = " ".join(html.unescape(title).split())
        if not clean_title:
            continue
        seen.add(sequence_id)
        results.append(SearchResult(sequence_id, clean_title[:160], "", note_count))
        if len(results) >= maximum:
            return results

    # Older versions of the public page used visible sequence-link text. Keep
    # this small fallback because it costs nothing and makes the client tolerant
    # of the site switching between those two server-rendered layouts.
    for match in _SEQUENCE_LINK_RE.finditer(page_html):
        sequence_id = int(match.group(1))
        if sequence_id in seen:
            continue
        title = _clean_text(match.group(2))
        if not title or title.casefold() in {"play", "open", "sequence"}:
            continue
        nearby = page_html[match.end() : match.end() + 1200]
        author_match = _AUTHOR_RE.search(nearby)
        author = _clean_text(author_match.group(1)) if author_match else ""
        count_match = _NOTE_COUNT_RE.search(_clean_text(nearby))
        note_count = int(count_match.group(1).replace(",", "")) if count_match else None
        seen.add(sequence_id)
        results.append(SearchResult(sequence_id, title[:160], author[:80], note_count))
        if len(results) >= maximum:
            break

    return results
'''
text = replace_once(text, old_function, new_function, "search parser function")
path.write_text(text, encoding="utf-8")


path = Path("tests/test_online_sequencer.py")
text = path.read_text(encoding="utf-8")
old_test = '''def test_search_parser_is_tolerant_and_deduplicates() -> None:
    page = """
    <div class="sequence-card">
      <a href="/111">Song &amp; One</a>
      by <a href="/members/abc">Alice</a>
      <span>1,234 notes</span>
    </div>
    <a href="https://onlinesequencer.net/222?x=1"><b>Song Two</b></a>
    <span>55 notes</span>
    <a href="/111">Song &amp; One</a>
    """
    results = parse_search_results(page)
    assert [item.sequence_id for item in results] == [111, 222]
    assert results[0].title == "Song & One"
    assert results[0].author == "Alice"
    assert results[0].note_count == 1234
    assert results[1].title == "Song Two"
    assert results[1].note_count == 55
'''
new_test = '''def test_search_parser_reads_current_preview_cards_and_deduplicates() -> None:
    page = """
    <div id="page_right"><div class="right_column">
      <div class="preview" title="Song &amp; One">
        <div class="image" style="background-image:url(/t/11/111.gif)"></div>
        <div class="info">1,234 notes</div>
        <a href="/111"></a>
      </div>
      <div class="preview" title="Song Two">
        <div class="image"></div><div class="info">55 notes</div><a href="/222"></a>
      </div>
      <div class="preview" title="Duplicate"><div class="info">9 notes</div><a href="/111"></a></div>
    </div></div>
    """
    results = parse_search_results(page)
    assert [item.sequence_id for item in results] == [111, 222]
    assert results[0].title == "Song & One"
    assert results[0].author == ""
    assert results[0].note_count == 1234
    assert results[1].title == "Song Two"
    assert results[1].note_count == 55


def test_search_parser_keeps_legacy_visible_anchor_fallback() -> None:
    page = """
    <a href="/333">Legacy Song</a>
    by <a href="/members/abc">Alice</a>
    <span>77 notes</span>
    """
    results = parse_search_results(page)
    assert [item.sequence_id for item in results] == [333]
    assert results[0].title == "Legacy Song"
'''
text = replace_once(text, old_test, new_test, "search parser test")
path.write_text(text, encoding="utf-8")

print("Updated Online Sequencer parser for current preview-card search markup")
