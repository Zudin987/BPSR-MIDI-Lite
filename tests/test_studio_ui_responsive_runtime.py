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
    reason="Windows Studio/Tk desktop contract",
)


SCRIPT = r'''
import time
from pathlib import Path

import band_ui
import playback_advanced_ui as advanced_ui
import playback_calibration_ui as calibration_ui
import studio_launcher
import ui_full_overhaul_2026 as full_ui


def pump(app, seconds=.25):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update()
        time.sleep(.01)


def row(widget):
    return int(widget.grid_info().get("row", -1))


def capture(app, name):
    try:
        from PIL import ImageGrab

        reports = Path("ui-smoke-report")
        reports.mkdir(exist_ok=True)
        x, y = app.winfo_rootx(), app.winfo_rooty()
        ImageGrab.grab((x, y, x + app.winfo_width(), y + app.winfo_height())).save(
            reports / name
        )
    except OSError:
        pass


def assert_overlay_inside_body(app, panel):
    body = app._gaming_body
    left = panel.winfo_rootx()
    right = left + panel.winfo_width()
    body_left = body.winfo_rootx()
    body_right = body_left + body.winfo_width()
    assert left >= body_left - 2, (left, body_left)
    assert right <= body_right + 2, (right, body_right)


app = studio_launcher.app.App()
try:
    # The normal product min-width can be larger on a roomy CI desktop. Lower
    # it explicitly so this regression test also exercises the emergency
    # compact contract rather than silently staying at 720+ logical pixels.
    app.minsize(560, 380)
    app.geometry("560x700+0+0")
    pump(app)
    app._band_enabled_var.set(True)
    band_ui._set_band_frame_visible(app, True)
    pump(app)
    full_ui._responsive_root(app)
    pump(app)

    state = full_ui._overlay_state(app, "band")
    assert state.get("visible") is True
    assert app._band_frame.winfo_manager() == "place"
    assert app._band_frame.winfo_width() < 560, app._band_frame.winfo_width()
    assert str(app._ux_band_room_button.cget("state")) == "normal"
    assert_overlay_inside_body(app, app._band_frame)

    status_rows = {
        row(widget)
        for widget in app._band_frame.winfo_children()
        if widget.winfo_class() == "TLabel"
        and str(widget.cget("textvariable")) in {
            str(app._band_players_var),
            str(app._band_room_status_var),
            str(app._band_part_summary_var),
        }
    }
    lineup_row = row(app._band_lineup_frame)
    share_row = row(app._band_share_frame)

    assert status_rows == {5, 6, 7}, status_rows
    assert lineup_row >= 8, lineup_row
    assert share_row > lineup_row, (lineup_row, share_row)
    assert lineup_row not in status_rows and share_row not in status_rows
    assert row(app._band_share_checkbox) == 1
    assert row(app._band_download_button) == 2

    # The permanent playback toolbar must stay both vertically and horizontally
    # reachable while the secondary Band Room overlay is open.
    window_bottom = app.winfo_rooty() + app.winfo_height()
    window_right = app.winfo_rootx() + app.winfo_width()
    toolbar_bottom = app.stop_button.winfo_rooty() + app.stop_button.winfo_height()
    toolbar_right = app.stop_button.winfo_rootx() + app.stop_button.winfo_width()
    assert toolbar_bottom <= window_bottom + 2, (toolbar_bottom, window_bottom)
    assert toolbar_right <= window_right + 2, (toolbar_right, window_right)

    capture(app, "main-band-room-compact.png")

    # If the Band Room is taller than the compact viewport, the final UI must
    # expose a scrollbar and make the bottom Room MIDI controls reachable.
    _width, _requested, _viewport, maximum = full_ui._overlay_geometry(app, "band")
    body_bottom = app._gaming_body.winfo_rooty() + app._gaming_body.winfo_height()
    if maximum > 0:
        scrollbar = state.get("scrollbar")
        assert scrollbar is not None and scrollbar.winfo_manager() == "place"
        full_ui._overlay_scroll_command(app, "band", "moveto", "1.0")
        pump(app)
        capture(app, "main-band-room-compact-bottom.png")
    share_bottom = app._band_share_frame.winfo_rooty() + app._band_share_frame.winfo_height()
    download_bottom = app._band_download_button.winfo_rooty() + app._band_download_button.winfo_height()
    assert share_bottom <= body_bottom + 2, (share_bottom, body_bottom)
    assert download_bottom <= body_bottom + 2, (download_bottom, body_bottom)

    # Closing the overlay keeps Band Mode selected and exposes a direct reopen
    # action instead of requiring the user to toggle the feature off/on.
    full_ui._hide_feature_overlay(app, "band")
    pump(app)
    assert not full_ui._overlay_state(app, "band").get("visible")
    assert bool(app._band_enabled_var.get())
    assert str(app._ux_band_room_button.cget("state")) == "normal"

    # Secondary interfaces are real responsive surfaces too, not just the main
    # page. Exercise Settings, Custom tuning and Calibration at the same width.
    full_ui._set_settings_visible(app, True)
    pump(app)
    assert app._gaming_settings_visible
    assert app._gaming_settings_panel.winfo_manager() == "place"
    assert_overlay_inside_body(app, app._gaming_settings_panel)
    capture(app, "main-settings-compact.png")
    full_ui._set_settings_visible(app, False)

    advanced_ui._show_custom_panel(app, True)
    pump(app)
    custom_state = full_ui._overlay_state(app, "custom")
    assert custom_state.get("visible") is True
    assert app.custom_settings_frame.winfo_manager() == "place"
    assert_overlay_inside_body(app, app.custom_settings_frame)
    capture(app, "main-custom-tuning-compact.png")
    advanced_ui._show_custom_panel(app, False)

    calibration_ui._show_panel(app, True)
    pump(app)
    calibration_state = full_ui._overlay_state(app, "calibration")
    assert calibration_state.get("visible") is True
    assert app._calibration_panel.winfo_manager() == "place"
    assert_overlay_inside_body(app, app._calibration_panel)
    capture(app, "main-calibration-compact.png")
    calibration_ui._show_panel(app, False)

    # Do not allow two independent side/feature overlays to pile on top of each
    # other. Opening Settings, Custom tuning, or user-opened Songs replaces Band.
    band_ui._set_band_frame_visible(app, True)
    pump(app)
    assert full_ui._overlay_state(app, "band").get("visible")
    full_ui._set_settings_visible(app, True)
    pump(app)
    assert not full_ui._overlay_state(app, "band").get("visible")
    assert app._gaming_settings_visible
    full_ui._set_settings_visible(app, False)

    band_ui._set_band_frame_visible(app, True)
    pump(app)
    advanced_ui._show_custom_panel(app, True)
    pump(app)
    assert not full_ui._overlay_state(app, "band").get("visible")
    assert full_ui._overlay_state(app, "custom").get("visible")
    advanced_ui._show_custom_panel(app, False)

    band_ui._set_band_frame_visible(app, True)
    pump(app)
    full_ui._hide_library(app)
    full_ui._show_library(app, user_opened=True)
    pump(app)
    assert not full_ui._overlay_state(app, "band").get("visible")
    assert app._gaming_library_visible and app._ux_library_overlay
    full_ui._hide_library(app)
finally:
    app.destroy()
'''


def test_compact_band_room_keeps_extension_panels_separate_and_controls_reachable() -> None:
    with tempfile.TemporaryDirectory() as folder:
        env = dict(os.environ)
        env["BPSR_STUDIO_BAND_HOME"] = str(Path(folder) / "band")
        result = subprocess.run(
            [sys.executable, "-c", SCRIPT],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, (
            f"compact Studio UI subprocess failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
