"""Recording-driven smoke for the beta.8 UI cleanup.

This specifically guards defects visible in the user's 77.8-second desktop
recording: clipped Library tabs/columns, leaking focused surfaces, detached
Close/scroll chrome, compact Custom-tuning clipping, stale Audio-tab copy,
obsolete duplicate YouTube UI and misleading Audio scroll/progress state.
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


def walk(root):
    for child in root.winfo_children():
        yield child
        yield from walk(child)


def main() -> None:
    reports = Path("ui-smoke-report")
    reports.mkdir(exist_ok=True)
    checks: dict[str, object] = {}

    with tempfile.TemporaryDirectory() as folder:
        os.environ["BPSR_STUDIO_BAND_HOME"] = str(Path(folder) / "band")
        import band_ui
        import playback_advanced_ui as advanced_ui
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

            nested_library_titles = []
            for widget in walk(app._gaming_library_panel):
                try:
                    if widget.winfo_class() in {"TLabelframe", "Labelframe"}:
                        nested_library_titles.append(str(widget.cget("text")))
                except Exception:
                    pass
            assert "Songs" not in nested_library_titles, nested_library_titles

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

            # Band Mode now behaves like Audio -> Band: checking the mode opens
            # a dedicated resizable workspace instead of replacing/covering the
            # main player. Closing the window hides only the workspace; Band Mode
            # remains enabled and the Band room button can reopen it.
            assert not app._band_window.winfo_viewable()
            app._band_enabled_var.set(True)
            band_ui._toggle_band_mode(app)
            pump(app)
            assert app._band_window.winfo_viewable()
            assert app._band_window.title() == "Band Room"
            assert app._band_frame.master is app._band_window_body
            assert app._band_frame.winfo_manager() == "grid"
            assert app.winfo_viewable(), "Main player disappeared when Band Room opened"
            capture(app._band_window, reports / "video-audit-band-room-1280x720.png")
            app._band_window.event_generate("<Escape>")
            pump(app)
            assert not app._band_window.winfo_viewable()
            assert bool(app._band_enabled_var.get())
            app._ux_band_room_button.invoke()
            pump(app)
            assert app._band_window.winfo_viewable(), "Band room reopen button did not restore workspace"
            app._band_window.withdraw()
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

            # The supplied recording showed a concrete compact Custom regression:
            # Retrigger gap and the long helper sentence extended past the right
            # edge. Verify every mapped direct child is physically contained.
            app.geometry("560x700+0+0")
            pump(app)
            advanced_ui._show_custom_panel(app, True)
            pump(app)
            full_ui._responsive_root(app)
            pump(app)
            custom = app.custom_settings_frame
            custom_left = custom.winfo_rootx()
            custom_right = custom_left + custom.winfo_width()
            for widget in custom.winfo_children():
                if not widget.winfo_ismapped():
                    continue
                left = widget.winfo_rootx()
                right = left + widget.winfo_width()
                assert left >= custom_left - 2, (str(widget), left, custom_left)
                assert right <= custom_right + 2, (str(widget), right, custom_right)
            assert getattr(custom, "_ux_round3_narrow", None) is True
            capture(app, reports / "video-audit-custom-560x700.png")
            advanced_ui._show_custom_panel(app, False)
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
            # Keep the visual capture above the Windows taskbar. The normal
            # open_workspace code already uses screen-height headroom; this test
            # should not intentionally force a 760px client onto a ~768px runner.
            safe_height = min(680, max(480, int(audio.workspace.winfo_screenheight()) - 90))
            audio.workspace.geometry(f"1180x{safe_height}+0+0")
            pump(app)
            assert audio.workspace.title() == "Audio → Band"
            assert int(float(audio.bar.cget("value"))) == 0
            assert str(audio.bar.cget("mode")) == "determinate"
            assert not audio.source_hscrollbar.winfo_ismapped(), "source horizontal scrollbar visible on wide workspace"
            assert not audio.summary_hscrollbar.winfo_ismapped(), "summary horizontal scrollbar visible on wide workspace"
            audio_text = []
            for widget in walk(audio.workspace):
                try:
                    value = str(widget.cget("text"))
                except Exception:
                    continue
                if value:
                    audio_text.append(value)
            assert "Melody" in audio_text and "Separation" in audio_text, audio_text
            assert "Main Melody" not in audio_text and "Stem Quality" not in audio_text, audio_text
            capture(audio.workspace, reports / "video-audit-audio-band-wide.png")

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
