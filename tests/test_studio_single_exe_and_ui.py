from pathlib import Path


def test_studio_build_is_one_file_and_release_exposes_experimental_exe() -> None:
    spec = Path("BPSR-MIDI-Studio.spec").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/build-studio.yml").read_text(encoding="utf-8")

    assert "a.binaries" in spec
    assert "a.datas" in spec
    assert "COLLECT(" not in spec
    assert "exclude_binaries=True" not in spec
    assert "dist/BPSR-MIDI-Studio.exe" in workflow
    assert "BPSR-MIDI-Studio-Experimental-Beta.exe" in workflow
    assert "BPSR-MIDI-Studio-Windows-x64.zip" not in workflow
    assert "gh release upload $tag" in workflow
    assert "gh release create $tag" not in workflow


def test_studio_youtube_polish_keeps_results_visible_and_explains_save_quality() -> None:
    polish = Path("studio_polish.py").read_text(encoding="utf-8")
    launcher = Path("studio_launcher.py").read_text(encoding="utf-8")
    ui = Path("studio_ui.py").read_text(encoding="utf-8")

    assert "_resize_source_notebook" in polish
    assert "<<NotebookTabChanged>>" in polish
    assert "Save MIDI to Local" in ui
    assert "instrumental" in ui
    assert "piano" in ui
    assert "full vocal/full-band mix" in ui
    assert "install_studio_polish(app)" in launcher


def test_studio_has_visible_working_indicator() -> None:
    ui = Path("studio_ui.py").read_text(encoding="utf-8")

    assert "youtube_progress" in ui
    assert "ttk.Progressbar" in ui
    assert "_progress_start" in ui
    assert "_progress_done" in ui
    assert "The progress bar moves while Studio is working." in ui
