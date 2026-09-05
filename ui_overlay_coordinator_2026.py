from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

import ui_full_overhaul_2026 as full_ui


def _band_visible(app: Any) -> bool:
    return bool(full_ui._overlay_state(app, "band").get("visible"))


def _close_band_if_needed(app: Any) -> None:
    if _band_visible(app):
        full_ui._hide_feature_overlay(app, "band")


def _force_unmap(panel: Any) -> None:
    """Physically hide a panel even before the overlay registry knows about it."""
    if panel is None:
        return
    for method_name in ("grid_remove", "pack_forget", "place_forget"):
        try:
            getattr(panel, method_name)()
        except (tk.TclError, AttributeError):
            pass


def _dedupe_songs_button(app: Any) -> None:
    """Keep exactly one visible top-bar Songs action."""
    songs = getattr(app, "_ux_songs_button", None)
    library = full_ui._find_button(app, "Library")
    if songs is None or library is None or songs is library:
        return
    try:
        manager = str(library.winfo_manager())
    except (tk.TclError, AttributeError):
        manager = ""
    try:
        # v3.4 intentionally grid-removes the old Library button. In that case
        # the responsive layer's generated Songs button is the real visible
        # control; destroying it would leave users with no Library entry point.
        if not manager:
            library.destroy()
            return
        # If a future layout keeps the legacy button mapped, reuse it rather
        # than drawing a second control in the same top-bar cell.
        library.configure(text="Songs")
        songs.destroy()
        app._ux_songs_button = library
    except (tk.TclError, AttributeError):
        pass


def _widget_for_variable(panel: Any, variable: Any, class_name: str | None = None) -> Any | None:
    if panel is None or variable is None:
        return None
    target = str(variable)
    try:
        children = tuple(panel.winfo_children())
    except (tk.TclError, AttributeError):
        return None
    for widget in children:
        try:
            if class_name is not None and widget.winfo_class() != class_name:
                continue
            if "textvariable" in widget.keys() and str(widget.cget("textvariable")) == target:
                return widget
        except (tk.TclError, TypeError, AttributeError):
            pass
    return None


def _calibration_text_widget(panel: Any, text: str) -> Any | None:
    try:
        children = tuple(panel.winfo_children())
    except (tk.TclError, AttributeError):
        return None
    for widget in children:
        try:
            if str(widget.cget("text")) == text:
                return widget
        except (tk.TclError, TypeError):
            pass
    return None


def _reflow_calibration_panel(app: Any) -> None:
    """Stack Calibration controls before the seven-column form can clip."""
    panel = getattr(app, "_calibration_panel", None)
    if panel is None:
        return
    full_ui._remember_grid_children(panel, "_ux_calibration_grid")
    try:
        width = max(1, int(panel.winfo_width()))
    except (tk.TclError, TypeError, ValueError):
        return

    compact = width < 700
    previous = getattr(panel, "_ux_calibration_compact", None)
    panel._ux_calibration_compact = compact

    # Long explanatory labels need to track the actual overlay width even if
    # the grid mode did not change during this Configure event.
    for child in panel.winfo_children():
        info = getattr(child, "_ux_calibration_grid", None)
        try:
            if (
                child.winfo_class() == "TLabel"
                and isinstance(info, dict)
                and int(info.get("row", -1)) >= 2
            ):
                child.configure(wraplength=max(220, width - 30), justify="left")
        except (tk.TclError, TypeError, ValueError):
            pass

    if previous == compact:
        return

    if not compact:
        full_ui._restore_grid_children(panel, "_ux_calibration_grid")
        try:
            for column in range(7):
                panel.columnconfigure(column, weight=0)
            panel.columnconfigure(3, weight=1)
        except tk.TclError:
            pass
        return

    instrument_label = _calibration_text_widget(panel, "Instrument")
    instrument_value = _widget_for_variable(panel, getattr(app, "_calibration_instrument_var", None), "TLabel")
    test_label = _calibration_text_widget(panel, "Test")
    test_combo = _widget_for_variable(panel, getattr(app, "_calibration_test_var", None), "TCombobox")
    value_label = _calibration_text_widget(panel, "Value")
    value_spin = _widget_for_variable(panel, getattr(app, "_calibration_value_var", None), "TSpinbox")
    ms_label = _calibration_text_widget(panel, "ms")
    poly_label = _calibration_text_widget(panel, "Working chord keys (not verified)")
    poly_spin = _widget_for_variable(panel, getattr(app, "_calibration_polyphony_var", None), "TSpinbox")
    save_button = _calibration_text_widget(panel, "Save working value")
    play_button = getattr(app, "_calibration_play_button", None)
    feedback = tuple(getattr(app, "_calibration_feedback_buttons", ()))
    summary = _widget_for_variable(panel, getattr(app, "_calibration_summary_var", None), "TLabel")
    hint = None
    for child in panel.winfo_children():
        info = getattr(child, "_ux_calibration_grid", None)
        try:
            if child.winfo_class() == "TLabel" and isinstance(info, dict) and int(info.get("row", -1)) == 3:
                hint = child
                break
        except (tk.TclError, TypeError, ValueError):
            pass

    try:
        for column in range(7):
            panel.columnconfigure(column, weight=0)
        panel.columnconfigure(1, weight=1)
        panel.columnconfigure(2, weight=1)
        panel.columnconfigure(3, weight=1)

        if instrument_label is not None:
            instrument_label.grid_configure(row=0, column=0, sticky="w", padx=0, pady=0)
        if instrument_value is not None:
            instrument_value.grid_configure(row=0, column=1, columnspan=3, sticky="w", padx=(8, 0), pady=0)

        if test_label is not None:
            test_label.grid_configure(row=1, column=0, sticky="w", padx=0, pady=(7, 0))
        if test_combo is not None:
            test_combo.grid_configure(row=1, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=(7, 0))

        if value_label is not None:
            value_label.grid_configure(row=2, column=0, sticky="w", padx=0, pady=(7, 0))
        if value_spin is not None:
            value_spin.grid_configure(row=2, column=1, sticky="w", padx=(8, 0), pady=(7, 0))
        if ms_label is not None:
            ms_label.grid_configure(row=2, column=2, sticky="w", padx=(4, 0), pady=(7, 0))

        if poly_label is not None:
            poly_label.grid_configure(row=3, column=0, columnspan=2, sticky="w", padx=0, pady=(8, 0))
        if poly_spin is not None:
            poly_spin.grid_configure(row=3, column=2, sticky="w", padx=(8, 0), pady=(8, 0))

        if save_button is not None:
            save_button.grid_configure(row=4, column=0, columnspan=2, sticky="w", padx=0, pady=(8, 0))
        if play_button is not None:
            play_button.grid_configure(row=4, column=2, columnspan=2, sticky="w", padx=(8, 0), pady=(8, 0))

        for index, button in enumerate(feedback[:3]):
            button.grid_configure(
                row=5,
                column=index,
                columnspan=1,
                sticky="w",
                padx=(0 if index == 0 else 8, 0),
                pady=(8, 0),
            )

        if summary is not None:
            summary.grid_configure(row=6, column=0, columnspan=4, sticky="ew", padx=0, pady=(10, 0))
            summary.configure(wraplength=max(220, width - 30), justify="left")
        if hint is not None:
            hint.grid_configure(row=7, column=0, columnspan=4, sticky="ew", padx=0, pady=(5, 0))
            hint.configure(wraplength=max(220, width - 30), justify="left")
    except tk.TclError:
        pass


def _schedule_calibration_reflow(app: Any) -> None:
    panel = getattr(app, "_calibration_panel", None)
    if panel is None or bool(getattr(panel, "_ux_calibration_reflow_pending", False)):
        return
    panel._ux_calibration_reflow_pending = True

    def run() -> None:
        panel._ux_calibration_reflow_pending = False
        _reflow_calibration_panel(app)

    try:
        app.after_idle(run)
    except tk.TclError:
        panel._ux_calibration_reflow_pending = False


def install_overlay_coordinator() -> None:
    """Make Studio's secondary surfaces mutually exclusive on compact screens."""
    if getattr(full_ui, "_overlay_coordinator_2026_installed", False):
        return

    import gaming_runtime_2026 as gaming_runtime
    import gaming_ui_2026 as gaming_ui
    import playback_advanced_ui as advanced_ui
    import playback_calibration_ui as calibration_ui
    import ui_persistent_library as persistent

    original_settings = full_ui._set_settings_visible
    original_feature = full_ui._show_feature_overlay
    original_library = full_ui._show_library
    original_toggle_library = full_ui._toggle_library
    original_root = full_ui._responsive_root
    original_finalize = full_ui._finalize_app_ui
    original_custom_show = advanced_ui._show_custom_panel
    original_calibration_show = calibration_ui._show_panel

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
        # explicitly opening Songs is a navigation action, so make it the only
        # secondary surface instead of stacking it with Settings or a feature
        # overlay. This also covers callers that use the persistent-library API
        # directly instead of going through the top-bar toggle.
        if user_opened:
            app._ux_library_user_closed = False
            _close_band_if_needed(app)
            if bool(getattr(app, "_gaming_settings_visible", False)):
                set_settings_visible(app, False)
            full_ui._hide_feature_overlay(app, "custom")
            full_ui._hide_feature_overlay(app, "calibration")
        original_library(app, user_opened=user_opened)

    def toggle_library(app: Any) -> None:
        # Remember an explicit close separately from the automatic compact
        # collapse. Without this distinction, an early 1px Tk configure event
        # can hide the default Library during startup and it never comes back on
        # a normal desktop; conversely, blindly restoring it would ignore a real
        # user choice to close Songs.
        was_visible = bool(getattr(app, "_gaming_library_visible", False))
        app._ux_library_user_closed = was_visible
        original_toggle_library(app)
        if not was_visible:
            app._ux_library_user_closed = False

    def show_custom_panel(app: Any, visible: bool) -> None:
        # Advanced UI creates and grids/packs the panel before calling its final
        # hide during App construction. At that moment the final overlay state
        # has never registered the panel, so the generic hide alone cannot find
        # it. Unmap the real widget first to prevent a hidden Custom surface from
        # leaking into Band Room or the main player on first launch.
        if not visible:
            _force_unmap(getattr(app, "custom_settings_frame", None))
        original_custom_show(app, visible)

    def show_calibration_panel(app: Any, visible: bool) -> None:
        # Calibration has the same construction order as Custom tuning: its
        # LabelFrame is initially gridded before the first hide call. Physically
        # unmap it before delegating so it cannot remain visible beneath another
        # overlay merely because its overlay state is not initialized yet.
        panel = getattr(app, "_calibration_panel", None)
        if not visible:
            _force_unmap(panel)
            original_calibration_show(app, False)
            return
        original_calibration_show(app, True)
        panel = getattr(app, "_calibration_panel", None)
        if panel is not None and not bool(getattr(panel, "_ux_calibration_reflow_bound", False)):
            try:
                panel.bind("<Configure>", lambda _event: _schedule_calibration_reflow(app), add="+")
                panel._ux_calibration_reflow_bound = True
            except tk.TclError:
                pass
        _schedule_calibration_reflow(app)

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

        body_width, _body_height = full_ui._safe_dimensions(getattr(app, "_gaming_body", app))
        if (
            body_width >= 820
            and not bool(getattr(app, "_gaming_library_visible", False))
            and not bool(getattr(app, "_ux_library_user_closed", False))
        ):
            # Recover from startup/temporary compact Configure events. This is an
            # automatic restore, so it does not mark the Library as user-opened.
            show_library(app, user_opened=False)

        if preserve_settings and bool(getattr(app, "_gaming_settings_visible", False)):
            full_ui._refresh_settings_position(app)
        if full_ui._overlay_state(app, "calibration").get("visible"):
            _schedule_calibration_reflow(app)

    def finalize(app: Any) -> None:
        original_finalize(app)
        _dedupe_songs_button(app)

    full_ui._set_settings_visible = set_settings_visible
    full_ui._show_feature_overlay = show_feature_overlay
    full_ui._show_library = show_library
    full_ui._toggle_library = toggle_library
    full_ui._responsive_root = responsive_root
    full_ui._finalize_app_ui = finalize
    gaming_ui._toggle_library = toggle_library
    gaming_runtime._toggle_library = toggle_library
    persistent._toggle_library_persistent = toggle_library
    advanced_ui._show_custom_panel = show_custom_panel
    calibration_ui._show_panel = show_calibration_panel
    full_ui._overlay_coordinator_2026_installed = True
