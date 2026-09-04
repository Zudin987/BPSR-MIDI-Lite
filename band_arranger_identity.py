from __future__ import annotations

from typing import Any, Callable

import band_arranger
import band_ui


_original_current_app_version: Callable[[Any], str] | None = None


def band_room_version(app: Any) -> str:
    """Return a room compatibility identity without changing release metadata."""
    if _original_current_app_version is None:
        base = str(getattr(getattr(app, "_modern_module", None), "APP_VERSION", "unknown"))
    else:
        base = str(_original_current_app_version(app))
    suffix = f"+band-arr{int(band_arranger.BAND_ARRANGEMENT_VERSION)}"
    return base if base.endswith(suffix) else base + suffix


def install_band_arranger_identity(app_module: Any) -> None:
    global _original_current_app_version
    if getattr(app_module, "_band_arranger_identity_installed", False):
        return
    if not getattr(app_module, "_shared_band_arrangement_installed", False):
        raise RuntimeError("Shared Band arrangement must be installed before arranger identity.")

    _original_current_app_version = band_ui._current_app_version
    band_ui._current_app_version = band_room_version
    app_module._band_arranger_identity_installed = True
