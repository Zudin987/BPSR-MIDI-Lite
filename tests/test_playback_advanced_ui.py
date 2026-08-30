from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from playback_advanced_ui import (
    CUSTOM_PROFILE_LABEL,
    _append_timing_preview,
    _custom_profile_summary,
)


class _Var:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


def test_custom_profile_copy_matches_safe_no_page_product_policy() -> None:
    app = SimpleNamespace(
        _instrument_code=lambda: "keyboard",
        articulation_var=_Var("Balanced"),
    )
    summary, notice = _custom_profile_summary(app)
    assert CUSTOM_PROFILE_LABEL == "Custom — Advanced timing & mapping"
    assert "Stable / no-page playback" in summary
    assert "never presses < or >" in notice
    assert "experimental full range" not in (summary + notice).lower()


def test_custom_profile_is_integrated_into_the_gaming_ui_instead_of_only_exposed_in_the_combo() -> None:
    source = Path("playback_advanced_ui.py").read_text(encoding="utf-8")
    assert "original_build_ui = app_class._build_ui" in source
    assert "_prepare_custom_panel(self, app_module)" in source
    assert "app.custom_settings_frame = panel" in source
    assert "app._build_custom_settings(panel)" in source
    assert 'if self._profile_code() != "custom"' in source
    assert "original_apply_profile_ui(self, schedule=schedule)" in source
    assert "_show_custom_panel(self, True)" in source


def test_song_check_exposes_v32_timing_adjustments_without_duplication() -> None:
    analysis = _Var("Ready • Keyboard\nOriginal range C3–C6")
    plan = SimpleNamespace(
        articulation_mode="balanced",
        timing_profile="keyboard",
        retrigger_compressed_notes=3,
        retrigger_merged_notes=1,
        retrigger_dropped_notes=0,
        sustain_mode="simulated",
        page_switches=0,
    )
    app = SimpleNamespace(current_plan=plan, analysis_var=analysis)
    _append_timing_preview(app)
    first = analysis.get()
    assert "BPSR timing • Keyboard / Balanced" in first
    assert "rapid repeats 4 adjusted (3 shortened, 1 merged, 0 dropped)" in first
    assert "sustain Simulated" in first
    _append_timing_preview(app)
    assert analysis.get() == first


def _run_ui_smoke(module_name: str) -> None:
    code = f'''
import {module_name} as launcher
from playback_advanced_ui import CUSTOM_PROFILE_LABEL
root = launcher.app.App()
try:
    root.withdraw()
    root.profile_var.set(CUSTOM_PROFILE_LABEL)
    root._profile_changed()
    root.update_idletasks()
    assert hasattr(root, "custom_settings_frame")
    assert hasattr(root, "release_gap_var")
    assert hasattr(root, "articulation_var")
    assert hasattr(root, "sustain_mode_var")
    assert root._profile_code() == "custom"
    assert "no-page" in root.profile_summary_var.get().lower()
    assert root.mode_combo.cget("state") == "disabled"
finally:
    root.destroy()
'''
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr


@pytest.mark.skipif(os.name != "nt", reason="Tk/Windows launcher smoke test")
def test_lite_launcher_can_open_and_select_custom_profile() -> None:
    _run_ui_smoke("modern_launcher")


@pytest.mark.skipif(
    os.name != "nt" or importlib.util.find_spec("basic_pitch") is None,
    reason="Studio dependencies are available only in the Studio build job",
)
def test_studio_launcher_can_open_and_select_custom_profile() -> None:
    _run_ui_smoke("studio_launcher")
