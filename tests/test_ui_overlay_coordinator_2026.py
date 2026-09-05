from pathlib import Path


SOURCE = Path("ui_overlay_coordinator_2026.py").read_text(encoding="utf-8")
LAUNCHER = Path("studio_launcher.py").read_text(encoding="utf-8")


def test_secondary_overlays_replace_band_room_instead_of_stacking() -> None:
    assert "_close_band_if_needed(app)" in SOURCE
    assert 'if key != "band"' in SOURCE
    assert "if visible:" in SOURCE
    assert "if user_opened:" in SOURCE


def test_overlay_coordinator_installs_after_band_overlay_patch() -> None:
    assert "from ui_overlay_coordinator_2026 import install_overlay_coordinator" in LAUNCHER
    assert LAUNCHER.index("install_band_responsive_patch()") < LAUNCHER.index("install_overlay_coordinator()")
