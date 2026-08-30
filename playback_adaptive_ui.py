from __future__ import annotations

from typing import Any

import midi_engine as me


def arrangement_impact_text(plan: Any) -> str:
    if plan is None:
        return "Source → BPSR: waiting for a song"
    source_notes = max(0, int(getattr(plan, "source_note_count", 0)))
    played_notes = max(0, int(getattr(plan, "note_count", 0)))
    source_chord = max(0, int(getattr(plan, "max_source_chord", 0)))
    planned_chord = max(0, int(getattr(plan, "max_planned_chord", 0)))
    source_low = me.midi_note_name(getattr(plan, "source_min_pitch", None))
    source_high = me.midi_note_name(getattr(plan, "source_max_pitch", None))
    planned_low = me.midi_note_name(getattr(plan, "planned_min_pitch", None))
    planned_high = me.midi_note_name(getattr(plan, "planned_max_pitch", None))
    remapped = max(0, int(getattr(plan, "remapped_notes", 0)))
    removed = max(
        0,
        int(getattr(plan, "chord_removed_notes", 0))
        + int(getattr(plan, "skipped_notes", 0))
        + int(getattr(plan, "retrigger_dropped_notes", 0)),
    )
    rapid = max(
        0,
        int(getattr(plan, "retrigger_compressed_notes", 0))
        + int(getattr(plan, "retrigger_merged_notes", 0))
        + int(getattr(plan, "retrigger_dropped_notes", 0)),
    )
    normalized = max(0, int(getattr(plan, "normalized_chords", 0)))
    priority = max(0, int(getattr(plan, "priority_evictions", 0)))
    extras: list[str] = []
    if remapped:
        extras.append(f"{remapped} remapped")
    if removed:
        extras.append(f"{removed} removed/thinned")
    if rapid:
        extras.append(f"{rapid} rapid-repeat edits")
    if normalized:
        extras.append(f"{normalized} chord attacks normalized")
    if priority:
        extras.append(f"{priority} melody-priority steals")
    suffix = " • " + " • ".join(extras) if extras else " • no destructive edits"
    return (
        f"Source {source_notes} notes / chord {source_chord} / {source_low}–{source_high}  →  "
        f"BPSR {played_notes} notes / chord {planned_chord} / {planned_low}–{planned_high}{suffix}"
    )


def _draw_impact(app: Any) -> None:
    canvas = getattr(app, "_adaptive_impact_canvas", None)
    if canvas is None:
        return
    try:
        canvas.delete("all")
        width = max(260, int(canvas.winfo_width()))
        height = max(30, int(canvas.winfo_height()))
        plan = getattr(app, "current_plan", None)
        if plan is None:
            canvas.create_text(
                8,
                height / 2,
                anchor="w",
                text="Choose a song to compare source complexity with the BPSR arrangement",
                fill="#9da7b3",
            )
            return
        source = max(1, int(getattr(plan, "source_note_count", 1)))
        played = max(0, int(getattr(plan, "note_count", 0)))
        source_chord = max(1, int(getattr(plan, "max_source_chord", 1)))
        planned_chord = max(0, int(getattr(plan, "max_planned_chord", 0)))

        label_w = 72
        bar_w = max(80, width - label_w - 12)
        source_fraction = 1.0
        played_fraction = min(1.0, played / source)
        chord_fraction = min(1.0, planned_chord / source_chord)
        canvas.create_text(4, 9, anchor="w", text="Notes", fill="#9da7b3")
        canvas.create_rectangle(label_w, 4, label_w + bar_w * source_fraction, 12, fill="#3a4654", outline="")
        canvas.create_rectangle(label_w, 4, label_w + bar_w * played_fraction, 12, fill="#58a6ff", outline="")
        canvas.create_text(4, 24, anchor="w", text="Chord", fill="#9da7b3")
        canvas.create_rectangle(label_w, 19, label_w + bar_w, 27, fill="#3a4654", outline="")
        canvas.create_rectangle(label_w, 19, label_w + bar_w * chord_fraction, 27, fill="#7ee787", outline="")
    except Exception:
        return


def install_adaptive_arranger_ui(app_module: Any) -> None:
    if getattr(app_module, "_adaptive_arranger_ui_installed", False):
        return
    app_class = app_module.App
    original_build_ui = app_class._build_ui
    original_analyze = app_class._analyze

    def build_ui(self: Any) -> None:
        original_build_ui(self)
        frame = getattr(self, "analysis_frame", None)
        if frame is None:
            return
        self._adaptive_impact_var = app_module.tk.StringVar(
            master=self,
            value="Source → BPSR: waiting for a song",
        )
        app_module.ttk.Separator(frame).pack(fill="x", pady=(8, 5))
        app_module.ttk.Label(
            frame,
            text="Arrangement impact",
            style="Gaming.Micro.TLabel",
        ).pack(anchor="w")
        app_module.ttk.Label(
            frame,
            textvariable=self._adaptive_impact_var,
            style="Hint.TLabel",
            wraplength=540,
            justify="left",
        ).pack(anchor="w", pady=(2, 2))
        self._adaptive_impact_canvas = app_module.tk.Canvas(
            frame,
            height=30,
            borderwidth=0,
            highlightthickness=0,
            background="#171b22",
        )
        self._adaptive_impact_canvas.pack(fill="x")
        self._adaptive_impact_canvas.bind(
            "<Configure>",
            lambda _event: _draw_impact(self),
            add="+",
        )

    def analyze(self: Any) -> None:
        original_analyze(self)
        if hasattr(self, "_adaptive_impact_var"):
            self._adaptive_impact_var.set(arrangement_impact_text(getattr(self, "current_plan", None)))
            _draw_impact(self)

    app_class._build_ui = build_ui
    app_class._analyze = analyze
    app_module._adaptive_arranger_ui_installed = True
