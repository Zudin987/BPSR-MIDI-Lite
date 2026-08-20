from pathlib import Path


def test_studio_build_is_one_file_and_release_exposes_exe() -> None:
    spec = Path("BPSR-MIDI-Studio.spec").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/build-studio.yml").read_text(encoding="utf-8")

    assert "a.binaries" in spec
    assert "a.datas" in spec
    assert "COLLECT(" not in spec
    assert "exclude_binaries=True" not in spec
    assert "dist/BPSR-MIDI-Studio.exe" in workflow
    assert "release-studio/BPSR-MIDI-Studio.exe" in workflow
    assert "BPSR-MIDI-Studio-Windows-x64.zip" not in workflow


def test_studio_youtube_polish_keeps_results_visible_and_explains_save_quality() -> None:
    polish = Path("studio_polish.py").read_text(encoding="utf-8")
    launcher = Path("studio_launcher.py").read_text(encoding="utf-8")

    assert "_resize_source_notebook" in polish
    assert "<<NotebookTabChanged>>" in polish
    assert "Save MIDI to Local" in polish
    assert "instrumental" in polish
    assert "piano" in polish
    assert "install_studio_polish(app)" in launcher
