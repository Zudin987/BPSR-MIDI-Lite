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
