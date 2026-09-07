from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from studio_band_ui import BandAudioTab


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _sync_quality(tab):
    tab.quality.set("HQ" if bool(tab.deep_separation.get()) else "Standard")


def _patch_main_ui():
    original_init = BandAudioTab.__init__
    if getattr(original_init, "_bpsr_fast_precision", False):
        return

    def init(self, app):
        # Advanced has already been installed by the launcher before any tab is
        # constructed. Wrap it before original_init binds the Advanced button,
        # otherwise Tk would keep the old bound method forever.
        _patch_advanced_ui()
        original_init(self, app)
        self.deep_separation = tk.BooleanVar(app, value=False)
        self.quality.set("Standard")
        quality_label = None
        quality_combo = None
        for widget in _walk(self.workspace):
            try:
                if isinstance(widget, ttk.Label) and str(widget.cget("text")) == "Stem Quality":
                    quality_label = widget
                elif isinstance(widget, ttk.Combobox) and str(widget.cget("textvariable")) == str(self.quality):
                    quality_combo = widget
            except tk.TclError:
                continue
        if quality_label is not None:
            parent = quality_label.master
            info = quality_label.grid_info()
            quality_label.grid_remove()
            if quality_combo is not None:
                quality_combo.grid_remove()
            self.fast_separation_label = ttk.Label(
                parent,
                text="Separation: Auto (fast)",
                style="Hint.TLabel",
            )
            self.fast_separation_label.grid(
                row=int(info.get("row", 0)),
                column=int(info.get("column", 2)),
                columnspan=2,
                sticky="w",
                padx=(0, 6),
            )

    init._bpsr_fast_precision = True
    BandAudioTab.__init__ = init

    original_convert = BandAudioTab.convert

    def convert(self):
        _sync_quality(self)
        return original_convert(self)

    BandAudioTab.convert = convert


def _patch_advanced_ui():
    original = BandAudioTab.advanced
    if getattr(original, "_bpsr_fast_precision", False):
        return

    def advanced(self):
        result = original(self)
        windows = []
        for child in self.workspace.winfo_children():
            if isinstance(child, tk.Toplevel):
                try:
                    if child.winfo_exists() and child.title() == "Audio → Band · Model setup":
                        windows.append(child)
                except tk.TclError:
                    pass
        if not windows:
            return result
        window = windows[-1]
        basics = None
        footer = None
        for widget in _walk(window):
            try:
                text = str(widget.cget("text"))
            except (tk.TclError, AttributeError):
                continue
            if isinstance(widget, ttk.LabelFrame) and text == "1 · Recommended settings":
                basics = widget
            elif isinstance(widget, ttk.Label) and text.startswith("Suggested normal setup:"):
                footer = widget
            elif isinstance(widget, ttk.Checkbutton) and "Extra quality cross-check" in text:
                widget.configure(
                    text="Deep diagnostic model review (very slow; normally OFF)"
                )
        if basics is not None:
            rows = [
                int(child.grid_info().get("row", 0))
                for child in basics.winfo_children()
                if child.winfo_manager() == "grid"
            ]
            row = max(rows, default=5) + 1
            ttk.Checkbutton(
                basics,
                text="Deep separation (experimental full-song HQ; usually several× slower)",
                variable=self.deep_separation,
                command=lambda: _sync_quality(self),
            ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 2))
            ttk.Label(
                basics,
                text=(
                    "Normal conversion always uses the fast Demucs path plus automatic targeted "
                    "wrong-note review. Deep separation keeps BS-RoFormer available only for "
                    "difficult recordings/debugging; it is not expected to fix transcription "
                    "hallucinations by itself."
                ),
                style="Hint.TLabel",
                justify="left",
                wraplength=720,
            ).grid(row=row + 1, column=0, columnspan=2, sticky="w", pady=(0, 4))
        if footer is not None:
            footer.configure(
                text=(
                    "Recommended: Device Auto · fast separation · automatic setup ON · deep diagnostic review OFF. "
                    "The normal path automatically checks only suspicious Piano/Guitar notes; full-song HQ and "
                    "heavy multi-model review are retained only as diagnostics."
                )
            )
        return result

    advanced._bpsr_fast_precision = True
    BandAudioTab.advanced = advanced


def _patch_setup_policy() -> None:
    import studio_band_advanced_setup as setup

    if "hq" in setup._COMPONENTS:
        setup._COMPONENTS["hq"] = (
            "Deep separation",
            "Full-song BS-RoFormer separation; retained for difficult recordings/debugging",
            "Diagnostic",
        )
    if "guitar_review" in setup._COMPONENTS:
        setup._COMPONENTS["guitar_review"] = (
            "Targeted guitar verifier",
            "Six-fold GuitarSet reviewer on suspicious note neighborhoods only",
            "Targeted",
        )

    original_plan = setup._recommended_plan
    if not getattr(original_plan, "_bpsr_fast_precision", False):
        def recommended_plan(tab, hardware):
            plan = list(original_plan(tab, hardware))
            deep = bool(getattr(tab, "deep_separation", None) and tab.deep_separation.get())
            if not deep:
                plan = [name for name in plan if name != "hq"]
            if hardware.cuda and "guitar_review" in setup.RUNTIMES and "guitar_review" not in plan:
                plan.append("guitar_review")
            return list(dict.fromkeys(plan))
        recommended_plan._bpsr_fast_precision = True
        setup._recommended_plan = recommended_plan

    original_status = setup._component_status
    if not getattr(original_status, "_bpsr_fast_precision", False):
        def component_status(tab, key, hardware):
            if key == "hq" and not bool(getattr(tab, "deep_separation", None) and tab.deep_separation.get()):
                return "Diagnostic"
            if key == "guitar_review":
                if not hardware.cuda:
                    return "CUDA preferred"
                return "Ready" if tab.pipeline.runtimes.available(key, device="cuda") else "Needs setup"
            return original_status(tab, key, hardware)
        component_status._bpsr_fast_precision = True
        setup._component_status = component_status

    def performance_guide(tab, hardware):
        device = setup._effective_device(tab, hardware)
        deep = bool(getattr(tab, "deep_separation", None) and tab.deep_separation.get())
        diagnostic = bool(tab.cross_check.get())
        if device == "cuda":
            if diagnostic:
                time_text = (
                    "Deep diagnostic review can take tens of minutes because it may load MR-MT3, "
                    "Aria, YourMT3+ and high-VRAM ownership models. Leave it OFF for normal use."
                )
            elif deep:
                time_text = (
                    "Deep separation runs full-song BS-RoFormer and can take several times longer than "
                    "the normal fast path. Use it only when the recording has unusually severe stem bleed."
                )
            else:
                time_text = (
                    "Normal mode uses fast Demucs separation. Extra wrong-note work is targeted: the "
                    "guitar verifier sees at most 12 seconds of candidate neighborhoods, Aria at most "
                    "8 seconds when already installed, and YourMT3+ at most 6 seconds when already installed."
                )
            mega = (
                "Mega53 is available only inside Deep diagnostic review."
                if hardware.vram_gb >= 14.0 else
                "Mega53 remains disabled because it requires at least 14 GB VRAM."
            )
            pc_text = (
                f"GPU: {hardware.vram_gb:.1f} GB VRAM detected. NVIDIA CUDA is recommended. {mega} "
                "16 GB system RAM is the practical normal target; 24–32 GB gives more headroom for diagnostics."
            )
        else:
            time_text = (
                "CPU mode keeps the same precision sieve but skips CUDA-only specialist reviewers. "
                "It can be much slower than NVIDIA CUDA even though full-song HQ is no longer automatic."
            )
            pc_text = (
                "No usable NVIDIA CUDA device detected. Core conversion still works on CPU. "
                "16 GB system RAM is recommended for normal use."
            )
        note = (
            "Planning guidance only. First use may still take longer while runtimes/models download. "
            "Normal conversion never auto-runs full-song HQ or the deep multi-model diagnostic stack."
        )
        return time_text, pc_text, note

    setup._performance_guide = performance_guide


def install_fast_precision_ui() -> None:
    _patch_main_ui()
    _patch_setup_policy()
