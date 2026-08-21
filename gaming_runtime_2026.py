from __future__ import annotations

import time
import tkinter as tk
from typing import Any

import gaming_ui_2026 as gaming
import modern_ui
from player import MidiPlayer


VISUALIZER_FPS = 30
VISUALIZER_FRAME_MS = round(1000 / VISUALIZER_FPS)


def _pause_aware_wait(self: MidiPlayer, target: float) -> bool:
    """Wake immediately when Pause is requested instead of waiting for the next MIDI event."""
    while not self.stop_event.is_set():
        if self.pause_event.is_set():
            return False
        remaining = target - time.perf_counter()
        if remaining <= 0:
            return True
        if remaining > 0.010:
            self.stop_event.wait(min(max(remaining - 0.004, 0.001), 0.050))
        else:
            time.sleep(min(remaining, 0.001))
    return False


def _set_library_visible(app: Any, visible: bool) -> None:
    panel = getattr(app, "_gaming_library_panel", None)
    body = getattr(app, "_gaming_body", None)
    if panel is None or body is None:
        return
    if visible:
        panel.grid()
        body.columnconfigure(0, minsize=330)
        try:
            import online_ui

            online_ui._schedule_source_notebook_resize(app)
        except Exception:
            pass
    else:
        panel.grid_remove()
        body.columnconfigure(0, minsize=0)
    app._gaming_library_visible = visible


def _set_settings_visible(app: Any, visible: bool) -> None:
    panel = getattr(app, "_gaming_settings_panel", None)
    body = getattr(app, "_gaming_body", None)
    if panel is None or body is None:
        return
    if visible:
        panel.grid()
        body.columnconfigure(2, minsize=255)
    else:
        panel.grid_remove()
        body.columnconfigure(2, minsize=0)
    app._gaming_settings_visible = visible


def _toggle_library(app: Any) -> None:
    _set_library_visible(app, not bool(getattr(app, "_gaming_library_visible", True)))


def _toggle_settings(app: Any) -> None:
    _set_settings_visible(app, not bool(getattr(app, "_gaming_settings_visible", True)))


def _responsive_layout(app: Any, width: int) -> None:
    if width < 790:
        if getattr(app, "_gaming_settings_visible", True):
            _set_settings_visible(app, False)
        if getattr(app, "_gaming_library_visible", True):
            _set_library_visible(app, False)
    elif width < 1030 and getattr(app, "_gaming_settings_visible", True):
        _set_settings_visible(app, False)


def _render_visualizer(app: Any) -> None:
    """Render the prepared BPSR event stream at a capped 30 FPS."""
    canvas = getattr(app, "midi_visualizer", None)
    if canvas is None:
        return
    try:
        width = max(10, canvas.winfo_width())
        height = max(10, canvas.winfo_height())
        palette = gaming._visualizer_colors(app)
        canvas.configure(background=palette["bg"])
        canvas.delete("all")

        plan = getattr(app, "current_plan", None)
        plan_id = id(plan) if plan is not None else None
        if plan_id != getattr(app, "_gaming_visual_plan_id", None):
            app._gaming_visual_plan_id = plan_id
            app._gaming_note_spans = gaming._build_note_spans(plan) if plan is not None else {}

        lane_count = len(gaming.KEY_LANES)
        lane_w = width / lane_count
        for index in range(lane_count + 1):
            x = index * lane_w
            canvas.create_line(x, 0, x, height, fill=palette["grid"])

        now = float(getattr(app.player, "position", 0.0)) if app.player.is_playing else 0.0
        lookahead = 5.0
        current_y = height - 34
        spans = getattr(app, "_gaming_note_spans", {})
        for lane_index, key in enumerate(gaming.KEY_LANES):
            x1 = lane_index * lane_w + 1
            x2 = (lane_index + 1) * lane_w - 1
            for start, end in spans.get(key, ()):
                if end < now - 0.15 or start > now + lookahead:
                    continue
                y_start = current_y - ((start - now) / lookahead) * max(1, current_y - 8)
                y_end = current_y - ((end - now) / lookahead) * max(1, current_y - 8)
                canvas.create_rectangle(
                    x1,
                    min(y_start, y_end),
                    x2,
                    max(y_start, y_end),
                    fill=palette["note"],
                    outline="",
                )

        active_keys = tuple(app.player.active_keys)
        for key in active_keys:
            if key not in gaming.KEY_LANES:
                continue
            lane_index = gaming.KEY_LANES.index(key)
            canvas.create_rectangle(
                lane_index * lane_w + 1,
                current_y,
                (lane_index + 1) * lane_w - 1,
                height,
                fill=palette["active"],
                outline="",
            )

        canvas.create_line(0, current_y, width, current_y, fill=palette["line"], width=2)
        if plan is None:
            canvas.create_text(
                width / 2,
                height / 2,
                text="Choose a song to preview the BPSR note stream",
                fill=palette["text"],
                font=("Segoe UI Variable Text", 11),
            )
        elif not app.player.is_playing:
            canvas.create_text(
                12,
                12,
                anchor="nw",
                text="5-second note preview",
                fill=palette["text"],
                font=("Segoe UI Variable Text", 8),
            )

        app._gaming_active_keys_var.set("  ".join(key.upper() for key in active_keys[:12]) if active_keys else "—")
        app._gaming_activity_var.set(min(100, len(active_keys) * 18))
        if plan is None:
            app._gaming_router_var.set("Auto router • waiting for a song")
        else:
            percussion = "drums ignored" if bool(app.percussion_var.get()) else "drums included"
            app._gaming_router_var.set(
                f"Auto router • {plan.source_track_count} track(s) • {percussion} • max chord {plan.max_planned_chord}"
            )
    except (tk.TclError, AttributeError, TypeError, ValueError):
        pass
    try:
        app.after(VISUALIZER_FRAME_MS, lambda: _render_visualizer(app))
    except tk.TclError:
        pass


def install_gaming_runtime_2026(app_module: Any) -> None:
    """Install runtime polish after all source-specific UI integrations are layered."""
    app_class = app_module.App
    if getattr(app_class, "_gaming_runtime_2026_installed", False):
        return

    MidiPlayer._wait_until = _pause_aware_wait
    gaming._toggle_library = _toggle_library
    gaming._toggle_settings = _toggle_settings
    gaming._responsive_layout = _responsive_layout
    gaming._render_visualizer = _render_visualizer

    original_build = app_class._build_ui

    def build_ui(self: Any) -> None:
        original_build(self)
        # Preserve the v3 local-folder watcher. It intentionally sleeps while an
        # online source is active and resumes as soon as Local is selected.
        self.after(1500, lambda: modern_ui._poll_song_library(self))

    app_class._build_ui = build_ui
    app_class._gaming_runtime_2026_installed = True
