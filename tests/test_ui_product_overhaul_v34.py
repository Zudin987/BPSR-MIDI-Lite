from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ui_product_overhaul_v34 import product_metric_texts, product_summary_text


def test_product_summary_separates_intentional_bass_arrangement_from_physical_loss() -> None:
    plan = SimpleNamespace(
        note_count=163,
        remapped_notes=14,
        arranged_out_notes=432,
        skipped_notes=0,
        chord_removed_notes=0,
        retrigger_dropped_notes=0,
        max_simultaneous_keys=1,
        page_switches=0,
        arrangement_strategy="auto_bass_line",
        bass_line_notes=163,
        transposed_semitones=-1,
        folded_notes=0,
    )
    text = product_summary_text(plan)
    assert "Auto Bass Line" in text
    assert "163 bass-role notes" in text
    assert "Transposed -1 st" in text
    assert "0 physical removals" in text
    assert "No page keys" in text


def test_product_summary_keeps_normal_arrangement_compact() -> None:
    plan = SimpleNamespace(
        note_count=593,
        remapped_notes=41,
        arranged_out_notes=0,
        skipped_notes=0,
        chord_removed_notes=2,
        retrigger_dropped_notes=1,
        max_simultaneous_keys=4,
        page_switches=0,
        arrangement_strategy="adaptive",
    )
    text = product_summary_text(plan)
    assert text == "593 playable • 41 pitch-fitted • 3 simplified/removed • Peak 4 key(s) • No page keys"


def test_song_check_cards_keep_long_diagnostics_out_of_primary_row() -> None:
    plan = SimpleNamespace(
        note_count=187,
        source_note_count=187,
        remapped_notes=30,
        transposed_semitones=-3,
        folded_notes=30,
        skipped_notes=0,
        chord_removed_notes=0,
        retrigger_dropped_notes=0,
        page_switches=0,
    )
    assert product_metric_texts(plan) == {
        "playable": "187",
        "pitch": "-3 st + 30 fits",
        "removed": "0",
        "safety": "No page keys",
    }


def test_song_check_cards_surface_loss_without_sentence_clipping() -> None:
    plan = SimpleNamespace(
        note_count=117,
        source_note_count=187,
        remapped_notes=15,
        transposed_semitones=-22,
        folded_notes=15,
        skipped_notes=10,
        chord_removed_notes=60,
        retrigger_dropped_notes=0,
        page_switches=0,
    )
    metrics = product_metric_texts(plan)
    assert metrics["playable"] == "117 / 187"
    assert metrics["pitch"] == "-22 st + 15 fits"
    assert metrics["removed"] == "70"
    assert metrics["safety"] == "No page keys"


def test_persistent_library_keeps_sidebar_open_without_squeezing_center() -> None:
    source = Path("ui_persistent_library.py").read_text(encoding="utf-8")

    assert "_LIBRARY_WIDTH = 400" in source
    assert "_CENTER_MIN_WIDTH = 520" in source
    assert "_MIN_WINDOW_WIDTH = 990" in source
    assert "panel.grid_propagate(False)" in source
    assert "_remove_library_toggle" in source
    assert "gaming_runtime._set_library_visible = _set_library_visible_persistent" in source
    assert "gaming_ui._responsive_layout = _persistent_responsive_layout" in source
