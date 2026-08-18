import online_sequencer as osq
import online_ui


class _Status:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class _BrowserApp:
    def __init__(self) -> None:
        self.online_status_var = _Status()
        self.status_var = _Status()


def test_find_online_midi_id_opens_only_public_sequence_list(monkeypatch) -> None:
    opened: list[tuple[str, int, bool]] = []
    monkeypatch.setattr(
        online_ui.webbrowser,
        "open",
        lambda url, new, autoraise: opened.append((url, new, autoraise)) or True,
    )
    app = _BrowserApp()

    online_ui.find_online_midi_id(app)

    assert opened == [("https://onlinesequencer.net/sequences", 2, True)]
    assert osq.BROWSE_URL == opened[0][0]
    assert "copy its link or numeric ID" in app.online_status_var.value


class _Tab:
    def __init__(self, requested_height: int) -> None:
        self.requested_height = requested_height

    def winfo_reqheight(self) -> int:
        return self.requested_height


class _Notebook:
    def __init__(self) -> None:
        self.height = 0

    def select(self) -> str:
        return "selected-tab"

    def configure(self, *, height: int) -> None:
        self.height = height


class _ResizeApp:
    def __init__(self, requested_height: int) -> None:
        self.song_source_notebook = _Notebook()
        self.tab = _Tab(requested_height)

    def nametowidget(self, _name: str) -> _Tab:
        return self.tab


def test_song_source_notebook_fits_selected_tab_height() -> None:
    app = _ResizeApp(84)

    online_ui._resize_source_notebook(app)

    assert app.song_source_notebook.height == 84
