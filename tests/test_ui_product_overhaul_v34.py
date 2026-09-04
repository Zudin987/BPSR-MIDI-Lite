from __future__ import annotations

from types import SimpleNamespace

from ui_product_overhaul_v34 import product_summary_text


def test_product_summary_separates_intentional_bass_arrangement_from_physical_loss() -> None:
    plan = SimpleNamespace(
        note_count=163,
        remapped_notes=14,
        arranged_out_notes=432,
        skipped_notes=0,
        chord_removed_notes=432,
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
