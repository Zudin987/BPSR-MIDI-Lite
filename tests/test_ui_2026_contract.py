from __future__ import annotations

from pathlib import Path


def test_gaming_ui_is_single_window_and_has_anchored_quick_controls() -> None:
    ui = Path("gaming_ui_2026.py").read_text(encoding="utf-8")

    assert "midi_visualizer" in ui
    assert "_toggle_library" in ui
    assert "_toggle_settings" in ui
    assert "Live MIDI" in ui
    assert "Track / channel router" in ui
    assert "Tempo / speed" in ui
    assert "Panic Stop  F10" in ui
    assert 'text="Pause"' in ui
    assert 'text="Play"' in ui
    assert "messagebox.show" not in ui
    assert "Toplevel(" not in ui
    assert "DwmSetWindowAttribute" in ui


def test_compact_runtime_keeps_real_library_watcher_and_pause_responsive() -> None:
    runtime = Path("gaming_runtime_2026.py").read_text(encoding="utf-8")

    assert "modern_ui._poll_song_library" in runtime
    assert "pause_event.is_set()" in runtime
    assert "columnconfigure(0, minsize=0)" in runtime
    assert "columnconfigure(2, minsize=0)" in runtime


def test_live_midi_visualizer_is_capped_at_30_fps() -> None:
    runtime = Path("gaming_runtime_2026.py").read_text(encoding="utf-8")

    assert "VISUALIZER_FPS = 30" in runtime
    assert "VISUALIZER_FRAME_MS = round(1000 / VISUALIZER_FPS)" in runtime
    assert "app.after(VISUALIZER_FRAME_MS" in runtime


def test_lite_and_studio_install_the_same_2026_ui_and_online_title_search() -> None:
    lite = Path("modern_launcher.py").read_text(encoding="utf-8")
    studio = Path("studio_launcher.py").read_text(encoding="utf-8")

    for launcher in (lite, studio):
        assert "install_online_search_bridge()" in launcher
        assert "install_gaming_ui_2026(app)" in launcher
        assert "install_online_search_ui_2026()" in launcher
        assert "install_gaming_runtime_2026(app)" in launcher
        assert "install_playback_overhaul(app)" in launcher
        assert "install_advanced_playback_profile(app)" in launcher
        assert "install_adaptive_arranger(app)" in launcher
        assert "install_calibration_provenance(app)" in launcher
        assert "install_product_ui_overhaul(app)" in launcher
        assert "install_persistent_library(app)" in launcher

    assert 'app.APP_VERSION = "3.4.0"' in lite
    assert 'app.APP_VERSION = "Studio 0.5.0-band-accurate-beta.4"' in studio


def test_online_search_ui_is_search_first_with_verify_fallback() -> None:
    ui = Path("online_search_ui_2026.py").read_text(encoding="utf-8")

    assert 'widget.configure(text="Search")' in ui
    assert 'widget.configure(text="Verify once")' in ui
    assert "No link, ID, or cookie copying is needed." in ui


def test_release_workflows_are_manual_and_cover_product_ui_changes() -> None:
    lite = Path(".github/workflows/build-windows.yml").read_text(encoding="utf-8")
    studio = Path(".github/workflows/build-studio.yml").read_text(encoding="utf-8")

    for workflow in (lite, studio):
        assert "github.event_name == 'workflow_dispatch'" in workflow
        assert "inputs.release_version != ''" in workflow
        assert "[release v3.1.1]" not in workflow
        assert "RELEASE_VERSION: ${{ inputs.release_version }}" in workflow

    # New product UI modules must never bypass the Windows validation matrix.
    assert '- "ui_*.py"' in lite
    assert studio.count('- "ui_*.py"') >= 2
