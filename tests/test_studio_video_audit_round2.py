from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


_STUDIO_RUNTIME_AVAILABLE = (
    importlib.util.find_spec("numpy") is not None
    and importlib.util.find_spec("basic_pitch") is not None
)
pytestmark = pytest.mark.skipif(
    os.name != "nt" or not _STUDIO_RUNTIME_AVAILABLE,
    reason="Windows Studio/Tk recording-driven UI contract",
)


SCRIPT = r'''
import time

import playback_calibration_ui as calibration_ui
import studio_launcher
import ui_full_overhaul_2026 as full_ui


def pump(app, seconds=.25):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update()
        time.sleep(.01)


def walk(root):
    for child in root.winfo_children():
        yield child
        yield from walk(child)


app = studio_launcher.app.App()
try:
    app.geometry("1280x720+0+0")
    pump(app)
    full_ui._responsive_root(app)
    pump(app)

    # The old standalone YouTube -> single-MIDI page is intentionally retired.
    # yt-dlp remains internal for Audio -> Band fallback.
    notebook = app.song_source_notebook
    labels = [str(notebook.tab(i, "text")) for i in range(int(notebook.index("end")))]
    assert labels == ["Local", "Online", "Saved", "Audio"], labels
    assert str(app.youtube_tab) not in tuple(str(value) for value in notebook.tabs())

    # Studio identity is clear without a long build string dominating the header.
    mapped_text = []
    for widget in walk(app):
        try:
            if widget.winfo_ismapped() and widget.winfo_class() == "TLabel":
                mapped_text.append(str(widget.cget("text")))
        except Exception:
            pass
    assert "BPSR MIDI Studio" in mapped_text, mapped_text[:20]
    assert not any(text == "Songs" for text in mapped_text), mapped_text[:20]

    # The collapsed Song Check must not leave an empty Arrangement impact title
    # or decorative divider. With no MIDI selected the analysis parent itself can
    # legitimately remain unmapped even after Details is toggled, so the contract
    # here is state + chrome, not physical visibility of content with no song.
    title = app._ux_arrangement_impact_title
    assert title is not None and not title.winfo_ismapped()
    anchor = app._product_impact_anchor
    assert anchor is not None and not anchor.winfo_ismapped()
    full_ui._toggle_song_details(app)
    pump(app)
    assert bool(app._product_details_visible)
    assert not anchor.winfo_ismapped()
    full_ui._toggle_song_details(app)
    pump(app)
    assert not bool(app._product_details_visible)
    assert not title.winfo_ismapped()
    assert not anchor.winfo_ismapped()

    # 720p compact focused pages keep a real side margin instead of touching the
    # window edges. This also preserves the pre-beta.8 compact Calibration check.
    app.minsize(560, 380)
    app.geometry("720x640+0+0")
    pump(app)
    calibration_ui._show_panel(app, True)
    pump(app)
    full_ui._responsive_root(app)
    pump(app)
    assert full_ui._overlay_state(app, "calibration").get("visible")
    assert app._calibration_panel.winfo_width() <= 688, app._calibration_panel.winfo_width()
    calibration_ui._show_panel(app, False)
    pump(app)

    # Audio -> Band shows user-facing language; downloader implementation detail
    # remains available through the dedicated info control rather than the main
    # status line.
    audio = app._studio_band_audio
    notebook.select(audio.tab)
    app.event_generate("<<NotebookTabChanged>>")
    pump(app)
    assert "YouTube" not in str(app.status_var.get()), app.status_var.get()
    assert "spotDL" not in str(audio.resolver_status.get())
    assert "yt-dlp" not in str(audio.resolver_status.get())
    assert str(audio.status.get()) == "Choose local audio or search for a song to begin."

    audio.open_workspace()
    pump(app)
    texts = []
    for widget in walk(audio.workspace):
        try:
            text = str(widget.cget("text"))
        except Exception:
            continue
        if text:
            texts.append(text)
    assert "Download & Convert" in texts, texts
    assert "Convert audio" in texts, texts
    assert audio.workspace.title() == "Audio → Band"
    assert str(audio.bar.cget("mode")) == "determinate"
    assert int(float(audio.bar.cget("value"))) == 0
finally:
    app.destroy()
'''


def test_recording_driven_round2_runtime_contract() -> None:
    with tempfile.TemporaryDirectory() as folder:
        env = dict(os.environ)
        env["BPSR_STUDIO_BAND_HOME"] = str(Path(folder) / "band")
        result = subprocess.run(
            [sys.executable, "-c", SCRIPT],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            text=True,
            capture_output=True,
            timeout=90,
            check=False,
        )
        assert result.returncode == 0, (
            f"beta.8 recording-driven UI subprocess failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def test_round2_is_installed_after_the_first_video_audit() -> None:
    launcher = Path("studio_launcher.py").read_text(encoding="utf-8")
    first = launcher.index("install_video_audit_ui()")
    compat = launcher.index("install_video_audit_compat()")
    round2 = launcher.index("install_video_audit_round2()")
    assert first < compat < round2
    assert 'app.APP_VERSION = "Studio 0.5.0-band-accurate-beta.8"' in launcher
