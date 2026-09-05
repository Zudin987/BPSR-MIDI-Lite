"""Capture and assert the final responsive Studio UI on the Windows runner."""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path


def pump(app, seconds: float = 0.25) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update()
        time.sleep(0.01)


def inside_window(app, widget) -> bool:
    left = widget.winfo_rootx()
    top = widget.winfo_rooty()
    right = left + widget.winfo_width()
    bottom = top + widget.winfo_height()
    root_left = app.winfo_rootx()
    root_top = app.winfo_rooty()
    root_right = root_left + app.winfo_width()
    root_bottom = root_top + app.winfo_height()
    return (
        left >= root_left - 2
        and top >= root_top - 2
        and right <= root_right + 2
        and bottom <= root_bottom + 2
    )


def capture(app, path: Path) -> bool:
    try:
        from PIL import ImageGrab

        x, y = app.winfo_rootx(), app.winfo_rooty()
        ImageGrab.grab((x, y, x + app.winfo_width(), y + app.winfo_height())).save(path)
        return True
    except OSError as exc:
        print("Desktop capture unavailable:", exc)
        return False


def main() -> None:
    reports = Path("ui-smoke-report")
    reports.mkdir(exist_ok=True)
    checks: dict[str, object] = {}

    with tempfile.TemporaryDirectory() as folder:
        os.environ["BPSR_STUDIO_BAND_HOME"] = str(Path(folder) / "band")

        import band_ui
        import playback_advanced_ui as advanced_ui
        import playback_calibration_ui as calibration_ui
        import studio_launcher
        import ui_full_overhaul_2026 as full_ui

        app = studio_launcher.app.App()
        errors: list[str] = []
        app.report_callback_exception = lambda *error: errors.append(str(error))
        try:
            # Primary target: ordinary 1280x720 desktop. No control should need
            # an oversized window simply to remain reachable.
            app.minsize(560, 380)
            app.geometry("1280x720+0+0")
            pump(app)
            full_ui._responsive_root(app)
            pump(app)
            checks["main_1280x720"] = True
            checks["library_visible_1280"] = bool(app._gaming_library_visible)
            checks["toolbar_visible_1280"] = inside_window(app, app.stop_button)
            assert checks["toolbar_visible_1280"]
            capture(app, reports / "main-1280x720.png")

            full_ui._set_settings_visible(app, True)
            pump(app)
            assert app._gaming_settings_visible
            assert app._gaming_settings_panel.winfo_manager() == "place"
            capture(app, reports / "settings-1280x720.png")
            full_ui._set_settings_visible(app, False)
            checks["settings_overlay"] = True

            advanced_ui._show_custom_panel(app, True)
            pump(app)
            assert full_ui._overlay_state(app, "custom").get("visible")
            capture(app, reports / "custom-tuning-1280x720.png")
            advanced_ui._show_custom_panel(app, False)
            checks["custom_overlay"] = True

            calibration_ui._show_panel(app, True)
            pump(app)
            assert full_ui._overlay_state(app, "calibration").get("visible")
            capture(app, reports / "calibration-1280x720.png")
            calibration_ui._show_panel(app, False)
            checks["calibration_overlay"] = True

            # Also exercise the compact contract where the Library and toolbar
            # must reflow instead of forcing the window wider than requested.
            app.geometry("720x640+0+0")
            pump(app)
            full_ui._responsive_root(app)
            pump(app)
            checks["compact_720x640"] = True
            checks["toolbar_visible_720"] = inside_window(app, app.stop_button)
            checks["library_collapsed_720"] = not bool(app._gaming_library_visible)
            assert checks["toolbar_visible_720"]
            assert checks["library_collapsed_720"]
            capture(app, reports / "main-720x640.png")

            app._band_enabled_var.set(True)
            band_ui._set_band_frame_visible(app, True)
            pump(app)
            full_ui._responsive_root(app)
            pump(app)
            band_state = full_ui._overlay_state(app, "band")
            assert band_state.get("visible")
            assert app._band_frame.winfo_manager() == "place"
            capture(app, reports / "band-room-720x640.png")
            checks["band_overlay_720"] = True

            _width, _requested, _viewport, maximum = full_ui._overlay_geometry(app, "band")
            checks["band_scroll_needed_720"] = maximum > 0
            if maximum > 0:
                scrollbar = band_state.get("scrollbar")
                assert scrollbar is not None and scrollbar.winfo_manager() == "place"
                full_ui._overlay_scroll_command(app, "band", "moveto", "1.0")
                pump(app)
                capture(app, reports / "band-room-720x640-bottom.png")
                body_bottom = app._gaming_body.winfo_rooty() + app._gaming_body.winfo_height()
                download_bottom = app._band_download_button.winfo_rooty() + app._band_download_button.winfo_height()
                assert download_bottom <= body_bottom + 2
                checks["band_bottom_reachable_720"] = True
            else:
                checks["band_bottom_reachable_720"] = inside_window(app, app._band_download_button)

            checks["callbacks"] = errors
            assert not errors, errors
        finally:
            app.destroy()

    (reports / "responsive-ui-checks.json").write_text(
        json.dumps(checks, indent=2, sort_keys=True), encoding="utf-8"
    )
    print("Studio 1280x720 and compact responsive UI verified.")


if __name__ == "__main__":
    main()
