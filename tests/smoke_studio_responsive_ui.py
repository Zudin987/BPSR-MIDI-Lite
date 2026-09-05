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


def inside_window_horizontally(app, widget) -> bool:
    left = widget.winfo_rootx()
    right = left + widget.winfo_width()
    root_left = app.winfo_rootx()
    root_right = root_left + app.winfo_width()
    return left >= root_left - 2 and right <= root_right + 2


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

            # Calibration is not a selected product mode and must never leak out
            # of its overlay during construction. Custom tuning is different: a
            # saved Custom profile legitimately opens its tuning surface, so test
            # that state according to the active profile instead of assuming it
            # is always hidden.
            initial_profile = app._profile_code() if hasattr(app, "_profile_code") else ""
            checks["initial_profile"] = initial_profile
            checks["calibration_hidden_initially"] = not bool(app._calibration_panel.winfo_ismapped())
            assert checks["calibration_hidden_initially"]
            if initial_profile == "custom":
                checks["custom_profile_overlay_initially"] = bool(
                    full_ui._overlay_state(app, "custom").get("visible")
                )
                assert checks["custom_profile_overlay_initially"]
            else:
                checks["custom_hidden_initially"] = not bool(app.custom_settings_frame.winfo_ismapped())
                assert checks["custom_hidden_initially"]

            # There is one Song Library action, not a generated Songs button
            # sitting on top of the legacy Library button in the same grid cell.
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
            assert app._ux_songs_button.winfo_manager(), "Songs action exists but is not mapped"

            checks["main_1280x720"] = True
            checks["library_visible_1280"] = bool(app._gaming_library_visible)
            checks["toolbar_visible_1280"] = inside_window(app, app.stop_button)
            assert checks["library_visible_1280"]
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
            assert not app.custom_settings_frame.winfo_ismapped()
            assert not app._calibration_panel.winfo_ismapped()
            capture(app, reports / "main-720x640.png")

            # Calibration used to retain its seven-column desktop form here,
            # clipping Value and feedback controls off the right edge. At compact
            # width it must stack into the responsive rows and remain horizontally
            # reachable, while the generic overlay can handle vertical scrolling.
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
                assert inside_window_horizontally(app, button), (
                    button.cget("text"),
                    button.winfo_rootx(),
                    button.winfo_width(),
                    app.winfo_width(),
                )
            value_spin = next(
                widget
                for widget in app._calibration_panel.winfo_children()
                if widget.winfo_class() == "TSpinbox"
                and str(widget.cget("textvariable")) == str(app._calibration_value_var)
            )
            assert inside_window_horizontally(app, value_spin)
            capture(app, reports / "calibration-720x640.png")
            calibration_ui._show_panel(app, False)
            pump(app)
            checks["calibration_compact_no_horizontal_clip"] = True

            app._band_enabled_var.set(True)
            band_ui._set_band_frame_visible(app, True)
            pump(app)
            full_ui._responsive_root(app)
            pump(app)
            band_state = full_ui._overlay_state(app, "band")
            assert band_state.get("visible")
            assert app._band_frame.winfo_manager() == "place"
            assert not app.custom_settings_frame.winfo_ismapped()
            assert not app._calibration_panel.winfo_ismapped()
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
