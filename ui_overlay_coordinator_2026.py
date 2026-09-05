from __future__ import annotations

from typing import Any, Callable

import ui_full_overhaul_2026 as full_ui


def _band_visible(app: Any) -> bool:
    return bool(full_ui._overlay_state(app, "band").get("visible"))


def _close_band_if_needed(app: Any) -> None:
    if _band_visible(app):
        full_ui._hide_feature_overlay(app, "band")


def install_overlay_coordinator() -> None:
    """Make Studio's secondary surfaces mutually exclusive on compact screens."""
    if getattr(full_ui, "_overlay_coordinator_2026_installed", False):
        return

    original_settings = full_ui._set_settings_visible
    original_feature = full_ui._show_feature_overlay
    original_library = full_ui._show_library

    def set_settings_visible(app: Any, visible: bool) -> None:
        if visible:
            _close_band_if_needed(app)
        original_settings(app, visible)

    def show_feature_overlay(
        app: Any,
        key: str,
        panel: Any,
        preferred_width: int,
        close_command: Callable[[], None],
    ) -> None:
        if key != "band":
            _close_band_if_needed(app)
        original_feature(app, key, panel, preferred_width, close_command)

    def show_library(app: Any, *, user_opened: bool = False) -> None:
        # Automatic wide-layout docking is allowed beside Band Room. A user
        # explicitly opening Songs on a compact screen replaces the Band panel
        # rather than painting another overlay on top of it.
        if user_opened:
            _close_band_if_needed(app)
        original_library(app, user_opened=user_opened)

    full_ui._set_settings_visible = set_settings_visible
    full_ui._show_feature_overlay = show_feature_overlay
    full_ui._show_library = show_library
    full_ui._overlay_coordinator_2026_installed = True
