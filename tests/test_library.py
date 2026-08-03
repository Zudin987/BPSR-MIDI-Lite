from pathlib import Path

from app import scan_midi_folder


def test_scan_midi_folder_finds_mid_and_midi_recursively(tmp_path: Path) -> None:
    (tmp_path / "10_song.mid").write_bytes(b"")
    (tmp_path / "2_song.MID").write_bytes(b"")
    sub = tmp_path / "Anime"
    sub.mkdir()
    (sub / "1_theme.midi").write_bytes(b"")
    (sub / "notes.txt").write_text("ignore", encoding="utf-8")

    found = scan_midi_folder(tmp_path)
    relative = [path.relative_to(tmp_path).as_posix() for path in found]

    assert relative == ["2_song.MID", "10_song.mid", "Anime/1_theme.midi"]


def test_scan_midi_folder_returns_empty_for_missing_folder(tmp_path: Path) -> None:
    assert scan_midi_folder(tmp_path / "missing") == []
