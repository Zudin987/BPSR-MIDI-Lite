from __future__ import annotations

from urllib.error import HTTPError

import online_sequencer as osq
import online_ui
import theme


class _Response:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, _size: int) -> bytes:
        return self.payload


class _RetryOpener:
    def __init__(self) -> None:
        self.requests = []

    def open(self, request, timeout: float):
        self.requests.append(request)
        if len(self.requests) == 1:
            raise HTTPError(request.full_url, 403, "Forbidden", hdrs=None, fp=None)
        if len(self.requests) == 2:
            return _Response(b"homepage")
        return _Response(b"search-results")


def test_online_request_retries_403_with_browser_headers_and_cookie_warmup(monkeypatch) -> None:
    opener = _RetryOpener()
    monkeypatch.setattr(osq, "build_opener", lambda *_args: opener)

    payload = osq._request_bytes(
        osq.SEARCH_URL.format(query="Taylor"),
        timeout=3.0,
        max_bytes=1024,
    )

    assert payload == b"search-results"
    assert len(opener.requests) == 3
    assert opener.requests[0].get_header("User-agent").startswith("Mozilla/5.0")
    assert opener.requests[0].get_header("Accept-language") == "en-US,en;q=0.9"
    assert opener.requests[2].get_header("Referer") == osq.BASE_URL + "/"


class _Var:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class _Tree:
    def selection(self):
        return ()


class _Status:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class _App:
    def __init__(self, query: str) -> None:
        self.song_source_var = _Var("online")
        self.online_query_var = _Var(query)
        self.online_tree = _Tree()
        self.bookmark_tree = _Tree()
        self.status_var = _Status()


def test_open_online_uses_current_query_when_search_has_no_result(monkeypatch) -> None:
    opened = []
    monkeypatch.setattr(online_ui.webbrowser, "open", lambda url, **_kwargs: opened.append(url) or True)
    app = _App("Taylor Swift")

    online_ui.open_selected_online(app)

    assert opened == [osq.SEARCH_URL.format(query="Taylor+Swift")]
    assert "Opened Online Sequencer" in app.status_var.value


def test_dark_theme_styles_notebook_and_treeview() -> None:
    constants = set(theme.apply_theme.__code__.co_consts)
    assert "TNotebook.Tab" in constants
    assert "Treeview" in constants
    assert "Treeview.Heading" in constants
