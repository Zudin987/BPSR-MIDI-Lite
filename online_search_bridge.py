from __future__ import annotations

import configparser
import html
import os
import re
import sqlite3
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

import online_sequencer as osq


MAX_SEARCH_RESULTS = 12
MAX_SEARCH_BYTES = 2 * 1024 * 1024
_NOTE_COUNT_RE = re.compile(r"([\d,]+)\s+notes?\b", re.IGNORECASE)
_SEQUENCE_LINK_RE = re.compile(
    r'href=["\'](?:https?://onlinesequencer\.net)?/(\d+)(?:[?#][^"\']*)?["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class BrowserSession:
    name: str
    user_agent: str
    cookie_header: str


class _PreviewSearchParser(HTMLParser):
    """Parse Online Sequencer's server-rendered preview cards."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[tuple[int, str, int | None]] = []
        self._card_depth = 0
        self._card_title = ""
        self._card_sequence_id: int | None = None
        self._info_depth: int | None = None
        self._info_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.casefold(): (value or "") for name, value in attrs}
        tag = tag.casefold()
        if self._card_depth == 0:
            classes = {item.casefold() for item in values.get("class", "").split()}
            if tag == "div" and "preview" in classes:
                self._card_depth = 1
                self._card_title = " ".join(values.get("title", "").split())
                self._card_sequence_id = None
                self._info_depth = None
                self._info_parts = []
            return

        if tag == "div":
            self._card_depth += 1
            classes = {item.casefold() for item in values.get("class", "").split()}
            if "info" in classes:
                self._info_depth = self._card_depth
        elif tag == "a":
            match = re.fullmatch(r"/(\d+)/?", values.get("href", "").strip())
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
        if self._card_depth:
            return

        if self._card_sequence_id is not None and self._card_title:
            info = " ".join("".join(self._info_parts).split())
            count_match = _NOTE_COUNT_RE.search(info)
            note_count = int(count_match.group(1).replace(",", "")) if count_match else None
            self.cards.append((self._card_sequence_id, self._card_title, note_count))

        self._card_title = ""
        self._card_sequence_id = None
        self._info_depth = None
        self._info_parts = []


def _clean_text(fragment: str) -> str:
    return " ".join(html.unescape(_TAG_RE.sub(" ", fragment)).split()).strip()


def parse_search_results(page_html: str, limit: int = MAX_SEARCH_RESULTS) -> list[osq.SearchResult]:
    """Return Online Sequencer result cards from browser-visible search HTML."""
    maximum = max(1, int(limit))
    parser = _PreviewSearchParser()
    try:
        parser.feed(page_html)
        parser.close()
    except Exception:
        parser.cards = []

    results: list[osq.SearchResult] = []
    seen: set[int] = set()
    for sequence_id, title, note_count in parser.cards:
        if sequence_id in seen:
            continue
        clean_title = " ".join(html.unescape(title).split())
        if not clean_title:
            continue
        results.append(osq.SearchResult(sequence_id, clean_title[:160], "", note_count))
        seen.add(sequence_id)
        if len(results) >= maximum:
            return results

    # Tolerate the older visible-anchor layout too.
    for match in _SEQUENCE_LINK_RE.finditer(page_html):
        sequence_id = int(match.group(1))
        if sequence_id in seen:
            continue
        title = _clean_text(match.group(2))
        if not title or title.casefold() in {"play", "open", "sequence"}:
            continue
        nearby = _clean_text(page_html[match.end() : match.end() + 1000])
        count_match = _NOTE_COUNT_RE.search(nearby)
        note_count = int(count_match.group(1).replace(",", "")) if count_match else None
        results.append(osq.SearchResult(sequence_id, title[:160], "", note_count))
        seen.add(sequence_id)
        if len(results) >= maximum:
            break
    return results


def _firefox_root() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    root = Path(appdata) / "Mozilla" / "Firefox"
    return root if root.exists() else None


def _profile_paths() -> list[Path]:
    root = _firefox_root()
    if root is None:
        return []
    ini = root / "profiles.ini"
    if not ini.exists():
        return []

    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(ini, encoding="utf-8")
    except (OSError, configparser.Error):
        return []

    candidates: list[tuple[int, Path]] = []
    for section in parser.sections():
        if not section.casefold().startswith("profile"):
            continue
        raw = parser.get(section, "Path", fallback="").strip()
        if not raw:
            continue
        path = Path(raw)
        if parser.get(section, "IsRelative", fallback="1") != "0":
            path = root / path
        rank = 0 if parser.get(section, "Default", fallback="0") == "1" else 1
        if path.exists():
            candidates.append((rank, path))

    # New Firefox installs also record the default profile under [Install...].
    for section in parser.sections():
        if not section.casefold().startswith("install"):
            continue
        raw = parser.get(section, "Default", fallback="").strip()
        if not raw:
            continue
        path = root / raw
        if path.exists():
            candidates.append((-1, path))

    ordered: list[Path] = []
    seen: set[str] = set()
    for _rank, path in sorted(candidates, key=lambda item: item[0]):
        key = str(path.resolve()).casefold()
        if key not in seen:
            seen.add(key)
            ordered.append(path)
    return ordered


def _firefox_major(profile: Path) -> int | None:
    compatibility = profile / "compatibility.ini"
    if compatibility.exists():
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(compatibility, encoding="utf-8")
            raw = parser.get("Compatibility", "LastVersion", fallback="")
            match = re.match(r"(\d+)", raw)
            if match:
                return int(match.group(1))
        except (OSError, configparser.Error, ValueError):
            pass

    for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        base = os.environ.get(env_name)
        if not base:
            continue
        application_ini = Path(base) / "Mozilla Firefox" / "application.ini"
        if not application_ini.exists():
            continue
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(application_ini, encoding="utf-8")
            match = re.match(r"(\d+)", parser.get("App", "Version", fallback=""))
            if match:
                return int(match.group(1))
        except (OSError, configparser.Error, ValueError):
            pass
    return None


def _firefox_user_agent(profile: Path) -> str:
    major = _firefox_major(profile)
    if major is None:
        # Only used for a no-cookie attempt. A clearance cookie is never paired
        # with a guessed UA because Cloudflare can bind clearance to the UA.
        major = 140
    return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{major}.0) Gecko/20100101 Firefox/{major}.0"


def _read_cookie_header(profile: Path) -> str:
    database = profile / "cookies.sqlite"
    if not database.exists():
        return ""
    now = int(time.time())
    try:
        connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True, timeout=2.0)
        try:
            rows = connection.execute(
                "SELECT name, value, expiry FROM moz_cookies "
                "WHERE (host = 'onlinesequencer.net' OR host = '.onlinesequencer.net' "
                "OR host LIKE '%.onlinesequencer.net') "
                "ORDER BY lastAccessed DESC"
            ).fetchall()
        finally:
            connection.close()
    except (OSError, sqlite3.Error):
        return ""

    cookies: dict[str, str] = {}
    for name, value, expiry in rows:
        try:
            expires = int(expiry or 0)
        except (TypeError, ValueError):
            expires = 0
        if expires and expires < now:
            continue
        if name and value and str(name) not in cookies:
            cookies[str(name)] = str(value)
    return "; ".join(f"{name}={value}" for name, value in cookies.items())


def browser_sessions() -> list[BrowserSession]:
    sessions: list[BrowserSession] = []
    for profile in _profile_paths():
        cookie_header = _read_cookie_header(profile)
        if not cookie_header:
            continue
        major = _firefox_major(profile)
        if major is None:
            # Do not risk invalidating a UA-bound Cloudflare clearance cookie.
            continue
        sessions.append(
            BrowserSession(
                name="Firefox",
                user_agent=_firefox_user_agent(profile),
                cookie_header=cookie_header,
            )
        )
    return sessions


def _request_search_html(query: str, session: BrowserSession | None = None) -> str:
    url = f"{osq.BROWSE_URL}?{urllib.parse.urlencode({'search': query})}"
    if session is None:
        profiles = _profile_paths()
        ua = _firefox_user_agent(profiles[0]) if profiles else (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
        )
        cookie = ""
    else:
        ua = session.user_agent
        cookie = session.cookie_header

    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "Referer": osq.BASE_URL + "/",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    if cookie:
        headers["Cookie"] = cookie

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=12.0) as response:  # noqa: S310 - fixed HTTPS host
            raw = response.read(MAX_SEARCH_BYTES + 1)
            content_type = str(response.headers.get("Content-Type", "")).casefold()
            challenged = str(response.headers.get("Cf-Mitigated", "")).casefold() == "challenge"
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise osq.OnlineSequencerError("browser verification required") from exc
        raise osq.OnlineSequencerError(f"Online Sequencer returned HTTP {exc.code} while searching.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise osq.OnlineSequencerError("Could not reach Online Sequencer search.") from exc

    if len(raw) > MAX_SEARCH_BYTES:
        raise osq.OnlineSequencerError("Online Sequencer search returned too much data.")
    text = raw.decode("utf-8", errors="replace")
    if challenged or "just a moment" in text.casefold() or "challenges.cloudflare.com" in text.casefold():
        raise osq.OnlineSequencerError("browser verification required")
    if "text/html" not in content_type and "<html" not in text.casefold():
        raise osq.OnlineSequencerError("Online Sequencer search returned an unexpected response.")
    return text


def search_sequences(query: str) -> list[osq.SearchResult]:
    """Search titles in-app, reusing the user's real Firefox browser session when needed."""
    value = query.strip()
    direct_id = osq.parse_sequence_reference(value)
    if direct_id is not None:
        return [osq.SearchResult(direct_id, f"Sequence #{direct_id}")]
    if not value:
        raise osq.OnlineSequencerError("Enter a song title, Online Sequencer link, or numeric sequence ID.")

    # Try the public page first. Some networks do not receive a challenge.
    try:
        results = parse_search_results(_request_search_html(value), MAX_SEARCH_RESULTS)
        if results:
            return results
    except osq.OnlineSequencerError:
        pass

    # If Cloudflare expects a browser session, reuse the user's Firefox cookies
    # and matching Firefox UA. No cookie text is shown, copied, persisted, or sent
    # anywhere except the same onlinesequencer.net origin.
    for session in browser_sessions():
        try:
            results = parse_search_results(_request_search_html(value, session), MAX_SEARCH_RESULTS)
        except osq.OnlineSequencerError:
            continue
        if results:
            return results

    raise osq.OnlineSequencerError(
        "Online Sequencer needs a one-time browser verification. Click Verify once, "
        "complete the site check in Firefox, then return here and press Search again. "
        "You do not need to copy a link, ID, or cookie."
    )


def verification_url(query: str = "") -> str:
    params = {"search": query.strip()} if query.strip() else {}
    suffix = "?" + urllib.parse.urlencode(params) if params else ""
    return osq.BROWSE_URL + suffix


def _firefox_executable() -> Path | None:
    for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        base = os.environ.get(env_name)
        if base:
            candidate = Path(base) / "Mozilla Firefox" / "firefox.exe"
            if candidate.exists():
                return candidate
    return None


def open_verification(query: str = "") -> bool:
    """Open only the one-time Cloudflare verification page; no copy/paste flow."""
    url = verification_url(query)
    firefox = _firefox_executable()
    if firefox is not None:
        try:
            subprocess.Popen([str(firefox), url], close_fds=True)  # noqa: S603 - fixed installed executable
            return True
        except OSError:
            pass
    try:
        return bool(webbrowser.open(url, new=2, autoraise=True))
    except webbrowser.Error:
        return False


def install_online_search_bridge() -> None:
    """Replace only Online Sequencer title search; direct sequence loading stays untouched."""
    if getattr(osq, "_browser_search_bridge_installed", False):
        return
    osq.search_sequences = search_sequences  # type: ignore[assignment]
    osq._browser_search_bridge_installed = True
