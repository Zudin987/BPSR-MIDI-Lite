from pathlib import Path

from local_search_integration import filter_midi_names


def test_local_search_is_case_insensitive_and_matches_all_words() -> None:
    names = [
        "Anime/Blue Bird.mid",
        "Anime/Blue Orchestra Theme.mid",
        "Games/To Zanarkand.mid",
        "Taylor Swift - Love Story.mid",
    ]

    assert filter_midi_names(names, "blue") == names[:2]
    assert filter_midi_names(names, "BLUE bird") == ["Anime/Blue Bird.mid"]
    assert filter_midi_names(names, "love taylor") == ["Taylor Swift - Love Story.mid"]
    assert filter_midi_names(names, "") == names


def test_lite_and_studio_install_the_same_local_search_layer() -> None:
    lite = Path("modern_launcher.py").read_text(encoding="utf-8")
    studio = Path("studio_launcher.py").read_text(encoding="utf-8")

    assert "install_local_search_integration(app)" in lite
    assert "install_local_search_integration(app)" in studio


def test_local_tab_is_folder_search_button_and_scrollable_five_row_results() -> None:
    source = Path("local_search_integration.py").read_text(encoding="utf-8")

    assert "VISIBLE_LOCAL_ROWS = 5" in source
    assert 'text="Open folder"' in source
    assert 'text="Search"' in source
    assert 'height=VISIBLE_LOCAL_ROWS' in source
    assert 'orient="vertical"' in source
    assert "yscrollcommand=scrollbar.set" in source
    assert "trace_add" not in source
    assert "_render_results(app, \"\")" in source
    assert "filter_midi_names(names, query)" in source


def test_local_tab_resizes_after_browser_is_created() -> None:
    source = Path("local_search_integration.py").read_text(encoding="utf-8")

    assert "_resize_source_notebook" in source
    assert "after_idle" in source
    assert "app.after(40" in source
