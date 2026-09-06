from __future__ import annotations

from pathlib import Path

from studio_band.runtime import RUNTIMES, RUNTIME_VALIDATION, RuntimeManager


def test_hq_runtime_matches_audio_separator_047_numpy_requirement() -> None:
    requirements = RUNTIMES["hq"]
    assert "audio-separator[cpu]==0.47.0" in requirements
    assert "numpy==2.3.3" in requirements
    assert "numpy==1.26.4" not in requirements
    assert "metadata.version('numpy') == '2.3.3'" in RUNTIME_VALIDATION["hq"]


def test_optional_adtof_status_does_not_make_drums_look_broken(tmp_path) -> None:
    manager = RuntimeManager(tmp_path)
    drums = next(row for row in manager.statuses() if row["runtime"] == "drums")
    assert "built-in DSP" in drums["status"]
    assert "optional" in drums["status"]


def test_clear_advanced_setup_is_installed_by_studio_launcher() -> None:
    launcher = Path("studio_launcher.py").read_text(encoding="utf-8")
    setup = Path("studio_band_advanced_setup.py").read_text(encoding="utf-8")

    assert "from studio_band_advanced_setup import install_advanced_model_setup" in launcher
    assert launcher.index("install_band_audio(app)") < launcher.index("install_advanced_model_setup()")
    assert "Set up recommended for this PC" in setup
    assert "Drums are READY even without a runtime named" in setup
    assert "Processing device" in setup
    assert "HQ separation" in setup
    assert "BPSR playability limits" in setup
