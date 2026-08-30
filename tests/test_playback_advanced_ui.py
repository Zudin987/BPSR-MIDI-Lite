from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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
