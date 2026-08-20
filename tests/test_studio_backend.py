from __future__ import annotations

from pathlib import Path

import studio_youtube as studio


def test_youtube_search_parser_keeps_top_three() -> None:
    rows = [
        {
            "id": f"id{index}",
            "title": f"Song {index}",
            "channel": f"Channel {index}",
            "duration": 200 + index,
        }
        for index in range(1, 6)
    ]
    stdout = "\n".join(__import__("json").dumps(row) for row in rows)
    results = studio.parse_search_output(stdout, limit=3)

    assert [item.video_id for item in results] == ["id1", "id2", "id3"]
    assert results[0].title == "Song 1"
    assert results[0].channel == "Channel 1"
    assert results[0].duration_seconds == 201
    assert results[0].url == "https://www.youtube.com/watch?v=id1"


def test_youtube_search_parser_ignores_noise_and_duplicates() -> None:
    stdout = "\n".join(
        [
            "WARNING: harmless line",
            '{"id":"abc","title":"  First   Song ","uploader":"Uploader","duration":"61.2"}',
            '{"id":"abc","title":"Duplicate"}',
            "not-json",
            '{"id":"","title":"Missing ID"}',
        ]
    )
    results = studio.parse_search_output(stdout)

    assert len(results) == 1
    assert results[0].title == "First Song"
    assert results[0].channel == "Uploader"
    assert results[0].duration_seconds == 61


def test_standard_sha256sum_parser() -> None:
    digest = "ab" * 32
    text = f"{digest}  yt-dlp.exe\n"
    assert studio._parse_sha256_text(text, "yt-dlp.exe") == digest


def test_windows_powershell_sha256_parser() -> None:
    digest = "7FDD1F42E6B0855421ECF27BB406E2492ADE1087C85E30EBF0DEAB6280EA743C"
    text = (
        "Algorithm : SHA256\n"
        f"Hash      : {digest}\n"
        "Path      : C:\\a\\deno\\deno-x86_64-pc-windows-msvc.zip\n"
    )
    assert studio._parse_sha256_text(text, studio.DENO_ZIP_NAME) == digest.lower()


def test_checksum_parser_rejects_non_hash_tokens() -> None:
    assert studio._parse_sha256_text("Algorithm : SHA256\nPath : somewhere") is None


def test_duration_label() -> None:
    assert studio.duration_label(None) == "—"
    assert studio.duration_label(59) == "0:59"
    assert studio.duration_label(61) == "1:01"
    assert studio.duration_label(3661) == "1:01:01"


def test_safe_song_filename() -> None:
    name = studio.safe_song_filename('A <bad> : "song" / test?', "abc")
    assert name.endswith(".mid")
    for char in '<>:"/\\|?*':
        assert char not in name


def test_save_midi_uses_duplicate_safe_name(tmp_path: Path) -> None:
    source = tmp_path / "source.mid"
    source.write_bytes(b"MThd")
    first = studio.save_midi_to_local(source, "Song", "id", tmp_path / "songs")
    second = studio.save_midi_to_local(source, "Song", "id", tmp_path / "songs")
    assert first.name == "Song.mid"
    assert second.name == "Song (2).mid"


def test_lite_import_does_not_require_studio_ai_packages() -> None:
    # Heavy Studio packages are imported only when conversion actually runs.
    assert "basic_pitch" not in studio.__dict__
    assert "imageio_ffmpeg" not in studio.__dict__
