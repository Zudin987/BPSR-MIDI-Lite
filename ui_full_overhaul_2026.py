from __future__ import annotations

import ctypes
import os
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable


# Final 2026 desktop UI contract. This module installs after every feature layer so
# old UI modules keep their behavior while the final composition becomes adaptive.
_WIDE_LIBRARY = 360
_MEDIUM_LIBRARY = 300
_COMPACT_LIBRARY = 260
_SETTINGS_MIN_WIDTH = 286
_SETTINGS_MAX_WIDTH = 370
_MAIN_MIN_WIDTH = 560
_MAIN_MIN_HEIGHT = 380


def _enable_per_monitor_dpi_awareness() -> None:
    """Best-effort Per-Monitor-V2 DPI awareness before the Tk root is created."""
    if os.name != "nt":
        return
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = (HANDLE)-4.
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError, TypeError, ValueError):
        pass
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE = 2.
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            return
    except (AttributeError, OSError, TypeError, ValueError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def _safe_dimensions(widget: Any) -> tuple[int, int]:
    try:
        return max(1, int(widget.winfo_width())), max(1, int(widget.winfo_height()))
    except (tk.TclError, TypeError, ValueError, AttributeError):
        return 1180, 720


def _children(root: Any):
    try:
        return tuple(root.winfo_children())
    except (tk.TclError, AttributeError):
        return ()


def _walk(root: Any):
    for child in _children(root):
        yield child
        yield from _walk(child)


def _widget_text(widget: Any) -> str:
    try:
        return str(widget.cget("text"))
    except (tk.TclError, TypeError, AttributeError):
        return ""


def _find_button(root: Any, text: str) -> Any | None:
    for widget in _walk(root):
        try:
            if widget.winfo_class() in {"TButton", "TMenubutton"} and _widget_text(widget) == text:
                return widget
        except tk.TclError:
            pass
    return None


def _set_mapped(widget: Any, visible: bool) -> None:
    try:
        manager = widget.winfo_manager()
        if visible:
            if manager == "grid":
                widget.grid()
            elif manager == "pack":
                widget.pack()
            elif manager == "place":
                widget.place()
        elif manager == "grid":
            widget.grid_remove()
        elif manager == "pack":
            widget.pack_forget()
        elif manager == "place":
            widget.place_forget()
    except (tk.TclError, AttributeError):
        pass


def _apply_accessible_styles(app: Any) -> None:
    """Readable desktop typography without wasting 720p vertical space."""
    style = getattr(app, "_style", None)
    if style is None:
        return
    try:
        style.configure(".", font=("Segoe UI", 10))
        style.configure("TButton", padding=(9, 5))
        style.configure("TNotebook.Tab", padding=(10, 6))
        style.configure("Treeview", rowheight=28)
        style.configure("Gaming.Treeview", rowheight=28)
        style.configure("Gaming.Subtitle.TLabel", font=("Segoe UI Variable Text", 10))
        style.configure("Gaming.Section.TLabel", font=("Segoe UI Variable Text", 11, "bold"))
        style.configure("Gaming.Metric.TLabel", font=("Segoe UI Variable Text", 11, "bold"))
        style.configure("Gaming.Micro.TLabel", font=("Segoe UI Variable Text", 9))
        style.configure("Product.MetricName.TLabel", font=("Segoe UI Variable Text", 9))
        style.configure("Product.MetricValue.TLabel", font=("Segoe UI Variable Text", 11, "bold"))
        style.configure("Product.Status.TLabel", font=("Segoe UI Variable Text", 10))
    except tk.TclError:
        pass


def _fit_main_window(app: Any) -> None:
    """Choose an initial geometry that leaves Windows chrome/taskbar headroom."""
    try:
        sw = max(640, int(app.winfo_screenwidth()))
        sh = max(480, int(app.winfo_screenheight()))
        width = min(1180, max(_MAIN_MIN_WIDTH, sw - 80))
        height = min(720, max(_MAIN_MIN_HEIGHT, sh - 100))
        min_width = min(720, max(_MAIN_MIN_WIDTH, sw - 120))
        min_height = min(500, max(_MAIN_MIN_HEIGHT, sh - 130))
        app.geometry(f"{width}x{height}")
        app.minsize(min_width, min_height)
    except (tk.TclError, TypeError, ValueError):
        pass


def _library_width_for(window_width: int) -> int:
    if window_width >= 1280:
        return _WIDE_LIBRARY
    if window_width >= 1040:
        return _MEDIUM_LIBRARY
    return _COMPACT_LIBRARY


def _sync_library_tables(app: Any, width: int) -> None:
    """Keep lower-priority table columns from stealing the Song column."""
    compact = width < 300
    for name in ("online_tree", "bookmark_tree"):
        tree = getattr(app, name, None)
        if tree is None:
            continue
        try:
            tree.configure(displaycolumns=("fit", "notes") if compact else ("fit", "changes", "notes"))
            tree.column("#0", width=max(135, width - (145 if compact else 245)), minwidth=120, stretch=True)
            tree.column("fit", width=72, minwidth=64, stretch=False)
            tree.column("notes", width=64, minwidth=54, stretch=False)
            if not compact:
                tree.column("changes", width=110, minwidth=90, stretch=False)
        except (tk.TclError, KeyError):
            pass
    variable = getattr(app, "online_status_var", None)
    if variable is not None:
        target = str(variable)
        for widget in _walk(getattr(app, "_gaming_library_panel", app)):
            try:
                if widget.winfo_class() == "TLabel" and str(widget.cget("textvariable")) == target:
                    widget.configure(wraplength=max(170, width - 32), justify="left")
            except (tk.TclError, TypeError):
                pass
    try:
        import online_ui
        online_ui._schedule_source_notebook_resize(app)
    except Exception:
        pass


def _hide_library(app: Any) -> None:
    panel = getattr(app, "_gaming_library_panel", None)
    body = getattr(app, "_gaming_body", None)
    if panel is None or body is None:
        return
    try:
        panel.grid_remove()
        panel.place_forget()
        body.columnconfigure(0, minsize=0, weight=0)
        app._gaming_library_visible = False
        app._ux_library_overlay = False
    except tk.TclError:
        pass


def _show_library(app: Any, *, user_opened: bool = False) -> None:
    panel = getattr(app, "_gaming_library_panel", None)
    body = getattr(app, "_gaming_body", None)
    if panel is None or body is None:
        return
    width, height = _safe_dimensions(body)
    library_width = min(_library_width_for(width), max(230, width - 70))
    try:
        panel.grid_remove()
        panel.place_forget()
        panel.configure(width=library_width)
        panel.grid_propagate(False)
        if width < 820:
            body.columnconfigure(0, minsize=0, weight=0)
            panel.place(x=0, y=0, anchor="nw", width=library_width, relheight=1.0)
            panel.lift()
            app._ux_library_overlay = True
        else:
            body.columnconfigure(0, minsize=library_width, weight=0)
            panel.grid(row=0, column=0, sticky="nsew")
            app._ux_library_overlay = False
        app._gaming_library_visible = True
        if user_opened:
            app._ux_library_user_open = True
    except tk.TclError:
        return
    _sync_library_tables(app, library_width)


def _toggle_library(app: Any) -> None:
    if bool(getattr(app, "_gaming_library_visible", False)):
        _hide_library(app)
        app._ux_library_user_open = False
    else:
        _set_settings_visible(app, False)
        _show_library(app, user_opened=True)


def _ensure_songs_button(app: Any) -> None:
    if getattr(app, "_ux_songs_button", None) is not None:
        return
    settings = _find_button(app, "Settings")
    if settings is None:
        return
    top = settings.master
    try:
        button = ttk.Button(top, text="Songs", command=lambda: _toggle_library(app))
        info = settings.grid_info()
        row = int(info.get("row", 0))
        column = max(0, int(info.get("column", 4)) - 1)
        button.grid(row=row, column=column, padx=(8, 0))
        button.lift()
        app._ux_songs_button = button
    except (tk.TclError, TypeError, ValueError):
        return


def _settings_width(app: Any) -> int:
    width, _ = _safe_dimensions(getattr(app, "_gaming_body", app))
    return min(_SETTINGS_MAX_WIDTH, max(_SETTINGS_MIN_WIDTH, int(width * 0.36)))


def _bind_wheel_tree(root: Any, callback: Callable[[Any], Any]) -> None:
    marker = "_ux_wheel_bound"
    for widget in (root, *_walk(root)):
        if getattr(widget, marker, False):
            continue
        try:
            widget.bind("<MouseWheel>", callback, add="+")
            widget.bind("<Button-4>", callback, add="+")
            widget.bind("<Button-5>", callback, add="+")
            setattr(widget, marker, True)
        except (tk.TclError, AttributeError):
            pass


def _wheel_steps(event: Any) -> int:
    delta = int(getattr(event, "delta", 0) or 0)
    if delta:
        return -int(delta / 120) or (-1 if delta > 0 else 1)
    number = getattr(event, "num", None)
    if number == 4:
        return -1
    if number == 5:
        return 1
    return 0


def _settings_scrollbar(app: Any) -> Any | None:
    body = getattr(app, "_gaming_body", None)
    if body is None:
        return None
    scrollbar = getattr(app, "_ux_settings_scrollbar", None)
    if scrollbar is not None:
        return scrollbar
    try:
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=lambda *args: _settings_scroll_command(app, *args))
        app._ux_settings_scrollbar = scrollbar
        return scrollbar
    except tk.TclError:
        return None


def _refresh_settings_position(app: Any) -> None:
    if not bool(getattr(app, "_gaming_settings_visible", False)):
        return
    panel = getattr(app, "_gaming_settings_panel", None)
    body = getattr(app, "_gaming_body", None)
    if panel is None or body is None:
        return
    body_width, body_height = _safe_dimensions(body)
    try:
        panel.update_idletasks()
        requested = max(body_height, int(panel.winfo_reqheight()) + 14)
    except (tk.TclError, TypeError, ValueError):
        requested = body_height
    maximum = max(0, requested - body_height)
    offset = max(0, min(int(getattr(app, "_ux_settings_offset", 0)), maximum))
    app._ux_settings_offset = offset
    width = min(_settings_width(app), max(250, body_width - 32))
    try:
        panel.place_forget()
        panel.place(
            relx=1.0,
            x=-14,
            y=-offset,
            anchor="ne",
            width=width,
            height=requested,
        )
        panel.lift()
    except tk.TclError:
        return
    scrollbar = _settings_scrollbar(app)
    if scrollbar is None:
        return
    if maximum > 0:
        try:
            scrollbar.place(relx=1.0, x=-2, y=4, anchor="ne", height=max(60, body_height - 8))
            first = offset / requested
            last = min(1.0, (offset + body_height) / requested)
            scrollbar.set(first, last)
            scrollbar.lift()
        except tk.TclError:
            pass
    else:
        try:
            scrollbar.place_forget()
        except tk.TclError:
            pass


def _settings_scroll_command(app: Any, *args: str) -> None:
    panel = getattr(app, "_gaming_settings_panel", None)
    body = getattr(app, "_gaming_body", None)
    if panel is None or body is None:
        return
    _, body_height = _safe_dimensions(body)
    try:
        requested = max(body_height, int(panel.winfo_reqheight()) + 14)
    except (tk.TclError, TypeError, ValueError):
        requested = body_height
    maximum = max(0, requested - body_height)
    offset = int(getattr(app, "_ux_settings_offset", 0))
    if args and args[0] == "moveto" and len(args) >= 2:
        offset = int(float(args[1]) * maximum)
    elif args and args[0] == "scroll" and len(args) >= 3:
        amount = int(args[1])
        unit = 48 if args[2] == "units" else max(80, body_height - 80)
        offset += amount * unit
    app._ux_settings_offset = max(0, min(offset, maximum))
    _refresh_settings_position(app)


def _settings_wheel(app: Any, event: Any):
    if not bool(getattr(app, "_gaming_settings_visible", False)):
        return None
    steps = _wheel_steps(event)
    if not steps:
        return None
    _settings_scroll_command(app, "scroll", str(steps), "units")
    return "break"


def _set_settings_visible(app: Any, visible: bool) -> None:
    panel = getattr(app, "_gaming_settings_panel", None)
    body = getattr(app, "_gaming_body", None)
    if panel is None or body is None:
        return
    try:
        panel.grid_remove()
        panel.place_forget()
    except tk.TclError:
        pass
    scrollbar = getattr(app, "_ux_settings_scrollbar", None)
    if not visible:
        if scrollbar is not None:
            try:
                scrollbar.place_forget()
            except tk.TclError:
                pass
        app._gaming_settings_visible = False
        return

    # Side overlays never compete for the same narrow screen edge.
    if bool(getattr(app, "_ux_library_overlay", False)):
        _hide_library(app)
    _hide_feature_overlay(app, "custom")
    _hide_feature_overlay(app, "calibration")
    app._ux_settings_offset = 0
    app._gaming_settings_visible = True
    _bind_wheel_tree(panel, lambda event: _settings_wheel(app, event))
    _refresh_settings_position(app)
    try:
        body.after_idle(lambda: _refresh_settings_position(app))
    except tk.TclError:
        pass


def _toggle_settings(app: Any) -> None:
    _set_settings_visible(app, not bool(getattr(app, "_gaming_settings_visible", False)))


def _overlay_state(app: Any, key: str) -> dict[str, Any]:
    states = getattr(app, "_ux_feature_overlays", None)
    if states is None:
        states = {}
        app._ux_feature_overlays = states
    return states.setdefault(key, {"offset": 0, "visible": False})


def _overlay_scrollbar(app: Any, key: str, close: Callable[[], None]) -> tuple[Any | None, Any | None]:
    body = getattr(app, "_gaming_body", None)
    if body is None:
        return None, None
    state = _overlay_state(app, key)
    scrollbar = state.get("scrollbar")
    close_button = state.get("close_button")
    try:
        if scrollbar is None:
            scrollbar = ttk.Scrollbar(body, orient="vertical",
                                      command=lambda *args: _overlay_scroll_command(app, key, *args))
            state["scrollbar"] = scrollbar
        if close_button is None:
            close_button = ttk.Button(body, text="Close", command=close)
            state["close_button"] = close_button
    except tk.TclError:
        return None, None
    return scrollbar, close_button


def _overlay_geometry(app: Any, key: str) -> tuple[int, int, int, int]:
    state = _overlay_state(app, key)
    panel = state.get("panel")
    body = getattr(app, "_gaming_body", None)
    if panel is None or body is None:
        return 0, 0, 0, 0
    body_width, body_height = _safe_dimensions(body)
    max_width = int(state.get("max_width", 760))
    width = min(max_width, max(280, body_width - 28))
    try:
        panel.update_idletasks()
        requested = max(1, int(panel.winfo_reqheight()) + 18)
    except (tk.TclError, TypeError, ValueError):
        requested = body_height
    viewport = max(160, body_height - 24)
    maximum = max(0, requested - viewport)
    offset = max(0, min(int(state.get("offset", 0)), maximum))
    state["offset"] = offset
    return width, requested, viewport, maximum


def _refresh_feature_overlay(app: Any, key: str) -> None:
    state = _overlay_state(app, key)
    if not state.get("visible"):
        return
    panel = state.get("panel")
    body = getattr(app, "_gaming_body", None)
    if panel is None or body is None:
        return
    width, requested, viewport, maximum = _overlay_geometry(app, key)
    offset = int(state.get("offset", 0))
    try:
        panel.grid_remove()
        panel.place_forget()
        panel.place(relx=0.5, y=12 - offset, anchor="n", width=width, height=requested)
        panel.lift()
    except tk.TclError:
        return

    close_fn = state.get("close")
    scrollbar, close_button = _overlay_scrollbar(app, key, close_fn)
    _, body_height = _safe_dimensions(body)
    if close_button is not None:
        try:
            close_button.place(relx=0.5, x=width // 2 - 10, y=18, anchor="ne")
            close_button.lift()
        except tk.TclError:
            pass
    if scrollbar is not None:
        if maximum > 0:
            try:
                scrollbar.place(relx=0.5, x=width // 2 - 2, y=54, anchor="ne",
                                height=max(70, body_height - 70))
                first = offset / requested
                last = min(1.0, (offset + viewport) / requested)
                scrollbar.set(first, last)
                scrollbar.lift()
            except tk.TclError:
                pass
        else:
            try:
                scrollbar.place_forget()
            except tk.TclError:
                pass


def _overlay_scroll_command(app: Any, key: str, *args: str) -> None:
    state = _overlay_state(app, key)
    if not state.get("visible"):
        return
    _width, _requested, viewport, maximum = _overlay_geometry(app, key)
    offset = int(state.get("offset", 0))
    if args and args[0] == "moveto" and len(args) >= 2:
        offset = int(float(args[1]) * maximum)
    elif args and args[0] == "scroll" and len(args) >= 3:
        amount = int(args[1])
        unit = 48 if args[2] == "units" else max(80, viewport - 80)
        offset += amount * unit
    state["offset"] = max(0, min(offset, maximum))
    _refresh_feature_overlay(app, key)


def _overlay_wheel(app: Any, key: str, event: Any):
    state = _overlay_state(app, key)
    if not state.get("visible"):
        return None
    steps = _wheel_steps(event)
    if not steps:
        return None
    _overlay_scroll_command(app, key, "scroll", str(steps), "units")
    return "break"


def _hide_feature_overlay(app: Any, key: str) -> None:
    state = _overlay_state(app, key)
    panel = state.get("panel")
    if panel is not None:
        try:
            panel.grid_remove()
            panel.place_forget()
        except tk.TclError:
            pass
    for name in ("scrollbar", "close_button"):
        widget = state.get(name)
        if widget is not None:
            try:
                widget.place_forget()
            except tk.TclError:
                pass
    state["visible"] = False


def _show_feature_overlay(app: Any, key: str, panel: Any, max_width: int, close: Callable[[], None]) -> None:
    _set_settings_visible(app, False)
    if bool(getattr(app, "_ux_library_overlay", False)):
        _hide_library(app)
    other = "calibration" if key == "custom" else "custom"
    _hide_feature_overlay(app, other)
    state = _overlay_state(app, key)
    state.update({"panel": panel, "max_width": max_width, "close": close, "offset": 0, "visible": True})
    _bind_wheel_tree(panel, lambda event: _overlay_wheel(app, key, event))
    _refresh_feature_overlay(app, key)
    try:
        app.after_idle(lambda: _refresh_feature_overlay(app, key))
    except tk.TclError:
        pass


def _install_feature_overlay_hooks() -> None:
    try:
        import playback_advanced_ui as advanced
    except Exception:
        advanced = None
    if advanced is not None:
        def show_custom(app: Any, visible: bool) -> None:
            panel = getattr(app, "custom_settings_frame", None)
            if panel is None:
                return
            if not visible:
                _hide_feature_overlay(app, "custom")
                return
            _show_feature_overlay(
                app,
                "custom",
                panel,
                780,
                lambda: _hide_feature_overlay(app, "custom"),
            )
        advanced._show_custom_panel = show_custom

    try:
        import playback_calibration_ui as calibration
    except Exception:
        calibration = None
    if calibration is not None:
        def show_calibration(app: Any, visible: bool) -> None:
            panel = getattr(app, "_calibration_panel", None)
            if panel is None:
                return
            if not visible:
                _hide_feature_overlay(app, "calibration")
                app._calibration_visible = False
                return
            app._calibration_visible = True
            _show_feature_overlay(
                app,
                "calibration",
                panel,
                820,
                lambda: show_calibration(app, False),
            )
        calibration._show_panel = show_calibration


def _remember_pack(widget: Any) -> None:
    if getattr(widget, "_ux_saved_pack", None) is not None:
        return
    try:
        if widget.winfo_manager() == "pack":
            info = dict(widget.pack_info())
            info.pop("in", None)
            widget._ux_saved_pack = info
    except (tk.TclError, AttributeError):
        pass


def _restore_pack(widget: Any) -> bool:
    info = getattr(widget, "_ux_saved_pack", None)
    if not info:
        return False
    try:
        widget.pack(**info)
        return True
    except tk.TclError:
        return False


def _hide_song_diagnostics(app: Any) -> None:
    for name in ("_product_detail_label", "_product_impact_label", "_adaptive_impact_canvas"):
        widget = getattr(app, name, None)
        if widget is None:
            continue
        _remember_pack(widget)
        try:
            widget.pack_forget()
        except tk.TclError:
            pass
    app._product_details_visible = False
    button = getattr(app, "_product_detail_button", None)
    if button is not None:
        try:
            button.configure(text="Details ▸")
        except tk.TclError:
            pass


def _toggle_song_details(app: Any) -> None:
    visible = bool(getattr(app, "_product_details_visible", False))
    detail = getattr(app, "_product_detail_label", None)
    impact_label = getattr(app, "_product_impact_label", None)
    impact_canvas = getattr(app, "_adaptive_impact_canvas", None)
    widgets = [detail, impact_label, impact_canvas]
    if visible:
        for widget in widgets:
            if widget is not None:
                try:
                    widget.pack_forget()
                except tk.TclError:
                    pass
    else:
        # Product v3.4 intentionally hid the long analysis label before this
        # final layer was installed, so it may no longer have pack_info. Put it
        # back next to Details using the same anchor contract as the original UI.
        if detail is not None and not _restore_pack(detail):
            anchor = getattr(app, "_product_impact_anchor", None)
            try:
                kwargs = dict(fill="x", anchor="w", pady=(5, 3))
                if anchor is not None:
                    kwargs["before"] = anchor
                detail.pack(**kwargs)
            except tk.TclError:
                pass
        for widget in (impact_label, impact_canvas):
            if widget is not None:
                _restore_pack(widget)
    app._product_details_visible = not visible
    button = getattr(app, "_product_detail_button", None)
    if button is not None:
        try:
            button.configure(text="Details ▾" if not visible else "Details ▸")
        except tk.TclError:
            pass


def _reflow_metric_cards(app: Any) -> None:
    frame = getattr(app, "_product_metrics_frame", None)
    if frame is None:
        return
    try:
        width = max(1, int(frame.winfo_width()))
        children = tuple(frame.winfo_children())
    except (tk.TclError, TypeError, ValueError):
        return
    columns = 2 if width < 520 else 4
    previous = getattr(frame, "_ux_columns", None)
    if previous == columns:
        return
    frame._ux_columns = columns
    for column in range(4):
        try:
            frame.columnconfigure(column, weight=0)
        except tk.TclError:
            pass
    for index, child in enumerate(children):
        row, column = divmod(index, columns)
        try:
            child.grid_configure(row=row, column=column, sticky="nsew",
                                 padx=(0 if column == 0 else 4, 0), pady=(0, 4))
            frame.columnconfigure(column, weight=1, uniform="song-metrics-responsive")
        except tk.TclError:
            pass


def _install_product_hooks() -> None:
    try:
        import ui_product_overhaul_v34 as product
        import gaming_ui_2026 as gaming_ui
        import gaming_runtime_2026 as gaming_runtime
        import ui_persistent_library as persistent
    except Exception:
        return

    # The v3.4 fixed 400px Library was useful on a large desktop but it defeats
    # 720p/high-DPI layouts. Keep it visible by default, not permanently.
    persistent._LIBRARY_WIDTH = _WIDE_LIBRARY
    persistent._CENTER_MIN_WIDTH = 360
    persistent._MIN_WINDOW_WIDTH = _MAIN_MIN_WIDTH

    def force_library(app: Any) -> None:
        width, _ = _safe_dimensions(getattr(app, "_gaming_body", app))
        if width < 820 and not bool(getattr(app, "_ux_library_user_open", False)):
            _hide_library(app)
        else:
            _show_library(app)
    persistent._force_library_open = force_library
    persistent._toggle_library_persistent = _toggle_library
    persistent._set_library_visible_persistent = lambda app, visible=True: (
        _show_library(app, user_opened=True) if visible else _hide_library(app)
    )
    persistent._persistent_responsive_layout = lambda app, width: _responsive_root(app, width)

    product._set_settings_drawer_visible = _set_settings_visible
    product._toggle_settings_drawer = _toggle_settings
    product._drawer_width = _settings_width
    product._toggle_technical_details = _toggle_song_details

    gaming_ui._toggle_library = _toggle_library
    gaming_ui._toggle_settings = _toggle_settings
    gaming_ui._responsive_layout = lambda app, width: _responsive_root(app, width)
    gaming_runtime._set_library_visible = lambda app, visible: (
        _show_library(app, user_opened=True) if visible else _hide_library(app)
    )
    gaming_runtime._toggle_library = _toggle_library
    gaming_runtime._set_settings_visible = _set_settings_visible
    gaming_runtime._toggle_settings = _toggle_settings


def _find_parent_button(root: Any, texts: tuple[str, ...]) -> Any | None:
    for widget in _walk(root):
        if _widget_text(widget) in texts:
            return widget
    return None


def _studio_tree_simplify(owner: Any) -> None:
    tree = getattr(owner, "source_tree", None)
    if tree is not None:
        try:
            # Selection + one primary button is clearer than repeating a per-row
            # "Download -> Analyze" status in a dedicated action column.
            columns = tuple(str(value) for value in tree.cget("columns"))
            keep = tuple(value for value in columns if value not in {"availability", "action"})
            if keep:
                tree.configure(displaycolumns=keep)
            tree.column("#0", minwidth=150, stretch=True)
            if "artist" in columns:
                tree.column("artist", minwidth=100, stretch=True)
            for source_name in ("provider", "source"):
                if source_name in columns:
                    tree.column(source_name, width=110, minwidth=80, stretch=False)
        except (tk.TclError, TypeError):
            pass


def _studio_hide_single_source_combo(owner: Any) -> None:
    entry = getattr(owner, "music_search_entry", None)
    if entry is None:
        return
    frame = entry.master
    combos = [widget for widget in _children(frame) if widget.winfo_class() == "TCombobox"]
    for combo in combos:
        try:
            values = tuple(str(value) for value in combo.cget("values"))
        except (tk.TclError, TypeError):
            values = ()
        # beta.5/6 repurpose the legacy storefront selector to one non-choice.
        if len(values) <= 1 or values in {("Auto",), ("spotDL",)}:
            try:
                combo.grid_remove()
            except tk.TclError:
                pass
            owner._ux_hidden_source_combo = combo


def _studio_polish_buttons(owner: Any) -> None:
    root = getattr(owner, "workspace", None)
    if root is None:
        return
    for widget in _walk(root):
        text = _widget_text(widget)
        try:
            if text == "Advanced":
                widget.configure(text="Models & quality…")
            elif text == "Technical details":
                widget.configure(text="Details…")
            elif text == "Downloader info":
                widget.configure(text="Download info")
            elif text == "Source setup":
                widget.configure(text="Source info")
            elif text == "Open arrangement":
                widget.configure(text="Open saved arrangement…")
            elif text == "Apply melody / category":
                widget.configure(text="Apply changes")
        except tk.TclError:
            pass


def _studio_search_reflow(owner: Any) -> None:
    if getattr(owner, "_ux_search_reflow_installed", False):
        return
    entry = getattr(owner, "music_search_entry", None)
    search_button = getattr(owner, "search_button", None)
    if entry is None or search_button is None:
        return
    owner._ux_search_reflow_installed = True
    frame = entry.master
    tertiary = next(
        (widget for widget in _children(frame)
         if widget.winfo_class() == "TButton" and widget is not search_button),
        None,
    )
    state = {"mode": None}

    def render(event=None):
        width = int(getattr(event, "width", 0) or frame.winfo_width() or 700)
        mode = "wide" if width >= 610 else "narrow"
        if state["mode"] == mode:
            return
        state["mode"] = mode
        for widget in (entry, search_button, tertiary):
            if widget is None:
                continue
            try:
                widget.grid_forget()
            except tk.TclError:
                pass
        for combo in [widget for widget in _children(frame) if widget.winfo_class() == "TCombobox"]:
            try:
                combo.grid_remove()
            except tk.TclError:
                pass
        frame.columnconfigure(0, weight=1)
        if mode == "wide":
            entry.grid(row=0, column=0, sticky="ew")
            search_button.grid(row=0, column=1, padx=(6, 0))
            if tertiary is not None:
                tertiary.grid(row=0, column=2, padx=(6, 0))
        else:
            entry.grid(row=0, column=0, columnspan=2, sticky="ew")
            search_button.grid(row=1, column=0, sticky="w", pady=(6, 0))
            if tertiary is not None:
                tertiary.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(6, 0))

    frame.bind("<Configure>", render, add="+")
    frame.after_idle(render)


def _install_studio_hooks() -> None:
    try:
        import studio_band_ui
    except Exception:
        return
    try:
        import studio_band_responsive
        studio_band_responsive._responsive_search_row = _studio_search_reflow
    except Exception:
        pass
    cls = studio_band_ui.BandAudioTab
    if getattr(cls, "_full_ux_overhaul_installed", False):
        return
    original_init = cls.__init__
    original_open_workspace = cls.open_workspace

    def init(self, app):
        original_init(self, app)
        _studio_hide_single_source_combo(self)
        _studio_tree_simplify(self)
        _studio_polish_buttons(self)
        _studio_search_reflow(self)
        # Keep the separate workspace useful at small screen sizes, but stop
        # opening larger than the active desktop.
        try:
            self.workspace.bind("<Escape>", lambda _event: self.hide_workspace(), add="+")
        except tk.TclError:
            pass

    def open_workspace(self):
        original_open_workspace(self)
        try:
            self.workspace.update_idletasks()
            sw = max(640, int(self.workspace.winfo_screenwidth()))
            sh = max(480, int(self.workspace.winfo_screenheight()))
            width = min(1120, max(560, sw - 60))
            height = min(760, max(420, sh - 90))
            x = max(0, (sw - width) // 2)
            y = max(0, (sh - height) // 3)
            self.workspace.geometry(f"{width}x{height}+{x}+{y}")
            self.workspace.minsize(min(620, width), min(440, height))
        except (tk.TclError, TypeError, ValueError):
            pass

    cls.__init__ = init
    cls.open_workspace = open_workspace
    cls._full_ux_overhaul_installed = True


def _remember_grid_children(frame: Any, key: str = "_ux_saved_grid") -> None:
    for widget in _children(frame):
        if getattr(widget, key, None) is not None:
            continue
        try:
            info = dict(widget.grid_info())
            if info:
                info.pop("in", None)
                setattr(widget, key, info)
        except (tk.TclError, AttributeError):
            pass


def _restore_grid_children(frame: Any, key: str = "_ux_saved_grid") -> None:
    for widget in _children(frame):
        info = getattr(widget, key, None)
        if not info:
            continue
        try:
            widget.grid_configure(**info)
        except tk.TclError:
            pass


def _label_for_variable(frame: Any, variable: Any) -> Any | None:
    if variable is None:
        return None
    target = str(variable)
    for widget in _children(frame):
        try:
            if str(widget.cget("textvariable")) == target:
                return widget
        except (tk.TclError, TypeError):
            pass
    return None


def _reflow_primary_setup(app: Any) -> None:
    frame = getattr(app, "_product_setup_frame", None)
    if frame is None:
        return
    try:
        width = max(1, int(frame.winfo_width()))
    except (tk.TclError, TypeError, ValueError):
        return
    _remember_grid_children(frame, "_ux_setup_grid")
    narrow = width < 500
    if getattr(frame, "_ux_setup_narrow", None) == narrow:
        return
    frame._ux_setup_narrow = narrow
    if not narrow:
        _restore_grid_children(frame, "_ux_setup_grid")
        try:
            frame.columnconfigure(0, weight=1, uniform="primary-setup")
            frame.columnconfigure(1, weight=2, uniform="primary-setup")
        except tk.TclError:
            pass
        return

    labels = [widget for widget in _children(frame) if widget.winfo_class() == "TLabel"]
    instrument_label = next((w for w in labels if _widget_text(w) == "Instrument"), None)
    category_label = next((w for w in labels if _widget_text(w) == "Unlocked category"), None)
    instrument_combo = getattr(app, "_primary_instrument_combo", None)
    profile_combo = getattr(app, "_primary_profile_combo", None)
    summary = getattr(app, "_primary_profile_summary_label", None)
    band_toggle = next((w for w in _children(frame) if _widget_text(w) == "Band Mode (Beta)"), None)
    band_hint = next((w for w in labels if _widget_text(w).startswith("Same MIDI")), None)
    try:
        frame.columnconfigure(0, weight=1, uniform="")
        frame.columnconfigure(1, weight=0, uniform="")
        if instrument_label is not None:
            instrument_label.grid_configure(row=0, column=0, columnspan=2, sticky="w", padx=0)
        if instrument_combo is not None:
            instrument_combo.grid_configure(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=(3, 6))
        if category_label is not None:
            category_label.grid_configure(row=2, column=0, columnspan=2, sticky="w", padx=0)
        if profile_combo is not None:
            profile_combo.grid_configure(row=3, column=0, columnspan=2, sticky="ew", padx=0, pady=(3, 0))
        if summary is not None:
            summary.grid_configure(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
            summary.configure(wraplength=max(220, width - 24))
        if band_toggle is not None:
            band_toggle.grid_configure(row=5, column=0, columnspan=2, sticky="w", pady=(7, 0))
        if band_hint is not None:
            band_hint.grid_configure(row=6, column=0, columnspan=2, sticky="ew", pady=(3, 0))
            band_hint.configure(wraplength=max(220, width - 24), justify="left")
    except tk.TclError:
        pass


def _reflow_band_panel(app: Any) -> None:
    frame = getattr(app, "_band_frame", None)
    if frame is None:
        return
    try:
        width = max(1, int(frame.winfo_width()))
    except (tk.TclError, TypeError, ValueError):
        return
    _remember_grid_children(frame, "_ux_band_grid")
    narrow = width < 560
    if getattr(frame, "_ux_band_narrow", None) == narrow:
        # Wrap status copy even when only the width changed.
        for widget in _children(frame):
            try:
                if widget.winfo_class() == "TLabel" and str(widget.cget("textvariable")) in {
                    str(getattr(app, "_band_players_var", "")),
                    str(getattr(app, "_band_room_status_var", "")),
                    str(getattr(app, "_band_part_summary_var", "")),
                }:
                    widget.configure(wraplength=max(220, width - 24), justify="left")
            except (tk.TclError, TypeError):
                pass
        return
    frame._ux_band_narrow = narrow
    if not narrow:
        _restore_grid_children(frame, "_ux_band_grid")
        try:
            frame.columnconfigure(1, weight=1)
            frame.columnconfigure(3, weight=1)
        except tk.TclError:
            pass
        actions = next(
            (w for w in _children(frame)
             if w.winfo_class() == "TFrame"
             and any(c is getattr(app, "_band_ready_button", None) for c in _children(w))),
            None,
        )
        if actions is not None:
            _restore_grid_children(actions, "_ux_band_action_grid")
        return

    name_label = next((w for w in _children(frame) if _widget_text(w) == "Name"), None)
    part_label = next((w for w in _children(frame) if _widget_text(w) == "Your part"), None)
    room_label = next((w for w in _children(frame) if _widget_text(w) == "Room code"), None)
    name_entry = _label_for_variable(frame, getattr(app, "_band_name_var", None))
    room_entry = _label_for_variable(frame, getattr(app, "_band_room_code_var", None))
    role_combo = getattr(app, "_band_role_combo", None)
    direct_frames = [w for w in _children(frame) if w.winfo_class() == "TFrame"]
    buttons = next(
        (w for w in direct_frames if any(_widget_text(c) == "Create" for c in _children(w))),
        None,
    )
    actions = next(
        (w for w in direct_frames if any(c is getattr(app, "_band_ready_button", None) for c in _children(w))),
        None,
    )
    status_widgets = []
    for variable in (
        getattr(app, "_band_players_var", None),
        getattr(app, "_band_room_status_var", None),
        getattr(app, "_band_part_summary_var", None),
    ):
        widget = _label_for_variable(frame, variable)
        if widget is not None:
            status_widgets.append(widget)

    try:
        for column in range(4):
            frame.columnconfigure(column, weight=0)
        frame.columnconfigure(1, weight=1)
        if name_label is not None:
            name_label.grid_configure(row=0, column=0, sticky="w")
        if name_entry is not None:
            name_entry.grid_configure(row=0, column=1, columnspan=3, sticky="ew", padx=(6, 0), pady=0)
        if part_label is not None:
            part_label.grid_configure(row=1, column=0, sticky="w", pady=(7, 0))
        if role_combo is not None:
            role_combo.grid_configure(row=1, column=1, columnspan=3, sticky="ew", padx=(6, 0), pady=(7, 0))
        if room_label is not None:
            room_label.grid_configure(row=2, column=0, sticky="w", pady=(7, 0))
        if room_entry is not None:
            room_entry.grid_configure(row=2, column=1, columnspan=3, sticky="ew", padx=(6, 0), pady=(7, 0))
        if buttons is not None:
            buttons.grid_configure(row=3, column=0, columnspan=4, sticky="w", pady=(7, 0))
        if actions is not None:
            _remember_grid_children(actions, "_ux_band_action_grid")
            actions.grid_configure(row=4, column=0, columnspan=4, sticky="ew", pady=(7, 0))
            clock = _label_for_variable(actions, getattr(app, "_band_sync_var", None))
            if clock is not None:
                clock.grid_configure(row=1, column=0, columnspan=4, sticky="w", pady=(5, 0))
                clock.configure(wraplength=max(210, width - 30), justify="left")
        for index, widget in enumerate(status_widgets, 5):
            widget.grid_configure(row=index, column=0, columnspan=4, sticky="ew", pady=(5, 0))
            widget.configure(wraplength=max(220, width - 24), justify="left")
    except tk.TclError:
        pass


def _responsive_topbar(app: Any, width: int) -> None:
    settings = _find_button(app, "Settings")
    if settings is None:
        return
    top = settings.master
    version = str(getattr(getattr(app, "_modern_module", None), "APP_VERSION", ""))
    for widget in _children(top):
        if widget.winfo_class() != "TLabel":
            continue
        try:
            text = str(widget.cget("text"))
        except tk.TclError:
            continue
        if text == version:
            try:
                if width < 760:
                    widget.grid_remove()
                else:
                    widget.grid()
            except tk.TclError:
                pass


def _responsive_root(app: Any, width: int | None = None) -> None:
    body = getattr(app, "_gaming_body", None)
    if body is None:
        return
    body_width, _body_height = _safe_dimensions(body)
    window_width = int(width or getattr(app, "winfo_width", lambda: body_width)())
    _ensure_songs_button(app)

    # Center content wins on narrow/high-DPI windows. The Song Library remains a
    # one-click overlay instead of imposing a 990px minimum width.
    visible = bool(getattr(app, "_gaming_library_visible", False))
    if body_width < 820:
        if visible and not bool(getattr(app, "_ux_library_user_open", False)):
            _hide_library(app)
        elif visible:
            _show_library(app)
    elif visible:
        _show_library(app)

    if body_width < 720 and bool(getattr(app, "_gaming_settings_visible", False)):
        _set_settings_visible(app, False)
    elif bool(getattr(app, "_gaming_settings_visible", False)):
        _refresh_settings_position(app)

    for key in ("custom", "calibration"):
        if _overlay_state(app, key).get("visible"):
            _refresh_feature_overlay(app, key)

    _responsive_topbar(app, window_width)
    _reflow_primary_setup(app)
    _reflow_band_panel(app)
    _reflow_metric_cards(app)


def _add_custom_tuning_shortcut(app: Any) -> None:
    settings = getattr(app, "_gaming_settings_panel", None)
    if settings is None or getattr(app, "_ux_custom_tuning_button", None) is not None:
        return
    try:
        rows = []
        for child in _children(settings):
            info = child.grid_info()
            if info:
                rows.append(int(info.get("row", 0)))
        row = (max(rows) + 1) if rows else 15
        button = ttk.Button(
            settings,
            text="Custom tuning…",
            command=lambda: _open_custom_tuning(app),
        )
        button.grid(row=row, column=0, sticky="ew", pady=(8, 0))
        app._ux_custom_tuning_button = button
        _sync_custom_tuning_button(app)
        profile_var = getattr(app, "profile_var", None)
        if profile_var is not None:
            profile_var.trace_add("write", lambda *_args: app.after_idle(lambda: _sync_custom_tuning_button(app)))
    except (tk.TclError, TypeError, ValueError):
        pass


def _sync_custom_tuning_button(app: Any) -> None:
    button = getattr(app, "_ux_custom_tuning_button", None)
    if button is None:
        return
    try:
        custom = bool(hasattr(app, "_profile_code") and app._profile_code() == "custom")
        button.configure(state="normal" if custom else "disabled")
    except (tk.TclError, Exception):
        pass


def _open_custom_tuning(app: Any) -> None:
    panel = getattr(app, "custom_settings_frame", None)
    if panel is None:
        return
    _show_feature_overlay(
        app,
        "custom",
        panel,
        780,
        lambda: _hide_feature_overlay(app, "custom"),
    )


def _escape(app: Any):
    if bool(getattr(app, "_gaming_settings_visible", False)):
        _set_settings_visible(app, False)
        return "break"
    for key in ("calibration", "custom"):
        if _overlay_state(app, key).get("visible"):
            _hide_feature_overlay(app, key)
            if key == "calibration":
                app._calibration_visible = False
            return "break"
    if bool(getattr(app, "_ux_library_overlay", False)):
        _hide_library(app)
        app._ux_library_user_open = False
        return "break"
    return None


def _finalize_app_ui(app: Any) -> None:
    _apply_accessible_styles(app)
    _fit_main_window(app)
    _ensure_songs_button(app)
    _hide_song_diagnostics(app)
    _add_custom_tuning_shortcut(app)

    # Tertiary copy stays short; normal users should not read implementation
    # details until they explicitly expand Details/Settings.
    for widget in _walk(app):
        text = _widget_text(widget)
        try:
            if text == "Find online MIDI ID":
                widget.configure(text="Browse MIDI IDs…")
            elif text == "BPSR Calibration Lab":
                widget.configure(text="Calibration…")
        except tk.TclError:
            pass

    try:
        app.bind("<Escape>", lambda _event: _escape(app), add="+")
        app.bind("<Configure>", lambda event: (
            _responsive_root(app, event.width) if event.widget is app else None
        ), add="+")
        body = getattr(app, "_gaming_body", None)
        if body is not None:
            body.bind("<Configure>", lambda _event: _responsive_root(app), add="+")
        metrics = getattr(app, "_product_metrics_frame", None)
        if metrics is not None:
            metrics.bind("<Configure>", lambda _event: _reflow_metric_cards(app), add="+")
        app.after_idle(lambda: _responsive_root(app))
    except tk.TclError:
        pass


def install_full_ui_overhaul(app_module: Any) -> None:
    """Install the final responsive/UI-priority layer for Lite and Studio."""
    if getattr(app_module, "_full_ui_overhaul_2026_installed", False):
        return
    _enable_per_monitor_dpi_awareness()
    _install_product_hooks()
    _install_feature_overlay_hooks()
    _install_studio_hooks()

    app_class = app_module.App
    original_build = app_class._build_ui

    def build_ui(self: Any) -> None:
        original_build(self)
        _finalize_app_ui(self)

    app_class._build_ui = build_ui
    app_module._full_ui_overhaul_2026_installed = True
