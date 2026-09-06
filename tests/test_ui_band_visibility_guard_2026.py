from pathlib import Path


SOURCE = Path("ui_band_visibility_guard_2026.py").read_text(encoding="utf-8")
LAUNCHER = Path("studio_launcher.py").read_text(encoding="utf-8")


def test_disabled_band_room_is_physically_unmapped_before_overlay_registration() -> None:
    assert "def _force_unmap_band_frame(app" in SOURCE
    assert 'for method_name in ("grid_remove", "pack_forget", "place_forget")' in SOURCE
    assert "if not visible:" in SOURCE
    assert "_force_unmap_band_frame(app)" in SOURCE
    assert "original(app, visible)" in SOURCE


def test_visibility_guard_installs_after_band_responsive_patch() -> None:
    assert "from ui_band_visibility_guard_2026 import install_band_visibility_guard" in LAUNCHER
    assert LAUNCHER.index("install_band_responsive_patch()") < LAUNCHER.index("install_band_visibility_guard()")
