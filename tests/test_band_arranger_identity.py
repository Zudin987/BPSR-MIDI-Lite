from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import band_arranger
import band_arranger_identity as identity


def test_band_room_version_appends_arranger_contract_without_changing_app_version() -> None:
    app = SimpleNamespace(_modern_module=SimpleNamespace(APP_VERSION="3.4.0"))
    identity._original_current_app_version = None
    band_arranger.BAND_ARRANGEMENT_VERSION = 4
    assert identity.band_room_version(app) == "3.4.0+band-arr4"
    assert app._modern_module.APP_VERSION == "3.4.0"


def test_launchers_install_arranger_identity_after_v4_and_before_network_layers() -> None:
    for filename in ("modern_launcher.py", "studio_launcher.py"):
        source = Path(filename).read_text(encoding="utf-8")
        assert "install_band_arranger_identity" in source
        assert source.index("install_shared_band_arrangement(app)") < source.index(
            "install_band_arranger_identity(app)"
        )
        assert source.index("install_band_arranger_identity(app)") < source.index(
            "install_band_network_hardening(app)"
        )
