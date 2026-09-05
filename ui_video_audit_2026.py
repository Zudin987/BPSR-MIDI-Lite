from __future__ import annotations

import ctypes
import os
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

import ui_full_overhaul_2026 as full_ui


# Final pass driven by a full 77.8 s / 2,334-frame desktop recording.  Keep this
# layer last: it fixes composition defects created by otherwise-correct feature
# patches without changing playback, networking or Audio -> Band inference.
_LIBRARY_TAB_NAMES = {
    "Local": "Local",
    "Online Sequencer": "Online",
    "Bookmarks": "Saved",
    "YouTube": "YouTube",
    "Audio → Band": "Audio",
}
_FOCUS_KEYS = ("settings", "custom", "calibration", "band")


def _children(widget: Any) -> tuple[Any, ...]:
    try:
        return tuple(widget.winfo_children())
    except (AttributeError, tk.TclError):
        return ()


def _widget_text(widget: Any) -> str:
    try:
        return str(widget.cget("text"))
    except (AttributeError, TypeError, tk.TclError):
        return ""


def _hide_widget(widget: Any) -> None:
    try:
        manager = str(widget.winfo_manager())
        if manager == "grid":
            widget.grid_remove()
        elif manager == "pack":
            widget.pack_forget()
        elif manager == "place":
            widget.place_forget()
    except (AttributeError, tk.TclError):
        pass


def _stash_siblings(panel: Any) -> list[tuple[Any, str, dict[str, Any]]]:
    saved: list[tuple[Any, str, dict[str, Any]]] = []
    master = getattr(panel, "master", None)
    if master is None:
        return saved
    for sibling in _children(master):
        if sibling is panel:
            continue
        try:
            manager = str(sibling.winfo_manager())
            if not manager:
                continue
            if manager == "grid":
                info = dict(sibling.grid_info())
                info.pop("in", None)
                sibling.grid_remove()
            elif manager == "pack":
                info = dict(sibling.pack_info())
                info.pop("in", None)
                sibling.pack_forget()
            elif manager == "place":
                info = dict(sibling.place_info())
                info.pop("in", None)
                sibling.place_forget()
            else:
                continue
            saved.append((sibling, manager, info))
        except (AttributeError, tk.TclError):
            pass
    return saved


def _restore_siblings(saved: list[tuple[Any, str, dict[str, Any]]]) -> None:
    for widget, manager, info in saved:
        try:
            if not widget.winfo_exists():
                continue
            if manager == "grid":
                # grid_remove() retains the canonical options. Calling grid()
                # avoids replaying stale row/column values after a responsive
                # reflow occurred while the focused surface was open.
                widget.grid()
            elif manager == "pack":
                widget.pack(**info)
            elif manager == "place":
                widget.place(**info)
        except (AttributeError, tk.TclError):
            pass


def _focus_geometry(app: Any, key: str) -> tuple[int, int, int, int]:
    state = full_ui._overlay_state(app, key)
    panel = state.get("panel")
    master = getattr(panel, "master", None) if panel is not None else None
    if panel is None or master is None:
        return 0, 0, 0, 0
    master_width, master_height = full_ui._safe_dimensions(master)
    max_width = int(state.get("max_width", 820))
    width = min(max_width, max(300, master_width - 18))
    try:
        panel.update_idletasks()
        requested = max(1, int(panel.winfo_reqheight()) + 16)
    except (tk.TclError, TypeError, ValueError):
        requested = master_height
    viewport = max(180, master_height - 18)
    maximum = max(0, requested - viewport)
    offset = max(0, min(int(state.get("offset", 0)), maximum))
    state["offset"] = offset
    return width, requested, viewport, maximum


def _focus_widgets(app: Any, key: str) -> tuple[Any | None, Any | None]:
    state = full_ui._overlay_state(app, key)
    panel = state.get("panel")
    master = getattr(panel, "master", None) if panel is not None else None
    if master is None:
        return None, None
    scrollbar = state.get("video_scrollbar")
    close_button = state.get("video_close_button")
    try:
        if scrollbar is None or scrollbar.master is not master:
            if scrollbar is not None:
                _hide_widget(scrollbar)
            scrollbar = ttk.Scrollbar(
                master,
                orient="vertical",
                command=lambda *args: _focus_scroll(app, key, *args),
            )
            state["video_scrollbar"] = scrollbar
        if close_button is None or close_button.master is not master:
            if close_button is not None:
                _hide_widget(close_button)
            close_button = ttk.Button(master, text="Close", command=state.get("close"))
            state["video_close_button"] = close_button
    except tk.TclError:
        return None, None
    return scrollbar, close_button


def _refresh_focus(app: Any, key: str) -> None:
    state = full_ui._overlay_state(app, key)
    if not state.get("visible"):
        return
    panel = state.get("panel")
    master = getattr(panel, "master", None) if panel is not None else None
    if panel is None or master is None:
        return
    width, requested, viewport, maximum = _focus_geometry(app, key)
    offset = int(state.get("offset", 0))
    placed_height = max(requested, viewport)
    try:
        panel.grid_remove()
        panel.place_forget()
        panel.place(relx=0.5, y=9 - offset, anchor="n", width=width, height=placed_height)
        panel.lift()
    except tk.TclError:
        return

    # The old generic overlay put Close/scroll controls in _gaming_body while
    # the feature panel itself is usually a child of _product_center.  That is
    # why the recording showed Close detached from the panel and content leaking
    # underneath it.  Keep all overlay chrome in the same coordinate system.
    old_close = state.get("close_button")
    old_scroll = state.get("scrollbar")
    if old_close is not None:
        _hide_widget(old_close)
    if old_scroll is not None:
        _hide_widget(old_scroll)

    scrollbar, close_button = _focus_widgets(app, key)
    if close_button is not None:
        try:
            close_button.configure(command=state.get("close"))
            close_button.place(relx=0.5, x=width // 2 - 8, y=15, anchor="ne")
            close_button.lift()
        except tk.TclError:
            pass
    if scrollbar is not None:
        if maximum > 0:
            try:
                scrollbar.place(
                    relx=0.5,
                    x=width // 2 - 2,
                    y=52,
                    anchor="ne",
                    height=max(72, viewport - 58),
                )
                first = offset / max(1, requested)
                last = min(1.0, (offset + viewport) / max(1, requested))
                scrollbar.set(first, last)
                scrollbar.lift()
            except tk.TclError:
                pass
        else:
            _hide_widget(scrollbar)


def _focus_scroll(app: Any, key: str, *args: str) -> None:
    state = full_ui._overlay_state(app, key)
    if not state.get("visible"):
        return
    _width, _requested, viewport, maximum = _focus_geometry(app, key)
    offset = int(state.get("offset", 0))
    if args and args[0] == "moveto" and len(args) >= 2:
        offset = int(float(args[1]) * maximum)
    elif args and args[0] == "scroll" and len(args) >= 3:
        amount = int(args[1])
        unit = 48 if args[2] == "units" else max(90, viewport - 90)
        offset += amount * unit
    state["offset"] = max(0, min(offset, maximum))
    _refresh_focus(app, key)


def _focus_wheel(app: Any, key: str, event: Any):
    state = full_ui._overlay_state(app, key)
    if not state.get("visible"):
        return None
    steps = full_ui._wheel_steps(event)
    if not steps:
        return None
    _focus_scroll(app, key, "scroll", str(steps), "units")
    return "break"


def _hide_focus(app: Any, key: str) -> None:
    state = full_ui._overlay_state(app, key)
    panel = state.get("panel")
    if panel is not None:
        try:
            panel.grid_remove()
            panel.place_forget()
        except tk.TclError:
            pass
    for name in ("scrollbar", "close_button", "video_scrollbar", "video_close_button"):
        widget = state.get(name)
        if widget is not None:
            _hide_widget(widget)
    saved = state.pop("video_siblings", [])
    _restore_siblings(saved)
    state["visible"] = False
    state["offset"] = 0
    if key == "settings":
        app._gaming_settings_visible = False
    if getattr(app, "_ux_active_focus_overlay", None) == key:
        app._ux_active_focus_overlay = None
    try:
        app.after_idle(lambda: full_ui._responsive_root(app))
    except tk.TclError:
        pass


def _show_focus(
    app: Any,
    key: str,
    panel: Any,
    max_width: int,
    close: Callable[[], None],
) -> None:
    if panel is None:
        return
    active = getattr(app, "_ux_active_focus_overlay", None)
    if active and active != key:
        _hide_focus(app, active)
    for other in _FOCUS_KEYS:
        if other != key and full_ui._overlay_state(app, other).get("visible"):
            _hide_focus(app, other)
    state = full_ui._overlay_state(app, key)
    if not state.get("visible"):
        state["video_siblings"] = _stash_siblings(panel)
    state.update(
        {
            "panel": panel,
            "max_width": max_width,
            "close": close,
            "offset": 0,
            "visible": True,
        }
    )
    if key == "settings":
        app._gaming_settings_visible = True
    app._ux_active_focus_overlay = key
    full_ui._bind_wheel_tree(panel, lambda event: _focus_wheel(app, key, event))
    _refresh_focus(app, key)
    try:
        app.after_idle(lambda: _refresh_focus(app, key))
    except tk.TclError:
        pass


def _set_settings_focus(app: Any, visible: bool) -> None:
    panel = getattr(app, "_gaming_settings_panel", None)
    if panel is None:
        return
    if not visible:
        _hide_focus(app, "settings")
        return
    _show_focus(
        app,
        "settings",
        panel,
        680,
        lambda: _set_settings_focus(app, False),
    )


def _polish_library_tabs(app: Any, width: int) -> None:
    notebook = getattr(app, "song_source_notebook", None)
    if notebook is None:
        return
    try:
        style = getattr(app, "_style", ttk.Style(app))
        style.configure("Library.TNotebook.Tab", padding=(5, 5))
        notebook.configure(style="Library.TNotebook")
        count = int(notebook.index("end"))
        for index in range(count):
            current = str(notebook.tab(index, "text"))
            # Once compacted, keep recognizing the compact names too.
            reverse = {
                "Online": "Online",
                "Saved": "Saved",
                "YT": "YouTube",
                "Audio": "Audio",
                "Local": "Local",
            }
            target = _LIBRARY_TAB_NAMES.get(current, reverse.get(current, current))
            if target == "YouTube" and width < 315:
                target = "YT"
            notebook.tab(index, text=target)
    except (tk.TclError, TypeError, ValueError):
        pass


def _polish_library_copy(app: Any, width: int) -> None:
    panel = getattr(app, "_gaming_library_panel", None)
    if panel is None:
        return
    for widget in full_ui._walk(panel):
        if widget.winfo_class() != "TLabel":
            continue
        text = _widget_text(widget)
        try:
            if text.startswith("Local files stay on disk."):
                widget.configure(
                    text="Local stays on this PC. Online uses cache. Save to Local keeps a permanent MIDI.",
                    wraplength=max(190, width - 28),
                    justify="left",
                )
            elif text.startswith("Turn a song into Piano, Guitar, Bass and Drums"):
                widget.configure(
                    text="Create Piano, Guitar, Bass and Drums from audio.",
                    wraplength=max(190, width - 28),
                    justify="left",
                )
            elif text.startswith("Choose or drop a song to create four playable"):
                widget.configure(
                    text="Choose local audio or search for a song in the full workspace.",
                    wraplength=max(190, width - 28),
                    justify="left",
                )
        except tk.TclError:
            pass


def _sync_library_tables(app: Any, width: int) -> None:
    # The recording showed Changes/Playable text truncated even at 1600x900,
    # because the Library itself intentionally stays narrow.  Song Check already
    # owns the detailed transformation metrics, so the chooser only needs Song +
    # BPSR fit (and Playable when there is genuinely enough room).
    for name in ("online_tree", "bookmark_tree"):
        tree = getattr(app, name, None)
        if tree is None:
            continue
        try:
            display = ("fit", "notes") if width >= 340 else ("fit",)
            tree.configure(displaycolumns=display)
            reserve = 150 if len(display) == 2 else 82
            tree.column("#0", width=max(138, width - reserve - 20), minwidth=120, stretch=True)
            tree.column("fit", width=72, minwidth=64, stretch=False, anchor="center")
            tree.column("notes", width=64, minwidth=56, stretch=False, anchor="e")
        except (tk.TclError, KeyError):
            pass

    youtube = getattr(app, "youtube_tree", None)
    if youtube is not None:
        try:
            youtube.configure(displaycolumns=("duration",))
            youtube.column("#0", width=max(150, width - 92), minwidth=130, stretch=True)
            youtube.column("duration", width=62, minwidth=56, stretch=False, anchor="center")
        except (tk.TclError, KeyError):
            pass

    _polish_library_tabs(app, width)
    _polish_library_copy(app, width)
    variable = getattr(app, "online_status_var", None)
    if variable is not None:
        target = str(variable)
        for widget in full_ui._walk(getattr(app, "_gaming_library_panel", app)):
            try:
                if widget.winfo_class() == "TLabel" and str(widget.cget("textvariable")) == target:
                    widget.configure(wraplength=max(180, width - 28), justify="left")
            except (tk.TclError, TypeError):
                pass
    try:
        import online_ui

        online_ui._schedule_source_notebook_resize(app)
    except Exception:
        pass


def _dark_titlebar(window: Any) -> None:
    if os.name != "nt":
        return
    try:
        window.update_idletasks()
        hwnd = int(window.winfo_id())
        wrapper = int(ctypes.windll.user32.GetParent(hwnd) or hwnd)
        value = ctypes.c_int(1)
        # DWMWA_USE_IMMERSIVE_DARK_MODE is 20 on current Windows 10/11 and was
        # 19 on earlier builds.  Trying both is harmless and avoids a bright
        # native title bar over an otherwise-dark Studio workspace.
        for attribute in (20, 19):
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    wrapper,
                    attribute,
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )
            except (AttributeError, OSError):
                pass
    except (AttributeError, OSError, tk.TclError, TypeError, ValueError):
        pass


def _fit_audio_tables(owner: Any, _event: Any = None) -> None:
    source_parent = owner.source_tree.master
    try:
        width = max(320, int(source_parent.winfo_width()) - 18)
    except (tk.TclError, TypeError, ValueError):
        width = 900
    if width >= 700:
        provider = 92
        artist = max(140, int((width - provider) * 0.30))
        track = max(210, width - provider - artist - 16)
        try:
            owner.source_tree.column("#0", width=track, minwidth=170, stretch=True)
            owner.source_tree.column("artist", width=artist, minwidth=120, stretch=True)
            for name in ("provider", "source"):
                if name in tuple(str(value) for value in owner.source_tree.cget("columns")):
                    owner.source_tree.column(name, width=provider, minwidth=78, stretch=False)
            hscroll = getattr(owner, "source_hscrollbar", None)
            if hscroll is not None:
                hscroll.grid_remove()
        except (tk.TclError, TypeError):
            pass
    else:
        hscroll = getattr(owner, "source_hscrollbar", None)
        if hscroll is not None:
            try:
                hscroll.grid()
            except tk.TclError:
                pass

    summary = owner.summary
    try:
        summary_width = max(360, int(summary.master.winfo_width()) - 18)
    except (tk.TclError, TypeError, ValueError):
        summary_width = 900
    if summary_width >= 760:
        names = ("notes", "melody", "rejected", "simplified", "shifted")
        part_width = 90
        each = max(82, int((summary_width - part_width - 16) / len(names)))
        try:
            summary.column("#0", width=part_width, minwidth=76, stretch=True)
            for name in names:
                summary.column(name, width=each, minwidth=70, stretch=True, anchor="center")
            hscroll = getattr(owner, "summary_hscrollbar", None)
            if hscroll is not None:
                hscroll.grid_remove()
        except tk.TclError:
            pass
    else:
        hscroll = getattr(owner, "summary_hscrollbar", None)
        if hscroll is not None:
            try:
                hscroll.grid()
            except tk.TclError:
                pass


def _polish_audio_workspace(owner: Any) -> None:
    try:
        owner.workspace.title("Audio → Band")
        owner.workspace.transient(owner.app)
    except tk.TclError:
        pass

    source = getattr(getattr(owner, "manual_button", None), "master", None)
    source = getattr(source, "master", None)
    if source is not None:
        try:
            source.configure(text="1. Choose audio")
        except tk.TclError:
            pass

    body = getattr(getattr(owner, "summary", None), "master", None)
    if body is not None:
        for widget in _children(body):
            text = _widget_text(widget)
            try:
                if text == "Main Melody":
                    widget.configure(text="Melody")
                elif text == "Stem Quality":
                    widget.configure(text="Separation")
            except tk.TclError:
                pass

    try:
        owner.source_tree.configure(height=5)
        owner.summary.configure(height=4)
        owner.bar.stop()
        owner.bar.configure(mode="determinate", value=0)
    except tk.TclError:
        pass

    for frame in (owner.source_tree.master, owner.summary.master):
        try:
            frame.bind("<Configure>", lambda event, owner=owner: _fit_audio_tables(owner, event), add="+")
        except tk.TclError:
            pass
    try:
        owner.workspace.after_idle(lambda: _fit_audio_tables(owner))
        owner.workspace.after_idle(lambda: _dark_titlebar(owner.workspace))
    except tk.TclError:
        pass


def _install_audio_workspace_patch() -> None:
    try:
        import studio_band_ui
    except Exception:
        return

    original_fit = studio_band_ui._fit_toplevel

    def fit_toplevel(window, preferred_width, preferred_height, minimum_width=640, minimum_height=480):
        geometry = original_fit(window, preferred_width, preferred_height, minimum_width, minimum_height)
        try:
            window.after_idle(lambda: _dark_titlebar(window) if window.winfo_exists() else None)
        except tk.TclError:
            pass
        return geometry

    studio_band_ui._fit_toplevel = fit_toplevel

    cls = studio_band_ui.BandAudioTab
    if getattr(cls, "_video_audit_ux_installed", False):
        return
    original_init = cls.__init__
    original_open = cls.open_workspace
    original_start = cls.start
    original_poll = cls.poll

    def init(self, app):
        original_init(self, app)
        _polish_audio_workspace(self)

    def open_workspace(self):
        original_open(self)
        try:
            self.workspace.update_idletasks()
            sw = max(640, int(self.workspace.winfo_screenwidth()))
            sh = max(480, int(self.workspace.winfo_screenheight()))
            width = min(1240, max(640, sw - 80))
            height = min(840, max(480, sh - 110))
            x = max(0, (sw - width) // 2)
            y = max(0, (sh - height) // 3)
            self.workspace.geometry(f"{width}x{height}+{x}+{y}")
            self.workspace.minsize(min(640, width), min(480, height))
            self.workspace.after_idle(lambda: (_fit_audio_tables(self), _dark_titlebar(self.workspace)))
        except (tk.TclError, TypeError, ValueError):
            pass

    def start(self, action, success_kind="done", task="conversion"):
        try:
            self.bar.configure(mode="indeterminate", value=0)
        except tk.TclError:
            pass
        return original_start(self, action, success_kind, task)

    def poll(self):
        result = original_poll(self)
        if not getattr(self, "busy", False):
            try:
                self.bar.stop()
                self.bar.configure(mode="determinate", value=0)
            except tk.TclError:
                pass
        return result

    cls.__init__ = init
    cls.open_workspace = open_workspace
    cls.start = start
    cls.poll = poll
    cls._video_audit_ux_installed = True


def install_video_audit_ui() -> None:
    """Apply the final human-recording UI audit without touching product logic."""
    if getattr(full_ui, "_video_audit_ui_installed", False):
        return

    original_sync_library = full_ui._sync_library_tables
    original_root = full_ui._responsive_root
    original_finalize = full_ui._finalize_app_ui

    def sync_library(app: Any, width: int) -> None:
        # Preserve status wrapping/source-notebook refresh from the previous layer,
        # then apply the deliberately simpler sidebar table contract.
        original_sync_library(app, width)
        _sync_library_tables(app, width)

    def responsive_root(app: Any, width: int | None = None) -> None:
        settings_active = full_ui._overlay_state(app, "settings").get("visible", False)
        if settings_active:
            # The older responsive root automatically closed the right drawer at
            # <720 px. Settings is now a focused full-width surface and should
            # stay open at compact resolutions.
            app._gaming_settings_visible = False
        original_root(app, width)
        if settings_active:
            app._gaming_settings_visible = True
        panel = getattr(app, "_gaming_library_panel", None)
        if panel is not None:
            try:
                _sync_library_tables(app, max(230, int(panel.winfo_width())))
            except (tk.TclError, TypeError, ValueError):
                pass
        active = getattr(app, "_ux_active_focus_overlay", None)
        if active and full_ui._overlay_state(app, active).get("visible"):
            # A Configure callback can remap a sibling that was intentionally
            # hidden while a focused workflow is open. Keep the focus surface
            # exclusive and refresh its geometry after the parent settles.
            for sibling, _manager, _info in full_ui._overlay_state(app, active).get("video_siblings", []):
                _hide_widget(sibling)
            _refresh_focus(app, active)

    def finalize(app: Any) -> None:
        original_finalize(app)
        panel = getattr(app, "_gaming_library_panel", None)
        width = 300
        if panel is not None:
            try:
                width = max(230, int(panel.winfo_width()))
            except (tk.TclError, TypeError, ValueError):
                pass
        _sync_library_tables(app, width)

    full_ui._sync_library_tables = sync_library
    full_ui._overlay_geometry = _focus_geometry
    full_ui._refresh_feature_overlay = _refresh_focus
    full_ui._overlay_scroll_command = _focus_scroll
    full_ui._overlay_wheel = _focus_wheel
    full_ui._hide_feature_overlay = _hide_focus
    full_ui._show_feature_overlay = _show_focus
    full_ui._set_settings_visible = _set_settings_focus
    full_ui._refresh_settings_position = lambda app: _refresh_focus(app, "settings")
    full_ui._settings_scroll_command = lambda app, *args: _focus_scroll(app, "settings", *args)
    full_ui._settings_wheel = lambda app, event: _focus_wheel(app, "settings", event)
    full_ui._responsive_root = responsive_root
    full_ui._finalize_app_ui = finalize

    # Some older modules retained direct references to the pre-overhaul drawer
    # helper. Point them at the focused Settings surface as well.
    try:
        import gaming_runtime_2026 as gaming_runtime
        import ui_product_overhaul_v34 as product

        gaming_runtime._set_settings_visible = _set_settings_focus
        product._set_settings_drawer_visible = _set_settings_focus
    except Exception:
        pass

    _install_audio_workspace_patch()
    full_ui._video_audit_ui_installed = True
