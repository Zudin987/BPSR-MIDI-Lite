from pathlib import Path

import online_sequencer as osq
import online_ui


class _Tree:
    def __init__(self, item_id: str) -> None:
        self.item_id = item_id
        self.title = ""

    def exists(self, item_id: str) -> bool:
        return item_id == self.item_id

    def item(self, _item_id: str, **values: object) -> None:
        if "text" in values:
            self.title = str(values["text"])


class _App:
    def __init__(self, result: osq.SearchResult) -> None:
        self._online_fetching = {result.sequence_id}
        self._online_cached: dict[int, osq.CachedSequence] = {}
        self._online_results = {result.sequence_id: result}
        self._online_bookmarks = {result.sequence_id: result}
        self._online_pending_saves: set[int] = set()
        self.online_tree = _Tree(f"os:{result.sequence_id}")
        self.bookmark_tree = _Tree(f"bm:{result.sequence_id}")
        self.saved_configs = 0

    def _save_config(self) -> None:
        self.saved_configs += 1


def test_resolved_title_updates_row_and_persisted_bookmark(monkeypatch, tmp_path: Path) -> None:
    sequence_id = 5529399
    generic = osq.SearchResult(sequence_id, f"Sequence #{sequence_id}")
    app = _App(generic)
    cached = osq.CachedSequence(
        sequence_id,
        Path(tmp_path / "cached.mid"),
        "Actually, I'll Take This Too (ULTRAKILL FAN-SONG)",
        "GabrielTheArchangel",
        874,
        0,
        10.0,
    )
    monkeypatch.setattr(online_ui, "_analyze_cached", lambda *_args: None)
    monkeypatch.setattr(online_ui, "_activate_cached_if_selected", lambda *_args: None)

    online_ui._fetch_finished(app, cached)

    renamed = app._online_bookmarks[sequence_id]
    assert renamed.title == cached.title
    assert renamed.author == cached.author
    assert app.online_tree.title.startswith(cached.title)
    assert app.bookmark_tree.title.startswith(cached.title)
    assert app.saved_configs == 1
