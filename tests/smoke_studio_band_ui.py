"""Exercise the actual patched Studio/Tk window on the Windows build runner."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    with tempfile.TemporaryDirectory() as folder:
        os.environ["BPSR_STUDIO_BAND_HOME"] = str(Path(folder) / "band")
        import studio_launcher
        from studio_band.arrange import ArrangementSettings, arrange, load_drum_profile
        from studio_band.export import export_arrangement
        from studio_band.music import BeatMap, MasterSong, MusicEvent
        app = studio_launcher.app.App()
        errors = []
        app.report_callback_exception = lambda *error: errors.append(str(error))

        def pump(seconds=.3):
            end = time.monotonic()+seconds
            while time.monotonic() < end:
                app.update()
                time.sleep(.01)

        try:
            audio = app._studio_band_audio
            app.song_source_notebook.select(audio.tab)
            audio.open_workspace()
            pump()
            assert app.song_source_var.get() == "audio_band"
            assert app._gaming_library_panel.winfo_width() == 400
            assert audio.workspace.winfo_viewable()
            assert audio.manual_button.winfo_viewable() and audio.source_tree.winfo_viewable()
            assert str(audio.acquire_button.cget("state")) == "disabled"
            assert audio.save_button.winfo_rootx()+audio.save_button.winfo_width() <= audio.workspace.winfo_rootx()+audio.workspace.winfo_width()
            # Each new job owns a fresh Event. The actual Cancel button must
            # cancel that job rather than the Event captured during UI creation.
            old_cancel = audio.cancel
            audio.start(lambda: (audio.cancel.wait(3), None)[1])
            audio.cancel_button.invoke()
            assert audio.cancel.is_set() and not old_cancel.is_set()
            pump()
            assert not audio.busy

            master = MasterSong("a"*64, 3, BeatMap(120, [0, .5, 1, 1.5, 2, 2.5], [], "fixture", .9),
                                [MusicEvent("vocals", "MAIN_MELODY", .5, 1, 72, 90, .9, "fixture", event_id="melody")])
            settings = ArrangementSettings()
            result = arrange(master, settings, load_drum_profile())
            manifest = export_arrangement(Path(folder)/"output", "UI synthetic", master, result, settings, Path(folder))
            audio.show_result(manifest)
            pump()
            assert len(audio.summary.get_children()) == 4
            assert str(audio.save_button.cget("state")) == "normal"
            assert str(audio.use_button.cget("state")) == "normal"
            audio.melody.set("Guitar")
            audio.rearrange()
            pump(1)
            assert not audio.busy and audio.record["melody_assignment"]["part"] == "guitar"
            assert not errors, errors
            reports = Path("ui-smoke-report")
            reports.mkdir(exist_ok=True)
            (reports/"ui-checks.json").write_text(json.dumps({"tab": "audio_band", "library_width": 400,
                "manual_audio_visible": True, "music_resolver_visible": True,
                "cancel_current_job": True, "rearrange_without_models": True, "callbacks": errors}), encoding="utf-8")
            try:
                from PIL import ImageGrab
                x, y = audio.workspace.winfo_rootx(), audio.workspace.winfo_rooty()
                ImageGrab.grab((x, y, x+audio.workspace.winfo_width(), y+audio.workspace.winfo_height())).save(reports/"audio-band-workspace.png")
            except OSError as exc:
                print("Desktop capture unavailable:", exc)
            print("Studio tab, preserved Library width, current-job cancellation, four-part summary and cached re-arrangement verified.")
        finally:
            app.destroy()


if __name__ == "__main__":
    main()
