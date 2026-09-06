from __future__ import annotations

from pathlib import Path


def test_video_audit_layer_fixes_sidebar_and_focus_overlay_defects() -> None:
    source = Path("ui_video_audit_2026.py").read_text(encoding="utf-8")

    assert '"Online Sequencer": "Online"' in source
    assert '"Bookmarks": "Saved"' in source
    assert '"Audio → Band": "Audio"' in source
    assert 'youtube.configure(displaycolumns=("duration",))' in source
    assert 'display = ("fit", "notes") if width >= 340 else ("fit",)' in source
    assert 'state["video_siblings"] = _stash_siblings(panel)' in source
    assert 'app._ux_active_focus_overlay = key' in source
    assert 'close_button = ttk.Button(master, text="Close"' in source


def test_video_audit_layer_fixes_audio_workspace_visual_noise() -> None:
    source = Path("ui_video_audit_2026.py").read_text(encoding="utf-8")

    assert 'owner.workspace.title("Audio → Band")' in source
    assert 'source.configure(text="1. Choose audio")' in source
    assert 'widget.configure(text="Separation")' in source
    assert 'hscroll.grid_remove()' in source
    assert 'owner.bar.configure(mode="determinate", value=0)' in source
    assert "DwmSetWindowAttribute" in source
    assert "DWMWA_USE_IMMERSIVE_DARK_MODE" in source
