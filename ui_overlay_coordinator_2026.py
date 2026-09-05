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
    original_root = full_ui._responsive_root

    def set_settings_visible(app: Any, visible: bool) -> None:
        # The product layout starts with Settings marked visible so the first
        # compact reflow can collapse it automatically. Once the user explicitly
        # opens Settings, however, later <Configure> reflows must not immediately
        # close it again. That made the Settings button effectively unusable on
        # small/high-DPI windows.
        if (
            not visible
            and bool(getattr(app, "_ux_settings_reflow_guard", False))
            and bool(getattr(app, "_ux_settings_user_open", False))
        ):
            return
        if visible:
            app._ux_settings_user_open = True
            _close_band_if_needed(app)
        else:
            app._ux_settings_user_open = False
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

    def responsive_root(app: Any, width: int | None = None) -> None:
        # ui_full_overhaul's base compact policy hides the initially-visible
        # Settings panel below 720 px. Guard only user-opened Settings while that
        # policy runs, then refresh its overlay geometry after all reflow work.
        preserve_settings = bool(
            getattr(app, "_gaming_settings_visible", False)
            and getattr(app, "_ux_settings_user_open", False)
        )
        if preserve_settings:
            app._ux_settings_reflow_guard = True
        try:
            original_root(app, width)
        finally:
            app._ux_settings_reflow_guard = False
        if preserve_settings and bool(getattr(app, "_gaming_settings_visible", False)):
            full_ui._refresh_settings_position(app)

    full_ui._set_settings_visible = set_settings_visible
    full_ui._show_feature_overlay = show_feature_overlay
    full_ui._show_library = show_library
    full_ui._responsive_root = responsive_root
    full_ui._overlay_coordinator_2026_installed = True
