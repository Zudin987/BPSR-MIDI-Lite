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

    def _instrument_code(self) -> str:
        return "keyboard"


def test_guided_feedback_narrows_threshold_and_proposes_next_value(monkeypatch) -> None:
    app = _App()
    monkeypatch.setattr(guidance, "_original_record_feedback", lambda _app, _feedback: None)

    guidance._guided_record_feedback(app, "missed")
    assert app._calibration_value_var.get() == 140
    assert "61–220 ms" in app._calibration_guide_var.get()

    guidance._guided_record_feedback(app, "clean")
    assert app._calibration_value_var.get() == 100
    assert "61–140 ms" in app._calibration_guide_var.get()


def test_guided_muddy_feedback_searches_downward(monkeypatch) -> None:
    app = _App()
    app._calibration_value_var.set(120)
    monkeypatch.setattr(guidance, "_original_record_feedback", lambda _app, _feedback: None)

    guidance._guided_record_feedback(app, "muddy")
    assert app._calibration_value_var.get() < 120
    assert "20–119 ms" in app._calibration_guide_var.get()


def test_launchers_install_guidance_after_calibration_lab() -> None:
    for filename in ("modern_launcher.py", "studio_launcher.py"):
        source = Path(filename).read_text(encoding="utf-8")
        assert "from playback_calibration_guidance import install_guided_calibration" in source
        assert source.index("install_calibration_lab(app)") < source.index("install_guided_calibration(app)")
