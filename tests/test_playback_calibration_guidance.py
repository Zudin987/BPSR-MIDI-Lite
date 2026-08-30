from __future__ import annotations

from pathlib import Path

import playback_calibration_guidance as guidance


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _App:
    def __init__(self) -> None:
        self._calibration_test_var = _Var("Minimum clean hold")
        self._calibration_value_var = _Var(60)
        self._calibration_guide_var = _Var("")
        self.status_var = _Var("")
        self._calibration_completed_sample = None

    def _instrument_code(self) -> str:
        return "keyboard"

    def mark_current_sample_complete(self) -> None:
        self._calibration_completed_sample = (
            "keyboard",
            "hold",
            int(self._calibration_value_var.get()),
        )


def test_guided_feedback_narrows_threshold_and_proposes_next_value(monkeypatch) -> None:
    app = _App()
    monkeypatch.setattr(guidance, "_original_record_feedback", lambda _app, _feedback: None)

    app.mark_current_sample_complete()
    guidance._guided_record_feedback(app, "missed")
    assert app._calibration_value_var.get() == 140
    assert "61–220 ms" in app._calibration_guide_var.get()

    app.mark_current_sample_complete()
    guidance._guided_record_feedback(app, "clean")
    assert app._calibration_value_var.get() == 100
    assert "61–140 ms" in app._calibration_guide_var.get()


def test_guided_muddy_feedback_searches_downward(monkeypatch) -> None:
    app = _App()
    app._calibration_value_var.set(120)
    app.mark_current_sample_complete()
    monkeypatch.setattr(guidance, "_original_record_feedback", lambda _app, _feedback: None)

    guidance._guided_record_feedback(app, "muddy")
    assert app._calibration_value_var.get() < 120
    assert "20–119 ms" in app._calibration_guide_var.get()


def test_guided_feedback_without_completed_sample_does_not_change_bounds(monkeypatch) -> None:
    app = _App()
    called = False

    def original(_app, _feedback):
        nonlocal called
        called = True

    monkeypatch.setattr(guidance, "_original_record_feedback", original)
    guidance._guided_record_feedback(app, "clean")

    assert called is False
    assert getattr(app, "_calibration_guide_bounds", {}) == {}
    assert app._calibration_value_var.get() == 60
    assert "Play and finish this exact calibration value" in app.status_var.get()


def test_changing_value_invalidates_completed_sample(monkeypatch) -> None:
    app = _App()
    app.mark_current_sample_complete()
    app._calibration_value_var.set(61)
    monkeypatch.setattr(guidance, "_original_record_feedback", lambda _app, _feedback: None)

    guidance._guided_record_feedback(app, "clean")

    assert getattr(app, "_calibration_guide_bounds", {}) == {}
    assert "Play and finish this exact calibration value" in app.status_var.get()


def test_calibration_player_completion_does_not_touch_tk_from_worker_callback() -> None:
    source = Path("playback_calibration_ui.py").read_text(encoding="utf-8")
    start = source.index("    def finished(error: str | None) -> None:")
    end = source.index("    app.player.start(", start)
    callback = source[start:end]
    assert "_calibration_ui_messages.put" in callback
    assert "app.after(" not in callback
    assert "configure(" not in callback
    assert "status_var.set" not in callback


def test_launchers_install_guidance_after_calibration_lab() -> None:
    for filename in ("modern_launcher.py", "studio_launcher.py"):
        source = Path(filename).read_text(encoding="utf-8")
        assert "from playback_calibration_guidance import install_guided_calibration" in source
        assert source.index("install_calibration_lab(app)") < source.index("install_guided_calibration(app)")
