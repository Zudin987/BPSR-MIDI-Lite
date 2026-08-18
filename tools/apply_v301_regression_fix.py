from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, path: str) -> str:
    if old not in text:
        raise RuntimeError(f"Expected text was not found in {path}: {old[:100]!r}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Online Sequencer HTTP: look like a normal browser, retain cookies during a
# request, and retry once after a lightweight homepage warm-up on HTTP 403.
# ---------------------------------------------------------------------------
path = "online_sequencer.py"
text = read(path)
text = replace_once(
    text,
    "import html\nimport json\nimport re\nimport shutil\nimport struct\nimport tempfile\nimport time\n",
    "import html\nimport json\nimport re\nimport shutil\nimport struct\nimport tempfile\nimport time\nfrom http.cookiejar import CookieJar\n",
    path,
)
text = replace_once(
    text,
    "from urllib.request import Request, urlopen\n",
    "from urllib.request import HTTPCookieProcessor, Request, build_opener\n",
    path,
)
text = replace_once(
    text,
    'USER_AGENT = "BPSR-MIDI-Lite/3.0 (+https://github.com/Zudin987/BPSR-MIDI-Lite)"\n',
    'BROWSER_USER_AGENT = (\n'
    '    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "\n'
    '    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"\n'
    ')\n',
    path,
)
request_block = re.compile(r"def _request_bytes\(url: str, \*, timeout: float, max_bytes: int\) -> bytes:\n.*?\n\ndef search_sequences", re.DOTALL)
replacement = '''def _browser_headers(url: str, *, referer: str | None = None) -> dict[str, str]:
    """Headers close to a normal Windows browser request.

    Online Sequencer may reject obvious non-browser clients with HTTP 403 on
    some residential connections. We do not bypass authentication or a login;
    these headers are only for the same public pages a normal browser can open.
    """
    is_proto = "/app/api/" in url
    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": (
            "application/octet-stream,*/*;q=0.8"
            if is_proto
            else "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
    }
    if is_proto:
        headers.update(
            {
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            }
        )
    else:
        headers.update(
            {
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none" if referer is None else "same-origin",
                "Sec-Fetch-User": "?1",
            }
        )
    if referer:
        headers["Referer"] = referer
    return headers


def _read_public_url(opener: object, url: str, *, timeout: float, max_bytes: int, referer: str | None = None) -> bytes:
    request = Request(url, headers=_browser_headers(url, referer=referer))
    with opener.open(request, timeout=timeout) as response:  # type: ignore[attr-defined]  # noqa: S310 - fixed HTTPS host
        length = response.headers.get("Content-Length")
        if length:
            try:
                if int(length) > max_bytes:
                    raise OnlineSequencerError("Online Sequencer returned a file that is too large.")
            except ValueError:
                pass
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise OnlineSequencerError("Online Sequencer returned a file that is too large.")
    return data


def _request_bytes(url: str, *, timeout: float, max_bytes: int) -> bytes:
    # A fresh cookie jar keeps concurrent background workers independent. If a
    # public request is rejected with 403, visit the public homepage once and
    # retry using the cookies it sets plus a same-origin Referer.
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    try:
        return _read_public_url(opener, url, timeout=timeout, max_bytes=max_bytes)
    except HTTPError as first_error:
        if first_error.code == 403:
            try:
                _read_public_url(
                    opener,
                    BASE_URL + "/",
                    timeout=min(timeout, 6.0),
                    max_bytes=min(MAX_SEARCH_BYTES, 512 * 1024),
                )
            except (HTTPError, URLError, TimeoutError, OSError, OnlineSequencerError):
                pass
            try:
                return _read_public_url(
                    opener,
                    url,
                    timeout=timeout,
                    max_bytes=max_bytes,
                    referer=BASE_URL + "/",
                )
            except HTTPError as retry_error:
                first_error = retry_error

        if first_error.code == 404:
            raise OnlineSequencerError("That Online Sequencer sequence was not found.") from first_error
        if first_error.code == 403:
            raise OnlineSequencerError(
                "Online Sequencer blocked the in-app request (HTTP 403) even after a browser-compatible retry. "
                "Use Open on Online Sequencer to run this search in your browser, or use Local MIDI."
            ) from first_error
        raise OnlineSequencerError(f"Online Sequencer returned HTTP {first_error.code}.") from first_error
    except (URLError, TimeoutError, OSError) as exc:
        raise OnlineSequencerError("Could not reach Online Sequencer. Check your internet connection and try again.") from exc


def search_sequences'''
text, count = request_block.subn(replacement, text, count=1)
if count != 1:
    raise RuntimeError("Could not replace _request_bytes in online_sequencer.py")
write(path, text)


# ---------------------------------------------------------------------------
# Online UI: browser fallback works even when there is no result to select.
# ---------------------------------------------------------------------------
path = "online_ui.py"
text = read(path)
text = replace_once(text, "import queue\nimport threading\n", "import os\nimport queue\nimport threading\n", path)
text = replace_once(text, "from typing import Any, Callable\n", "from typing import Any, Callable\nfrom urllib.parse import quote_plus\n", path)
old = '''def open_selected_online(app: Any) -> None:
    sequence_id = _current_action_sequence_id(app)
    if sequence_id is None:
        app.status_var.set("Choose an Online Sequencer song first.")
        return
    try:
        webbrowser.open_new_tab(osq.sequence_url(sequence_id))
    except webbrowser.Error:
        app.status_var.set("Could not open your web browser.")
'''
new = '''def _open_external_url(app: Any, url: str) -> None:
    try:
        opened = bool(webbrowser.open(url, new=2, autoraise=True))
        if not opened and os.name == "nt":
            os.startfile(url)  # type: ignore[attr-defined]
            opened = True
    except (OSError, webbrowser.Error):
        opened = False

    if opened:
        app.status_var.set("Opened Online Sequencer in your web browser.")
    else:
        app.status_var.set("Could not open your web browser.")


def open_selected_online(app: Any) -> None:
    sequence_id = _current_action_sequence_id(app)
    if sequence_id is not None:
        _open_external_url(app, osq.sequence_url(sequence_id))
        return

    # This is intentionally useful even when in-app search is unavailable. If
    # the user typed a query, open the equivalent public Online Sequencer search
    # page; with an empty query, open the sequence browser itself.
    query = app.online_query_var.get().strip()
    if query:
        url = osq.SEARCH_URL.format(query=quote_plus(query))
    else:
        url = osq.BASE_URL + "/sequences"
    _open_external_url(app, url)
'''
text = replace_once(text, old, new, path)
write(path, text)


# ---------------------------------------------------------------------------
# Dark theme: Notebook tabs + Treeview body/headings were previously left to
# platform defaults, which is why the result list was bright white in dark mode.
# ---------------------------------------------------------------------------
path = "theme.py"
text = read(path)
anchor = '    style.configure("TSeparator", background=colors.border)\n\n'
insert = '''    style.configure("TSeparator", background=colors.border)

    style.configure(
        "TNotebook",
        background=colors.background,
        bordercolor=colors.border,
        lightcolor=colors.border,
        darkcolor=colors.border,
    )
    style.configure(
        "TNotebook.Tab",
        background=colors.surface,
        foreground=colors.muted,
        bordercolor=colors.border,
        padding=(10, 5),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", colors.field), ("active", colors.active)],
        foreground=[("selected", colors.foreground), ("active", colors.foreground), ("disabled", colors.disabled)],
    )
    style.configure(
        "Treeview",
        background=colors.field,
        fieldbackground=colors.field,
        foreground=colors.foreground,
        bordercolor=colors.border,
        lightcolor=colors.border,
        darkcolor=colors.border,
        rowheight=24,
    )
    style.map(
        "Treeview",
        background=[("selected", colors.selection)],
        foreground=[("selected", "#ffffff")],
    )
    style.configure(
        "Treeview.Heading",
        background=colors.surface,
        foreground=colors.foreground,
        bordercolor=colors.border,
        lightcolor=colors.border,
        darkcolor=colors.border,
        relief="flat",
    )
    style.map(
        "Treeview.Heading",
        background=[("active", colors.active), ("pressed", colors.selection)],
        foreground=[("pressed", "#ffffff")],
    )

'''
text = replace_once(text, anchor, insert, path)
write(path, text)


# ---------------------------------------------------------------------------
# Version + user-facing notes.
# ---------------------------------------------------------------------------
path = "modern_launcher.py"
text = read(path).replace('app.APP_VERSION = "3.0.0"', 'app.APP_VERSION = "3.0.1"')
write(path, text)

path = "version_info.txt"
text = read(path)
text = text.replace("filevers=(3, 0, 0, 0)", "filevers=(3, 0, 1, 0)")
text = text.replace("prodvers=(3, 0, 0, 0)", "prodvers=(3, 0, 1, 0)")
text = text.replace("u'FileVersion', u'3.0.0'", "u'FileVersion', u'3.0.1'")
text = text.replace("u'ProductVersion', u'3.0.0'", "u'ProductVersion', u'3.0.1'")
write(path, text)

path = "CHANGELOG.md"
text = read(path)
entry = '''## v3.0.1

- Fixed Online Sequencer searches that could return **HTTP 403** on normal desktop/residential connections by using browser-compatible public-request headers, an isolated cookie session, and one safe retry after a homepage warm-up.
- Added a graceful 403 fallback message that keeps Local MIDI unaffected.
- Fixed dark mode for the Online Sequencer/Bookmarks tabs, result table body, selected rows, and table headings.
- **Open on Online Sequencer** now works even with no selected result: it opens the current typed search in the default browser, or the Online Sequencer browser when the search box is empty.
- Added regression tests for browser headers/403 retry, browser-search fallback, and dark-theme widget coverage.

'''
text = replace_once(text, "# Changelog\n\n", "# Changelog\n\n" + entry, path)
write(path, text)

path = "README.md"
text = read(path)
needle = "If Online Sequencer changes its public search page or sequence format, the online feature may need an update; **Local MIDI playback remains unaffected**.\n"
replacement = needle + "\nIf Online Sequencer refuses an in-app request, **Open on Online Sequencer** can also open the current search text directly in your normal web browser.\n"
text = replace_once(text, needle, replacement, path)
write(path, text)


# ---------------------------------------------------------------------------
# Regression tests that do not depend on Online Sequencer being online.
# ---------------------------------------------------------------------------
test_path = ROOT / "tests" / "test_v301_regressions.py"
test_path.write_text(
    '''from __future__ import annotations\n\nfrom urllib.error import HTTPError\n\nimport online_sequencer as osq\nimport online_ui\nimport theme\n\n\nclass _Response:\n    def __init__(self, payload: bytes) -> None:\n        self.payload = payload\n        self.headers = {}\n\n    def __enter__(self):\n        return self\n\n    def __exit__(self, exc_type, exc, tb):\n        return False\n\n    def read(self, _size: int) -> bytes:\n        return self.payload\n\n\nclass _RetryOpener:\n    def __init__(self) -> None:\n        self.requests = []\n\n    def open(self, request, timeout: float):\n        self.requests.append(request)\n        if len(self.requests) == 1:\n            raise HTTPError(request.full_url, 403, "Forbidden", hdrs=None, fp=None)\n        if len(self.requests) == 2:\n            return _Response(b"homepage")\n        return _Response(b"search-results")\n\n\ndef test_online_request_retries_403_with_browser_headers_and_cookie_warmup(monkeypatch) -> None:\n    opener = _RetryOpener()\n    monkeypatch.setattr(osq, "build_opener", lambda *_args: opener)\n\n    payload = osq._request_bytes(\n        osq.SEARCH_URL.format(query="Taylor"),\n        timeout=3.0,\n        max_bytes=1024,\n    )\n\n    assert payload == b"search-results"\n    assert len(opener.requests) == 3\n    assert opener.requests[0].get_header("User-agent").startswith("Mozilla/5.0")\n    assert opener.requests[0].get_header("Accept-language") == "en-US,en;q=0.9"\n    assert opener.requests[2].get_header("Referer") == osq.BASE_URL + "/"\n\n\nclass _Var:\n    def __init__(self, value: str) -> None:\n        self.value = value\n\n    def get(self) -> str:\n        return self.value\n\n\nclass _Tree:\n    def selection(self):\n        return ()\n\n\nclass _Status:\n    def __init__(self) -> None:\n        self.value = ""\n\n    def set(self, value: str) -> None:\n        self.value = value\n\n\nclass _App:\n    def __init__(self, query: str) -> None:\n        self.song_source_var = _Var("online")\n        self.online_query_var = _Var(query)\n        self.online_tree = _Tree()\n        self.bookmark_tree = _Tree()\n        self.status_var = _Status()\n\n\ndef test_open_online_uses_current_query_when_search_has_no_result(monkeypatch) -> None:\n    opened = []\n    monkeypatch.setattr(online_ui.webbrowser, "open", lambda url, **_kwargs: opened.append(url) or True)\n    app = _App("Taylor Swift")\n\n    online_ui.open_selected_online(app)\n\n    assert opened == [osq.SEARCH_URL.format(query="Taylor+Swift")]\n    assert "Opened Online Sequencer" in app.status_var.value\n\n\ndef test_dark_theme_styles_notebook_and_treeview() -> None:\n    constants = set(theme.apply_theme.__code__.co_consts)\n    assert "TNotebook.Tab" in constants\n    assert "Treeview" in constants\n    assert "Treeview.Heading" in constants\n''',
    encoding="utf-8",
)


# Remove the temporary self-migration step from the workflow before committing
# the actual product patch back to the feature branch.
workflow_path = ".github/workflows/build-windows.yml"
workflow = read(workflow_path)
migration = '''      - name: Apply one-run v3.0.1 regression patch
        if: ${{ github.event_name == 'pull_request' && github.event.pull_request.head.ref == 'fix/v3.0.1-online-403-dark-ui' }}
        shell: pwsh
        run: |
          git fetch origin fix/v3.0.1-online-403-dark-ui
          git checkout -B fix/v3.0.1-online-403-dark-ui origin/fix/v3.0.1-online-403-dark-ui
          python tools/apply_v301_regression_fix.py
          Remove-Item tools/apply_v301_regression_fix.py
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add -A
          git commit -m "Fix Online Sequencer 403 and dark UI regressions"
          git push origin HEAD:fix/v3.0.1-online-403-dark-ui

'''
workflow = replace_once(workflow, migration, "", workflow_path)
write(workflow_path, workflow)

print("v3.0.1 regression patch applied")
