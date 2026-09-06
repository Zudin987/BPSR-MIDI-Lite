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

import playback_advanced_ui as advanced_ui
import studio_launcher
import ui_full_overhaul_2026 as full_ui


def pump(app, seconds=.3):
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
    app.minsize(560, 380)
    app.geometry("560x700+0+0")
    pump(app)
    full_ui._responsive_root(app)
    pump(app)

    # MIDI Library already has an outer heading, so the old nested Songs caption
    # is blank rather than repeating the same information.
    nested_titles = []
    for widget in walk(app._gaming_library_panel):
        try:
            if widget.winfo_class() in {"TLabelframe", "Labelframe"}:
                nested_titles.append(str(widget.cget("text")))
        except Exception:
            pass
    assert "Songs" not in nested_titles, nested_titles

    # The second primary selector is a playback profile, not an unlocked-category
    # selector. Custom's summary must also stop directing users to a panel 'below'
    # now that the editor is a focused overlay.
    setup_labels = []
    for widget in walk(app._product_setup_frame):
        try:
            if widget.winfo_class() == "TLabel":
                setup_labels.append(str(widget.cget("text")))
        except Exception:
            pass
    assert "Playback profile" in setup_labels, setup_labels
    assert "Unlocked category" not in setup_labels, setup_labels
    assert "advanced panel below" not in str(app.profile_summary_var.get()).lower(), app.profile_summary_var.get()

    # Reproduce the exact compact Custom-tuning surface that clipped Retrigger
    # gap and its help line in the user's recording.
    advanced_ui._show_custom_panel(app, True)
    pump(app)
    full_ui._responsive_root(app)
    pump(app)
    panel = app.custom_settings_frame
    assert panel.winfo_manager() == "place"
    panel_left = panel.winfo_rootx()
    panel_right = panel_left + panel.winfo_width()
    visible = []
    for widget in panel.winfo_children():
        try:
            if not widget.winfo_ismapped():
                continue
            left = widget.winfo_rootx()
            right = left + widget.winfo_width()
            visible.append((str(widget), widget.winfo_class(), str(widget.cget("text")) if "text" in widget.keys() else "", left, right))
            assert left >= panel_left - 2, (widget, left, panel_left)
            assert right <= panel_right + 2, (widget, right, panel_right)
        except Exception as exc:
            if isinstance(exc, AssertionError):
                raise
    assert any(item[2] == "Retrigger gap" for item in visible), visible
    assert any(item[2] == "ms · 0 = Auto" for item in visible), visible
    assert getattr(panel, "_ux_round3_narrow", None) is True

    hint_target = str(app._advanced_hint_var)
    hint = next(
        widget for widget in panel.winfo_children()
        if widget.winfo_class() == "TLabel" and str(widget.cget("textvariable")) == hint_target
    )
    assert int(float(hint.cget("wraplength"))) <= panel.winfo_width(), hint.cget("wraplength")
    assert hint.winfo_rootx() + hint.winfo_width() <= panel_right + 2
    advanced_ui._show_custom_panel(app, False)
    pump(app)

    # Wide mode restores the original two-field layout instead of permanently
    # turning Custom tuning into a long mobile form.
    app.geometry("1280x720+0+0")
    pump(app)
    advanced_ui._show_custom_panel(app, True)
    pump(app)
    full_ui._responsive_root(app)
    pump(app)
    assert getattr(panel, "_ux_round3_narrow", None) is False
    retrigger = next(widget for widget in panel.winfo_children() if str(widget.cget("text")) == "Retrigger gap")
    assert int(retrigger.grid_info().get("column", -1)) == 2, retrigger.grid_info()
    advanced_ui._show_custom_panel(app, False)

    # Audio labels are user concepts, not internal pipeline terminology.
    audio = app._studio_band_audio
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
    assert "Melody" in texts, texts
    assert "Separation" in texts, texts
    assert "Main Melody" not in texts, texts
    assert "Stem Quality" not in texts, texts
    assert str(audio.resolver_status.get()) == "Automatic download with fallback. Local audio always remains available."
finally:
    app.destroy()
'''


def test_recording_driven_round3_runtime_contract() -> None:
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
            f"beta.8 final recording UI subprocess failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def test_round3_installs_last() -> None:
    launcher = Path("studio_launcher.py").read_text(encoding="utf-8")
    assert launcher.index("install_video_audit_round2()") < launcher.index("install_video_audit_round3()")
