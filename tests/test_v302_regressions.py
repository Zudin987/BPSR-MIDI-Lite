from __future__ import annotations

from urllib.error import HTTPError

import pytest

import online_sequencer as osq
import online_ui
import theme


class _Response:
    def __init__(self, payload: bytes, headers: dict[str, str] | None = None) -> None:
        self.payload = payload
        self.headers = headers or {"Content-Type": "application/octet-stream"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, _size: int) -> bytes:
        return self.payload


class _Opener:
    def __init__(self, response: _Response | None = None, status: int | None = None) -> None:
        self.response = response
        self.status = status
        self.requests = []

    def open(self, request, timeout: float):
        self.requests.append(request)
        if self.status is not None:
            raise HTTPError(request.full_url, self.status, "HTTP error", hdrs=None, fp=None)
        return self.response


def test_sequence_data_request_is_honest_and_does_not_retry_403(monkeypatch) -> None:
    opener = _Opener(status=403)
    monkeypatch.setattr(osq, "build_opener", lambda: opener)

    with pytest.raises(osq.OnlineSequencerError, match="public data"):
        osq._request_bytes(osq.PROTO_URL.format(sequence_id=123), timeout=3.0, max_bytes=1024)

    assert len(opener.requests) == 1
    request = opener.requests[0]
    assert request.get_header("User-agent") == osq.DATA_USER_AGENT
    assert request.get_header("Accept") == "application/octet-stream"
    assert request.get_header("Referer") is None
    assert request.get_header("Sec-fetch-mode") is None


def test_cloudflare_html_challenge_is_not_treated_as_sequence_data(monkeypatch) -> None:
    opener = _Opener(
        response=_Response(
            b"<!doctype html><title>Just a moment</title>",
            {"Content-Type": "text/html; charset=UTF-8", "Cf-Mitigated": "challenge"},
        )
    )
    monkeypatch.setattr(osq, "build_opener", lambda: opener)

    with pytest.raises(osq.OnlineSequencerError, match="web browser"):
        osq._request_bytes(osq.PROTO_URL.format(sequence_id=123), timeout=3.0, max_bytes=1024)

    assert len(opener.requests) == 1


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
        self.online_status_var = _Status()
        self.status_var = _Status()


def test_title_search_opens_browser_and_explains_the_copy_link_flow(monkeypatch) -> None:
    opened = []
    monkeypatch.setattr(online_ui.webbrowser, "open", lambda url, **_kwargs: opened.append(url) or True)
    app = _App("Taylor Swift")

    online_ui.search(app)

    assert opened == [osq.search_url("Taylor Swift")]
    assert "copy its address" in app.online_status_var.value
    assert "Local MIDI remains available" in app.status_var.value


def test_find_in_browser_opens_a_pasted_sequence_directly(monkeypatch) -> None:
    opened = []
    monkeypatch.setattr(online_ui.webbrowser, "open", lambda url, **_kwargs: opened.append(url) or True)
    app = _App("https://onlinesequencer.net/2553987")

    online_ui.find_in_browser(app)

    assert opened == [osq.sequence_url(2553987)]
    assert "Opened this sequence" in app.online_status_var.value


def test_browser_open_uses_windows_fallback_when_standard_open_returns_false(monkeypatch) -> None:
    fallback = []
    monkeypatch.setattr(online_ui.webbrowser, "open", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(online_ui.os, "name", "nt")
    monkeypatch.setattr(online_ui.os, "startfile", lambda url: fallback.append(url), raising=False)
    app = _App("")

    opened = online_ui._open_external_url(app, osq.BASE_URL)

    assert opened is True
    assert fallback == [osq.BASE_URL]
    assert "Opened Online Sequencer" in app.status_var.value


def test_open_online_uses_current_query_when_no_result_is_selected(monkeypatch) -> None:
    opened = []
    monkeypatch.setattr(online_ui.webbrowser, "open", lambda url, **_kwargs: opened.append(url) or True)
    app = _App("Taylor Swift")

    online_ui.open_selected_online(app)

    assert opened == [osq.search_url("Taylor Swift")]
    assert "search opened" in app.status_var.value


class _Root:
    def configure(self, **_kwargs) -> None:
        pass

    def tk_setPalette(self, **_kwargs) -> None:
        pass

    def option_add(self, *_args) -> None:
        pass


class _Style:
    def __init__(self) -> None:
        self.configured: dict[str, dict[str, object]] = {}
        self.mapped: dict[str, dict[str, object]] = {}
        self.theme = ""

    def theme_names(self):
        return ("vista", "clam")

    def theme_use(self, name: str) -> None:
        self.theme = name

    def configure(self, name: str, **kwargs) -> None:
        self.configured[name] = kwargs

    def map(self, name: str, **kwargs) -> None:
        self.mapped[name] = kwargs


def test_dark_theme_applies_real_online_notebook_and_table_colors(monkeypatch) -> None:
    monkeypatch.setattr(theme, "_set_titlebar_mode", lambda *_args: None)
    style = _Style()
    colors = theme.theme_colors(True)

    theme.apply_theme(_Root(), style, dark=True)

    assert style.theme == "clam"
    assert style.configured["TNotebook.Tab"]["background"] == colors.surface
    assert style.configured["Treeview"]["background"] == colors.field
    assert style.configured["Treeview"]["foreground"] == colors.foreground
    assert style.configured["Treeview.Heading"]["background"] == colors.surface
    assert style.mapped["Treeview"]["background"] == [("selected", colors.selection)]
