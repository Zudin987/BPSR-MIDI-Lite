"""Capture and assert the final responsive Studio UI on the Windows runner."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


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


def inside_horizontally(window, widget) -> bool:
    left = widget.winfo_rootx()
    right = left + widget.winfo_width()
    root_left = window.winfo_rootx()
    root_right = root_left + window.winfo_width()
    return left >= root_left - 2 and right <= root_right + 2


def capture(window, path: Path) -> bool:
    try:
        from PIL import ImageGrab

        window.update_idletasks()
        x, y = window.winfo_rootx(), window.winfo_rooty()
        ImageGrab.grab((x, y, x + window.winfo_width(), y + window.winfo_height())).save(path)
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
            app.minsize(560, 380)
            app.geometry("1280x720+0+0")
            pump(app)
            full_ui._responsive_root(app)
            pump(app)

            initial_profile = app._profile_code() if hasattr(app, "_profile_code") else ""
            checks["initial_profile"] = initial_profile
            assert not app._calibration_panel.winfo_ismapped()
            if initial_profile == "custom":
                assert full_ui._overlay_state(app, "custom").get("visible")
            else:
                assert not app.custom_settings_frame.winfo_ismapped()

            top = app._ux_songs_button.master
            top_text = []
            for widget in top.winfo_children():
                try:
                    if widget.winfo_class() == "TButton":
                        top_text.append(str(widget.cget("text")))
                except Exception:
                    pass
            checks["songs_button_count"] = top_text.count("Songs")
            checks["legacy_library_button_count"] = top_text.count("Library")
            assert checks["songs_button_count"] == 1, top_text
            assert checks["legacy_library_button_count"] == 0, top_text
            assert app._gaming_library_visible
            assert inside_window(app, app.stop_button)
            assert not app._band_window.winfo_viewable(), "Band Room leaked at startup"
            capture(app, reports / "main-1280x720.png")

            full_ui._set_settings_visible(app, True)
            pump(app)
            assert app._gaming_settings_panel.winfo_manager() == "place"
            capture(app, reports / "settings-1280x720.png")
            full_ui._set_settings_visible(app, False)

            advanced_ui._show_custom_panel(app, True)
            pump(app)
            assert full_ui._overlay_state(app, "custom").get("visible")
            capture(app, reports / "custom-tuning-1280x720.png")
            advanced_ui._show_custom_panel(app, False)

            calibration_ui._show_panel(app, True)
            pump(app)
            assert full_ui._overlay_state(app, "calibration").get("visible")
            capture(app, reports / "calibration-1280x720.png")
            calibration_ui._show_panel(app, False)

            # 720p/high-DPI main-player contract.
            app.geometry("720x640+0+0")
            pump(app)
            full_ui._responsive_root(app)
            pump(app)
            assert inside_window(app, app.stop_button)
            assert not app._gaming_library_visible
            assert not app.custom_settings_frame.winfo_ismapped()
            assert not app._calibration_panel.winfo_ismapped()
            capture(app, reports / "main-720x640.png")

            # Calibration retains the compact seven-column reflow and its
            # Studio-only extension controls stay horizontally reachable.
            calibration_ui._show_panel(app, True)
            pump(app)
            full_ui._responsive_root(app)
            pump(app)
            calibration_state = full_ui._overlay_state(app, "calibration")
            assert calibration_state.get("visible")
            assert app._calibration_panel.winfo_width() < 700
            assert int(app._calibration_play_button.grid_info().get("row", -1)) == 4
            for button in app._calibration_feedback_buttons:
                assert int(button.grid_info().get("row", -1)) == 5
                assert inside_horizontally(app, button)

            extension_widgets = []
            for widget in app._calibration_panel.winfo_children():
                remembered = getattr(widget, "_ux_calibration_grid", None)
                if not isinstance(remembered, dict):
                    continue
                try:
                    original_row = int(remembered.get("row", -1))
                except (TypeError, ValueError):
                    continue
                if original_row >= 4:
                    extension_widgets.append(widget)
            assert len(extension_widgets) >= 5
            extension_rows = [int(widget.grid_info().get("row", -1)) for widget in extension_widgets]
            assert min(extension_rows) >= 8, extension_rows
            assert len(extension_rows) == len(set(extension_rows)), extension_rows
            for widget in extension_widgets:
                assert inside_horizontally(app, widget)
            checks["calibration_extension_rows"] = sorted(extension_rows)
            capture(app, reports / "calibration-720x640.png")

            _width, _requested, _viewport, calibration_maximum = full_ui._overlay_geometry(app, "calibration")
            checks["calibration_scroll_needed_720"] = calibration_maximum > 0
            if calibration_maximum > 0:
                full_ui._overlay_scroll_command(app, "calibration", "moveto", "1.0")
                pump(app)
                body_bottom = app._gaming_body.winfo_rooty() + app._gaming_body.winfo_height()
                reset_bottom = app._calibration_reset_button.winfo_rooty() + app._calibration_reset_button.winfo_height()
                assert reset_bottom <= body_bottom + 2
                capture(app, reports / "calibration-720x640-bottom.png")
            calibration_ui._show_panel(app, False)
            pump(app)

            # New requested behavior: checking Band Mode automatically opens a
            # separate workspace window, while the main player remains intact.
            app._band_enabled_var.set(True)
            band_ui._toggle_band_mode(app)
            pump(app)
            assert app._band_window.winfo_viewable()
            assert app._band_window.title() == "Band Room"
            assert app._band_frame.master is app._band_window_body
            assert app._band_frame.winfo_manager() == "grid"
            assert app.winfo_viewable()
            assert inside_horizontally(app._band_window, app._band_download_button)
            assert inside_horizontally(app._band_window, app._band_role_combo)
            capture(app._band_window, reports / "band-room-window.png")
            checks["band_detached_window"] = True

            # Closing the workspace does not silently disable/disconnect Band
            # Mode; the dedicated reopen action restores it.
            app._band_window.event_generate("<Escape>")
            pump(app)
            assert not app._band_window.winfo_viewable()
            assert bool(app._band_enabled_var.get())
            app._ux_band_room_button.invoke()
            pump(app)
            assert app._band_window.winfo_viewable()
            checks["band_reopen_button"] = True

            # Compact/narrow Band Room reflow remains collision-free.
            app._band_window.geometry("600x520+20+20")
            pump(app)
            full_ui._reflow_band_panel(app)
            pump(app)
            rows = []
            for child in app._band_frame.winfo_children():
                info = child.grid_info()
                if info:
                    rows.append((str(child), int(info.get("row", -1))))
            assert len({row for _name, row in rows if row >= 8}) == len([row for _name, row in rows if row >= 8])
            assert inside_horizontally(app._band_window, app._band_download_button)
            capture(app._band_window, reports / "band-room-window-compact.png")

            checks["callbacks"] = errors
            assert not errors, errors
        finally:
            app.destroy()

    (reports / "responsive-ui-checks.json").write_text(
        json.dumps(checks, indent=2, sort_keys=True), encoding="utf-8"
    )
    print("Studio responsive main UI and detached Band Room verified.")


if __name__ == "__main__":
    main()
