from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows/Tk desktop contract")


SCRIPT = r'''
import time
from pathlib import Path

import studio_launcher
import ui_full_overhaul_2026 as full_ui


def pump(app, seconds=.25):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update()
        time.sleep(.01)


def row(widget):
    return int(widget.grid_info().get("row", -1))


app = studio_launcher.app.App()
try:
    app.geometry("560x700+0+0")
    app._band_frame.grid()
    pump(app)
    full_ui._responsive_root(app)
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

    window_bottom = app.winfo_rooty() + app.winfo_height()
    toolbar_bottom = app.stop_button.winfo_rooty() + app.stop_button.winfo_height()
    assert toolbar_bottom <= window_bottom + 2, (toolbar_bottom, window_bottom)

    reports = Path("ui-smoke-report")
    reports.mkdir(exist_ok=True)
    try:
        from PIL import ImageGrab

        x, y = app.winfo_rootx(), app.winfo_rooty()
        ImageGrab.grab((x, y, x + app.winfo_width(), y + app.winfo_height())).save(
            reports / "main-band-room-compact.png"
        )
    except OSError:
        pass
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
