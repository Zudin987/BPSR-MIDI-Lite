"""Exercise the actual patched Studio/Tk UI on the Windows build runner."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _find_text(root, text):
    for child in root.winfo_children():
        try:
            if str(child.cget("text")) == text:
                return child
        except Exception:
            pass
        found = _find_text(child, text)
        if found is not None:
            return found
    return None


def main():
    with tempfile.TemporaryDirectory() as folder:
        os.environ["BPSR_STUDIO_BAND_HOME"] = str(Path(folder) / "band")
        import studio_launcher
        import ui_full_overhaul_2026 as full_ui
        import playback_calibration_ui
        from studio_band.arrange import ArrangementSettings, arrange, load_drum_profile
        from studio_band.export import export_arrangement
        from studio_band.music import BeatMap, MasterSong, MusicEvent
        from studio_band.progress import ProgressEvent
        from studio_band.protocol import RuntimeSetupError, StageError, run_process
        app = studio_launcher.app.App()
        errors = []
        app.report_callback_exception = lambda *error: errors.append(str(error))

        def pump(seconds=.3):
            end = time.monotonic()+seconds
            while time.monotonic() < end:
                app.update()
                time.sleep(.01)

        try:
            pump()
            # Main product UI: normal desktop keeps a compact Library, but the
            # 990 px permanent minimum is gone and small/high-DPI layouts can
            # collapse it without losing access to Songs.
            library_width = app._gaming_library_panel.winfo_width()
            assert 250 <= library_width <= 370, library_width
            assert app.minsize()[0] <= 720, app.minsize()
            assert getattr(app, "_ux_songs_button", None) is not None, "Responsive Songs toggle missing"

            app.geometry("760x540+0+0")
            pump()
            assert not app._gaming_library_visible, "Library did not auto-collapse for compact window"
            app._ux_songs_button.invoke()
            pump()
            assert app._gaming_library_visible and app._gaming_library_panel.winfo_manager() == "place", "Songs did not reopen as compact overlay"
            app._ux_songs_button.invoke()
            pump()

            # Settings is a scrollable overlay rather than a tall fixed right
            # column. At a short window the last setting remains reachable.
            app.geometry("900x520+0+0")
            pump()
            full_ui._set_settings_visible(app, True)
            pump()
            assert app._gaming_settings_panel.winfo_manager() == "place", "Settings is not an overlay"
            full_ui._settings_scroll_command(app, "moveto", "1.0")
            pump()
            assert int(getattr(app, "_ux_settings_offset", 0)) >= 0
            full_ui._set_settings_visible(app, False)

            # Rare Calibration content also uses the same-window clipped/scrollable
            # overlay rather than pushing the entire main player downward.
            playback_calibration_ui._show_panel(app, True)
            pump()
            assert app._calibration_panel.winfo_manager() == "place", "Calibration did not become an overlay"
            assert full_ui._overlay_state(app, "calibration")["visible"] is True
            playback_calibration_ui._show_panel(app, False)
            pump()

            app.geometry("1180x650+0+0")
            pump()
            audio = app._studio_band_audio
            app.song_source_notebook.select(audio.tab)
            audio.open_workspace()
            pump()
            assert app.song_source_var.get() == "audio_band", "Audio -> Band tab did not become active"
            assert audio.workspace.winfo_viewable(), "Audio -> Band workspace is not visible"
            initial_geometry = audio.workspace.geometry()
            assert audio.workspace.winfo_rooty() + audio.workspace.winfo_height() <= audio.workspace.winfo_screenheight(), "Workspace extends below desktop"
            assert audio.manual_button.winfo_viewable() and audio.source_tree.winfo_viewable(), "Primary audio controls are not mapped"
            assert audio.workspace_scrollbar.winfo_viewable() and audio.source_scrollbar.winfo_viewable(), "Required vertical scrolling is unavailable"
            # Horizontal scrollbars can be below the current canvas viewport and
            # therefore do not need winfo_viewable() to be true at scroll top.
            assert hasattr(audio, "source_hscrollbar") and hasattr(audio, "summary_hscrollbar"), "Wide tables have no horizontal scroll fallback"
            assert str(audio.acquire_button.cget("state")) == "disabled", "Acquire should start disabled"
            assert audio.save_button.winfo_rootx()+audio.save_button.winfo_width() <= audio.workspace.winfo_rootx()+audio.workspace.winfo_width(), "Footer overflows horizontally"
            assert "availability" not in tuple(str(x) for x in audio.source_tree.cget("displaycolumns")), "Redundant action/status column still displayed"
            if hasattr(audio, "_ux_hidden_source_combo"):
                assert not audio._ux_hidden_source_combo.winfo_ismapped(), "One-choice source combobox is still visible"
            assert _find_text(audio.workspace, "Models & quality…") is not None, "Advanced model controls were not renamed for users"
            assert _find_text(audio.workspace, "Details…") is not None, "Technical details were not demoted"
            assert audio.progress_panel.winfo_viewable(), "Persistent progress panel is not visible"

            # A 640x480 Audio -> Band window keeps the manual input at the top
            # and footer controls reachable through vertical scrolling. Toolbars
            # reflow instead of clipping their right-most controls.
            audio.workspace.geometry("640x480+0+0")
            audio.workspace_canvas.yview_moveto(0)
            pump()
            assert audio.manual_button.winfo_rooty() >= audio.workspace.winfo_rooty(), "Manual picker moved above the small viewport"
            assert int(audio.search_button.grid_info()["row"]) >= 1, "Search controls did not wrap at 640 px"
            assert int(audio.rearrange_button.grid_info()["row"]) >= 1, "Conversion actions did not wrap at 640 px"
            window_right = audio.workspace.winfo_rootx() + audio.workspace.winfo_width()
            for button in audio.convert_button.master.winfo_children():
                assert button.winfo_rootx() + button.winfo_width() <= window_right, f"Action control clips horizontally: {button}"
            window_bottom = audio.workspace.winfo_rooty() + audio.workspace.winfo_height()
            footer_bottom = audio.save_button.winfo_rooty() + audio.save_button.winfo_height()
            if footer_bottom > window_bottom:
                assert audio.workspace_canvas.yview()[1] < 1.0, "Footer clips but workspace is not scrollable"
            audio.workspace_canvas.yview_moveto(1.0)
            pump()
            assert audio.save_button.winfo_rooty() + audio.save_button.winfo_height() <= (
                audio.workspace.winfo_rooty() + audio.workspace.winfo_height() + 2), "Footer cannot be reached at scroll bottom"
            assert audio.progress_panel.winfo_viewable(), "Progress disappeared after scrolling"
            assert audio.progress_panel.winfo_rooty() + audio.progress_panel.winfo_height() <= window_bottom + 2, "Progress panel clips below compact window"
            audio.workspace.geometry(initial_geometry)
            audio.workspace_canvas.yview_moveto(0)
            pump()

            # A model that cannot expose incremental inference callbacks keeps
            # its real operation/device visible and separates stage time from
            # total job time instead of looking frozen at a bare percentage.
            audio._accept_progress(ProgressEvent(
                "Cross-checking musical evidence on CUDA…",
                stage_id="cross_check", phase="Analyzing song", activity="gpu",
                overall=90.8, stage_fraction=.2,
            ))
            now = time.monotonic()
            audio.job_started_at = now - (17 * 60 + 32)
            audio.stage_started_at = now - (8 * 60)
            audio._accept_progress(ProgressEvent(
                "Cross-checking musical evidence on CUDA — no new progress report for 08:00; "
                "the worker process is still running…",
                stage_id="cross_check", phase="Analyzing song", activity="waiting",
                overall=90.8, stage_fraction=.2, last_reported_activity="gpu",
            ))
            assert "on CUDA" in audio.status.get(), "Silent inference lost the last real device"
            assert "stage 08:00" in audio.status.get() and "total 17:32" in audio.status.get()
            assert "Worker process alive" in audio.progress_context_var.get()

            # The real ncls/MSVC class of setup failure must end the job and
            # keep the concise reason in the normal UI while preserving the
            # installer output under Details.
            def failed_setup():
                try:
                    run_process(
                        [sys.executable, "-c", (
                            "import sys; sys.stderr.write('error: Microsoft Visual C++ 14.0 or greater is required.\\n'"
                            "); sys.stderr.write('ncls==0.0.70\\n'); raise SystemExit(1)"
                        )],
                        stage="Runtime setup", timeout=10,
                    )
                except StageError as exc:
                    raise RuntimeSetupError(
                        "piano",
                        "Could not prepare Transkun runtime. Windows dependency installation failed.",
                        exc.details,
                    ) from exc

            audio.start(failed_setup, task="conversion")
            pump(1)
            assert not audio.busy, "Failed setup left Audio -> Band busy"
            assert str(audio.cancel_button.cget("state")) == "disabled", "Cancel stayed active after failure"
            assert str(audio.convert_button.cget("state")) == "normal", "Convert control did not restore"
            assert str(audio.convert_button.cget("text")) == "Retry conversion", "Retry action was not exposed"
            assert str(audio.bar.cget("mode")) == "determinate", "Failed progress bar kept animating"
            assert str(audio.status.get()) == (
                "Conversion/setup failed · Could not prepare Transkun runtime. Windows dependency installation failed."
            )
            assert "Microsoft Visual C++" in audio.details and "ncls==0.0.70" in audio.details

            # Each new job owns a fresh Event. The actual Cancel button must
            # cancel that job rather than the Event captured during UI creation.
            old_cancel = audio.cancel
            audio.start(lambda: (audio.cancel.wait(3), None)[1])
            audio.cancel_button.invoke()
            assert audio.cancel.is_set() and not old_cancel.is_set(), "Cancel button did not target current job"
            pump()
            assert not audio.busy, "Cancelled job stayed busy"

            master = MasterSong("a"*64, 3, BeatMap(120, [0, .5, 1, 1.5, 2, 2.5], [], "fixture", .9),
                                [MusicEvent("vocals", "MAIN_MELODY", .5, 1, 72, 90, .9, "fixture", event_id="melody")])
            settings = ArrangementSettings()
            result = arrange(master, settings, load_drum_profile())
            manifest = export_arrangement(Path(folder)/"output", "UI synthetic", master, result, settings, Path(folder))
            audio.show_result(manifest)
            pump()
            assert len(audio.summary.get_children()) == 4, "Four-part summary did not render"
            assert str(audio.save_button.cget("state")) == "normal", "Export did not enable"
            assert str(audio.use_button.cget("state")) == "normal", "Use Full Band did not enable"
            audio.melody.set("Guitar")
            audio.rearrange()
            pump(1)
            assert not audio.busy and audio.record["melody_assignment"]["part"] == "guitar", "Cached rearrangement failed"
            assert not errors, errors
            reports = Path("ui-smoke-report")
            reports.mkdir(exist_ok=True)
            (reports/"ui-checks.json").write_text(json.dumps({
                "tab": "audio_band",
                "library_width": library_width,
                "responsive_library": True,
                "settings_scroll_overlay": True,
                "calibration_overlay": True,
                "manual_audio_visible": True,
                "music_resolver_visible": True,
                "resolver_action_column_removed": True,
                "one_choice_source_hidden": True,
                "fits_desktop": True,
                "small_window_footer_access": True,
                "small_window_toolbar_reflow": True,
                "horizontal_table_scroll": True,
                "persistent_progress": True,
                "silent_inference_heartbeat": True,
                "failed_setup_restores_controls": True,
                "resolver_scrollbar": True,
                "cancel_current_job": True,
                "rearrange_without_models": True,
                "callbacks": errors,
            }), encoding="utf-8")
            try:
                from PIL import ImageGrab
                x, y = audio.workspace.winfo_rootx(), audio.workspace.winfo_rooty()
                ImageGrab.grab((x, y, x+audio.workspace.winfo_width(), y+audio.workspace.winfo_height())).save(reports/"audio-band-workspace.png")
                app.deiconify(); app.lift(); pump(.2)
                x, y = app.winfo_rootx(), app.winfo_rooty()
                ImageGrab.grab((x, y, x+app.winfo_width(), y+app.winfo_height())).save(reports/"main-responsive-ui.png")
            except OSError as exc:
                print("Desktop capture unavailable:", exc)
            print("Studio main UI, responsive overlays, 640x480 Audio -> Band, cancellation and cached re-arrangement verified.")
        finally:
            app.destroy()


if __name__ == "__main__":
    main()
