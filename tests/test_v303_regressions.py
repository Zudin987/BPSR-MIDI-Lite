from pathlib import Path

import pytest

import online_sequencer as osq


def test_online_ui_keeps_one_loader_and_no_redundant_browser_actions() -> None:
    source = Path("online_ui.py").read_text(encoding="utf-8")

    assert source.count('text="Load link / ID"') == 1
    assert source.count('text="Find online MIDI ID"') == 1
    assert 'text="Check link / ID"' not in source
    assert 'text="Find in browser"' not in source
    assert 'text="Open on Online Sequencer"' not in source


def test_legacy_ui_has_no_online_browser_action() -> None:
    source = Path("app.py").read_text(encoding="utf-8")

    assert "Find Songs Online" not in source
    assert "_open_online_sequencer" not in source
    assert "import webbrowser" not in source


def test_windows_builder_uses_patch_version() -> None:
    source = Path("build_exe.bat").read_text(encoding="utf-8")
    assert "set VERSION=3.0.4" in source


def test_direct_link_still_loads_while_title_text_stays_in_app() -> None:
    result = osq.search_sequences("https://onlinesequencer.net/2553987")
    assert [item.sequence_id for item in result] == [2553987]

    with pytest.raises(osq.OnlineSequencerError, match="no browser was opened"):
        osq.search_sequences("Taylor")
