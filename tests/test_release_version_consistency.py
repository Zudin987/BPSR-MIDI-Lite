from __future__ import annotations

from pathlib import Path


def test_lite_release_version_is_consistent() -> None:
    launcher = Path("modern_launcher.py").read_text(encoding="utf-8")
    version_info = Path("version_info.txt").read_text(encoding="utf-8")
    builder = Path("build_exe.bat").read_text(encoding="utf-8")

    assert 'app.APP_VERSION = "3.4.0"' in launcher
    assert "filevers=(3, 4, 0, 0)" in version_info
    assert "prodvers=(3, 4, 0, 0)" in version_info
    assert "FileVersion', u'3.4.0'" in version_info
    assert "ProductVersion', u'3.4.0'" in version_info
    assert "set VERSION=3.4.0" in builder


def test_studio_release_version_is_consistent() -> None:
    launcher = Path("studio_launcher.py").read_text(encoding="utf-8")
    version_info = Path("studio_version_info.txt").read_text(encoding="utf-8")

    assert 'app.APP_VERSION = "Studio 0.5.0-band-accurate-beta.6"' in launcher
    assert "filevers=(0, 5, 0, 6)" in version_info
    assert "prodvers=(0, 5, 0, 6)" in version_info
    assert "FileVersion', u'0.5.0-band-accurate-beta.6'" in version_info
    assert "ProductVersion', u'0.5.0-band-accurate-beta.6'" in version_info