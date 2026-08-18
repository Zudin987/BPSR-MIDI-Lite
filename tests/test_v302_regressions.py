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

    with pytest.raises(osq.OnlineSequencerError, match="blocked access"):
        osq._request_bytes(osq.PROTO_URL.format(sequence_id=123), timeout=3.0, max_bytes=1024)

    assert len(opener.requests) == 1


def test_online_modules_have_no_browser_launcher() -> None:
    assert not hasattr(online_ui, "webbrowser")
    assert not hasattr(online_ui, "find_in_browser")
    assert not hasattr(online_ui, "open_selected_online")
    assert not hasattr(online_ui, "_open_external_url")


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
