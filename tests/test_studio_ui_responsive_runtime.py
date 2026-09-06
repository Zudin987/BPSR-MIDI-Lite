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


def capture(window, name):
    try:
        from PIL import ImageGrab

        reports = Path("ui-smoke-report")
        reports.mkdir(exist_ok=True)
        x, y = window.winfo_rootx(), window.winfo_rooty()
        ImageGrab.grab((x, y, x + window.winfo_width(), y + window.winfo_height())).save(
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
    app.minsize(560, 380)
    app.geometry("560x700+0+0")
    pump(app)
    assert not app._band_window.winfo_viewable()

    # Checking Band Mode must immediately open a separate Band Room workspace.
    app._band_enabled_var.set(True)
    band_ui._toggle_band_mode(app)
    pump(app)
    assert app._band_window.winfo_viewable()
    assert app._band_window.title() == "Band Room"
    assert app._band_frame.master is app._band_window_body
    assert app._band_frame.winfo_manager() == "grid"
    assert str(app._ux_band_room_button.cget("state")) == "normal"
    assert app.winfo_viewable()

    # Force a compact Band Room viewport and verify the same extension reflow
    # contract that previously protected the in-window overlay.
    app._band_window.geometry("560x520+10+10")
    pump(app)
    full_ui._reflow_band_panel(app)
    pump(app)

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

    # The detached window owns its own vertical scrollbar/canvas, while the main
    # playback toolbar stays reachable and unchanged behind it.
    assert app._band_window_scrollbar.winfo_manager() == "grid"
    assert app._band_window_canvas.winfo_manager() == "grid"
    window_bottom = app.winfo_rooty() + app.winfo_height()
    window_right = app.winfo_rootx() + app.winfo_width()
    toolbar_bottom = app.stop_button.winfo_rooty() + app.stop_button.winfo_height()
    toolbar_right = app.stop_button.winfo_rootx() + app.stop_button.winfo_width()
    assert toolbar_bottom <= window_bottom + 2, (toolbar_bottom, window_bottom)
    assert toolbar_right <= window_right + 2, (toolbar_right, window_right)

    band_right = app._band_window.winfo_rootx() + app._band_window.winfo_width()
    assert app._band_download_button.winfo_rootx() + app._band_download_button.winfo_width() <= band_right + 2
    assert app._band_role_combo.winfo_rootx() + app._band_role_combo.winfo_width() <= band_right + 2
    capture(app._band_window, "band-room-window-compact.png")

    # Closing the Band Room hides only the workspace. The mode remains selected,
    # and the dedicated button can reopen the same window without disconnecting.
    app._band_window.event_generate("<Escape>")
    pump(app)
    assert not app._band_window.winfo_viewable()
    assert bool(app._band_enabled_var.get())
    assert str(app._ux_band_room_button.cget("state")) == "normal"
    app._ux_band_room_button.invoke()
    pump(app)
    assert app._band_window.winfo_viewable()

    # Because Band Room is now a real second window, main-window Settings,
    # Custom tuning, Calibration and Songs no longer have to close it.
    full_ui._set_settings_visible(app, True)
    pump(app)
    assert app._gaming_settings_visible
    assert app._gaming_settings_panel.winfo_manager() == "place"
    assert_overlay_inside_body(app, app._gaming_settings_panel)
    assert app._band_window.winfo_viewable()
    capture(app, "main-settings-compact.png")
    full_ui._set_settings_visible(app, False)

    advanced_ui._show_custom_panel(app, True)
    pump(app)
    assert full_ui._overlay_state(app, "custom").get("visible") is True
    assert app.custom_settings_frame.winfo_manager() == "place"
    assert_overlay_inside_body(app, app.custom_settings_frame)
    assert app._band_window.winfo_viewable()
    advanced_ui._show_custom_panel(app, False)

    calibration_ui._show_panel(app, True)
    pump(app)
    assert full_ui._overlay_state(app, "calibration").get("visible") is True
    assert app._calibration_panel.winfo_manager() == "place"
    assert_overlay_inside_body(app, app._calibration_panel)
    assert app._band_window.winfo_viewable()
    calibration_ui._show_panel(app, False)

    full_ui._hide_library(app)
    full_ui._show_library(app, user_opened=True)
    pump(app)
    assert app._gaming_library_visible and app._ux_library_overlay
    assert app._band_window.winfo_viewable()
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
