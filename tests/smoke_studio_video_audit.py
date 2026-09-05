"""Recording-driven smoke for the beta.8 UI cleanup.

This specifically guards defects visible in the user's 77.8-second desktop
recording: clipped Library tabs/columns, leaking focused surfaces, detached
Close/scroll chrome, stale Audio-tab copy and always-visible Audio table
horizontal scrollbars/progress state.
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


def mapped_siblings(panel) -> list[str]:
    result: list[str] = []
    for widget in panel.master.winfo_children():
        if widget is panel:
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
            assert labels == ["Local", "Online", "Saved", "YouTube", "Audio"], labels
            for index in range(len(labels)):
                x, _y, width, _height = notebook.bbox(index)
                assert x + width <= notebook.winfo_width() + 2, (index, labels[index], x, width, notebook.winfo_width())

            for tree in (app.online_tree, app.bookmark_tree):
                display = tuple(str(value) for value in tree.cget("displaycolumns"))
                assert "changes" not in display, display
                assert display in {("fit",), ("fit", "notes")}, display
            youtube_display = tuple(str(value) for value in app.youtube_tree.cget("displaycolumns"))
            assert youtube_display == ("duration",), youtube_display
            capture(app, reports / "video-audit-main-1280x720.png")

            # Settings is a focused surface now: it must not sit as a narrow
            # transparent-looking strip over the player.
            full_ui._set_settings_visible(app, True)
            pump(app)
            settings_state = full_ui._overlay_state(app, "settings")
            assert settings_state.get("visible")
            assert app._gaming_settings_panel.winfo_manager() == "place"
            assert not mapped_siblings(app._gaming_settings_panel), mapped_siblings(app._gaming_settings_panel)
            assert settings_state["close_button"].master is app._gaming_settings_panel.master
            if settings_state.get("scrollbar") is not None:
                assert settings_state["scrollbar"].master is app._gaming_settings_panel.master
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
            assert not mapped_siblings(app._band_frame), mapped_siblings(app._band_frame)
            assert band_state["close_button"].master is app._band_frame.master
            if band_state.get("scrollbar") is not None:
                assert band_state["scrollbar"].master is app._band_frame.master
            capture(app, reports / "video-audit-band-room-1280x720.png")
            full_ui._hide_feature_overlay(app, "band")
            pump(app)

            # Audio -> Band sidebar selection must not inherit the previous
            # YouTube footer instruction.
            audio = app._studio_band_audio
            notebook.select(audio.tab)
            app.event_generate("<<NotebookTabChanged>>")
            pump(app)
            assert "YouTube" not in str(app.status_var.get()), app.status_var.get()
            assert "Audio" in str(app.status_var.get()), app.status_var.get()

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
