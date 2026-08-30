from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from playback_adaptive_ui import arrangement_impact_text


def test_arrangement_impact_text_explains_source_to_bpsr_changes() -> None:
    plan = SimpleNamespace(
        source_note_count=100,
        note_count=82,
        max_source_chord=7,
        max_planned_chord=4,
        source_min_pitch=36,
        source_max_pitch=96,
        planned_min_pitch=40,
        planned_max_pitch=86,
        remapped_notes=12,
        chord_removed_notes=14,
        skipped_notes=2,
        retrigger_dropped_notes=1,
        retrigger_compressed_notes=3,
        retrigger_merged_notes=2,
        normalized_chords=8,
        priority_evictions=2,
    )
    text = arrangement_impact_text(plan)
    assert "Source 100 notes / chord 7" in text
    assert "BPSR 82 notes / chord 4" in text
    assert "12 remapped" in text
    assert "17 removed/thinned" in text
    assert "6 rapid-repeat edits" in text
    assert "8 chord attacks normalized" in text
    assert "2 melody-priority steals" in text


def test_launchers_install_impact_ui_after_adaptive_pressure_model() -> None:
    for filename in ("modern_launcher.py", "studio_launcher.py"):
        source = Path(filename).read_text(encoding="utf-8")
        assert "from playback_adaptive_ui import install_adaptive_arranger_ui" in source
        assert source.index("install_adaptive_pressure_model(app)") < source.index("install_adaptive_arranger_ui(app)")
        assert source.index("install_adaptive_arranger_ui(app)") < source.index("install_calibration_lab(app)")
