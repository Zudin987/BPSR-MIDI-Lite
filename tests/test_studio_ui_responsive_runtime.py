from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows/Tk desktop contract")


def _pump(app, seconds: float = 0.25) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update()
        time.sleep(0.01)


def _row(widget) -> int:
    return int(widget.grid_info().get("row", -1))


def test_compact_band_room_keeps_extension_panels_separate_and_controls_reachable(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as folder:
        monkeypatch.setenv("BPSR_STUDIO_BAND_HOME", str(Path(folder) / "band"))
        import studio_launcher
        import ui_full_overhaul_2026 as full_ui

        app = studio_launcher.app.App()
        try:
            app.geometry("560x700+0+0")
            app._band_frame.grid()
            _pump(app)
            full_ui._responsive_root(app)
            _pump(app)

            status_rows = {
                _row(widget)
                for widget in app._band_frame.winfo_children()
                if widget.winfo_class() == "TLabel"
                and str(widget.cget("textvariable")) in {
                    str(app._band_players_var),
                    str(app._band_room_status_var),
                    str(app._band_part_summary_var),
                }
            }
            lineup_row = _row(app._band_lineup_frame)
            share_row = _row(app._band_share_frame)

            assert status_rows == {5, 6, 7}
            assert lineup_row >= 8
            assert share_row > lineup_row
            assert lineup_row not in status_rows and share_row not in status_rows

            # Room MIDI's long host permission + download controls stack instead
            # of competing on one line at compact widths.
            assert _row(app._band_share_checkbox) == 1
            assert _row(app._band_download_button) == 2

            # The permanent playback toolbar is outside the body and must remain
            # inside the window even while the expanded Band Room is visible.
            window_bottom = app.winfo_rooty() + app.winfo_height()
            toolbar_bottom = app.stop_button.winfo_rooty() + app.stop_button.winfo_height()
            assert toolbar_bottom <= window_bottom + 2

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
