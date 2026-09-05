"""Recording-driven smoke for the beta.8 UI cleanup.

This specifically guards defects visible in the user's 77.8-second desktop
recording: clipped Library tabs/columns, leaking focused surfaces, detached
Close/scroll chrome, stale Audio-tab copy, obsolete duplicate YouTube UI and
always-visible Audio table horizontal scrollbars/progress state.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def pump(app, seconds: float = 0.3) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update()
        time.sleep(0.01)


def capture(window, path: Path) -> None:
    try:
        from PIL import ImageGrab

        window.update_idletasks()
        x, y = window.winfo_rootx(), window.winfo_rooty()
        ImageGrab.grab((x, y, x + window.winfo_width(), y + window.winfo_height())).save(path)
    except OSError as exc:
        print("Desktop capture unavailable:", exc)


def mapped_content_siblings(panel, *chrome) -> list[str]:
    ignored = {widget for widget in chrome if widget is not None}
    result: list[str] = []
    for widget in panel.master.winfo_children():
        if widget is panel or widget in ignored:
            continue
        try:
            if widget.winfo_ismapped():
                result.append(str(widget))
        except Exception:
            pass
    return result


def main() -> None:
    reports = Path("ui-smoke-report")
    reports.mkdir(exist_ok=True)
    checks: dict[str, object] = {}

    with tempfile.TemporaryDirectory() as folder:
        os.environ["BPSR_STUDIO_BAND_HOME"] = str(Path(folder) / "band")
        import band_ui
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

            notebook = app.song_source_notebook
            labels = [str(notebook.tab(i, "text")) for i in range(int(notebook.index("end")))]
            checks["library_tabs"] = labels
            assert labels == ["Local", "Online", "Saved", "Audio"], labels
            assert str(app.youtube_tab) not in tuple(str(value) for value in notebook.tabs())
            for index in range(len(labels)):
                x, _y, width, _height = notebook.bbox(index)
                assert x + width <= notebook.winfo_width() + 2, (index, labels[index], x, width, notebook.winfo_width())

            for tree in (app.online_tree, app.bookmark_tree):
                display = tuple(str(value) for value in tree.cget("displaycolumns"))
                assert "changes" not in display, display
                assert display in {("fit",), ("fit", "notes")}, display

            # The collapsed Song Check should not leave an empty technical
            # section title/divider in the normal workflow.
            assert app._ux_arrangement_impact_title is not None
            assert not app._ux_arrangement_impact_title.winfo_ismapped()
            assert not app._product_impact_anchor.winfo_ismapped()
            capture(app, reports / "video-audit-main-1280x720.png")

            # Settings is a focused surface now: it must not sit as a narrow
            # transparent-looking strip over the player.
            full_ui._set_settings_visible(app, True)
            pump(app)
            settings_state = full_ui._overlay_state(app, "settings")
            assert settings_state.get("visible")
            assert app._gaming_settings_panel.winfo_manager() == "place"
            assert settings_state["close_button"].master is app._gaming_settings_panel.master
            if settings_state.get("scrollbar") is not None:
                assert settings_state["scrollbar"].master is app._gaming_settings_panel.master
            settings_leaks = mapped_content_siblings(
                app._gaming_settings_panel,
                settings_state.get("close_button"),
                settings_state.get("scrollbar"),
            )
            assert not settings_leaks, settings_leaks
            capture(app, reports / "video-audit-settings-1280x720.png")
            full_ui._set_settings_visible(app, False)
            pump(app)

            # Band Room should replace the center workflow, not float over Song
            # Check/Live MIDI with a detached Close button.
            app._band_enabled_var.set(True)
            band_ui._set_band_frame_visible(app, True)
            pump(app)
            full_ui._responsive_root(app)
            pump(app)
            band_state = full_ui._overlay_state(app, "band")
            assert band_state.get("visible")
            assert app._band_frame.winfo_manager() == "place"
            assert band_state["close_button"].master is app._band_frame.master
            if band_state.get("scrollbar") is not None:
                assert band_state["scrollbar"].master is app._band_frame.master
            band_leaks = mapped_content_siblings(
                app._band_frame,
                band_state.get("close_button"),
                band_state.get("scrollbar"),
            )
            assert not band_leaks, band_leaks
            capture(app, reports / "video-audit-band-room-1280x720.png")
            full_ui._hide_feature_overlay(app, "band")
            pump(app)

            # Compact focused surfaces keep a real side margin instead of
            # touching both window edges at 720 logical pixels.
            app.geometry("720x640+0+0")
            pump(app)
            import playback_calibration_ui as calibration_ui
            calibration_ui._show_panel(app, True)
            pump(app)
            full_ui._responsive_root(app)
            pump(app)
            assert app._calibration_panel.winfo_width() <= 688, app._calibration_panel.winfo_width()
            capture(app, reports / "video-audit-calibration-720x640.png")
            calibration_ui._show_panel(app, False)
            pump(app)

            # Audio -> Band sidebar selection must not inherit the previous
            # YouTube footer instruction or expose downloader implementation in
            # the normal idle state.
            app.geometry("1280x720+0+0")
            pump(app)
            audio = app._studio_band_audio
            notebook.select(audio.tab)
            app.event_generate("<<NotebookTabChanged>>")
            pump(app)
            assert "YouTube" not in str(app.status_var.get()), app.status_var.get()
            assert "Audio" in str(app.status_var.get()), app.status_var.get()
            assert "spotDL" not in str(audio.resolver_status.get())
            assert "yt-dlp" not in str(audio.resolver_status.get())

            audio.open_workspace()
            audio.workspace.geometry("1180x760+0+0")
            pump(app)
            assert audio.workspace.title() == "Audio → Band"
            assert int(float(audio.bar.cget("value"))) == 0
            assert str(audio.bar.cget("mode")) == "determinate"
            assert not audio.source_hscrollbar.winfo_ismapped(), "source horizontal scrollbar visible on wide workspace"
            assert not audio.summary_hscrollbar.winfo_ismapped(), "summary horizontal scrollbar visible on wide workspace"
            capture(audio.workspace, reports / "video-audit-audio-band-1180x760.png")

            audio.workspace.geometry("640x480+0+0")
            pump(app)
            assert audio.source_hscrollbar.winfo_manager() == "grid"
            assert audio.summary_hscrollbar.winfo_manager() == "grid"
            capture(audio.workspace, reports / "video-audit-audio-band-640x480.png")

            checks["callbacks"] = errors
            assert not errors, errors
        finally:
            app.destroy()

    (reports / "video-audit-checks.json").write_text(
        json.dumps(checks, indent=2, sort_keys=True), encoding="utf-8"
    )
    print("Recording-driven Studio UI audit passed.")


if __name__ == "__main__":
    main()
