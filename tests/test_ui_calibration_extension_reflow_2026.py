from pathlib import Path


SOURCE = Path("ui_calibration_extension_reflow_2026.py").read_text(encoding="utf-8")
LAUNCHER = Path("studio_launcher.py").read_text(encoding="utf-8")


def test_compact_calibration_extensions_stack_below_base_form() -> None:
    assert 'if row >= 4:' in SOURCE
    assert 'row = 8 + index' in SOURCE
    assert 'columnspan=4' in SOURCE
    assert 'sticky = "ew" if class_name in {"TLabel", "TSeparator"} else "w"' in SOURCE
    assert 'widget.configure(wraplength=max(220, width - 30), justify="left")' in SOURCE


def test_wide_calibration_keeps_original_desktop_grid() -> None:
    assert 'if width >= 700:' in SOURCE
    assert 'return' in SOURCE
    assert 'original(app)' in SOURCE


def test_extension_reflow_wraps_the_existing_coordinator_after_install() -> None:
    assert 'original = coordinator._reflow_calibration_panel' in SOURCE
    assert 'coordinator._reflow_calibration_panel = reflow' in SOURCE
    assert 'from ui_calibration_extension_reflow_2026 import install_calibration_extension_reflow' in LAUNCHER
    assert LAUNCHER.index('install_overlay_coordinator()') < LAUNCHER.index('install_calibration_extension_reflow()')
