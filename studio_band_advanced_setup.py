"""Clear model-setup experience for Audio -> Band Advanced.

The original Advanced page exposed internal runtime names and made optional ADTOF
look like a broken required drum component. This patch keeps the same settings
and runtime manager, but presents tasks, human names and one recommended setup
path instead of a raw dependency console.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from studio_band.runtime import RUNTIMES, detect_hardware
from studio_band_ui import BandAudioTab, _fit_toplevel, _scrollable_body


_COMPONENTS = {
    "separator": ("Core separation", "Demucs 6-stem + pitch evidence", "Core"),
    "piano": ("Piano transcription", "Transkun V2", "Core"),
    "beat": ("Beat detection", "Beat This", "Core"),
    "hq": ("HQ separation", "BS-RoFormer vocal split + six-stem evidence", "Recommended"),
    "drumsep": ("Drum kit evidence", "DrumSep / MDX23C kick-snare-hat-tom-cymbal evidence", "Quality"),
    "aria": ("Piano second opinion", "Aria-AMT on uncertain piano regions", "Quality"),
    "mt3": ("Musical repair", "MR-MT3 on uncertain regions", "Optional"),
    "global": ("Global music judge", "MuScriptor full-song evidence", "Optional"),
}


def _effective_device(tab, hardware) -> str:
    requested = tab.device.get()
    if requested == "cpu":
        return "cpu"
    return "cuda" if hardware.cuda else "cpu"


def _recommended_plan(tab, hardware) -> list[str]:
    """Build only what current settings can actually use."""
    device = _effective_device(tab, hardware)
    plan = [name for name in ("separator", "piano", "beat") if name in RUNTIMES]

    # HQ is the recommended NVIDIA path and explicit HQ on CPU is still valid,
    # albeit slower. Standard mode intentionally skips the large HQ runtime.
    if "hq" in RUNTIMES and (
        (device == "cuda" and tab.quality.get().lower() != "standard")
        or tab.quality.get().lower() == "hq"
    ):
        plan.append("hq")

    if tab.cross_check.get():
        if "mt3" in RUNTIMES and (device == "cuda" or tab.device.get() == "cpu"):
            plan.append("mt3")
        if device == "cuda":
            for name in ("drumsep", "aria"):
                if name in RUNTIMES:
                    plan.append(name)

    if device == "cuda" and tab.global_model.get() in {"medium", "large"} and "global" in RUNTIMES:
        plan.append("global")
    elif (
        device == "cuda" and tab.global_model.get() == "auto" and "global" in RUNTIMES
        and tab.pipeline.runtimes.muscriptor_model_access("medium")
    ):
        plan.append("global")

    # Preserve order while avoiding duplicates from future plan extensions.
    return list(dict.fromkeys(plan))


def _component_status(tab, key: str, hardware) -> str:
    if key == "aria" and not hardware.cuda:
        return "NVIDIA only"
    if tab.pipeline.runtimes.available(key):
        return "Ready"
    if key in {"separator", "piano", "beat", "hq"}:
        return "Needs setup"
    if key in {"drumsep", "aria"} and tab.cross_check.get():
        return "Needs setup"
    if key == "global" and tab.global_model.get() in {"medium", "large"}:
        return "Needs setup"
    if key == "mt3" and tab.cross_check.get():
        return "Needs setup"
    return "Optional"


def _advanced(self: BandAudioTab):
    window = tk.Toplevel(self.workspace)
    window.title("Audio → Band · Model setup")
    window.transient(self.workspace)
    _fit_toplevel(window, 820, 690, 560, 430)
    window._scroll_canvas, content, window._scrollbar = _scrollable_body(window, padding=14)

    hardware = detect_hardware()
    device = _effective_device(self, hardware)
    if hardware.cuda:
        hardware_text = f"Detected {hardware.gpu or 'NVIDIA GPU'} · {hardware.vram_gb:.1f} GB VRAM · Auto uses CUDA."
    else:
        hardware_text = "No usable NVIDIA CUDA GPU detected · Auto uses CPU."

    title = ttk.Label(content, text="Model setup", style="Title.TLabel")
    title.pack(anchor="w")
    intro = ttk.Label(
        content,
        text=(
            "For normal use you do not need to install every tool yourself. Leave Device on Auto, "
            "keep automatic setup enabled, then Analyze & Convert. Studio installs only the models "
            "needed by your selected quality settings."
        ),
        justify="left", wraplength=760,
    )
    intro.pack(anchor="w", fill="x", pady=(3, 8))
    ttk.Label(content, text=hardware_text, style="Hint.TLabel", wraplength=760).pack(anchor="w", pady=(0, 10))

    basics = ttk.LabelFrame(content, text="1 · Recommended settings", padding=10)
    basics.pack(fill="x", pady=(0, 10))
    basics.columnconfigure(1, weight=1)
    ttk.Label(basics, text="Processing device").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=3)
    ttk.Combobox(
        basics, textvariable=self.device, values=("auto", "cpu", "cuda"),
        state="readonly", width=12,
    ).grid(row=0, column=1, sticky="w", pady=3)
    ttk.Label(
        basics, text="Auto is recommended. CUDA means NVIDIA GPU acceleration.",
        style="Hint.TLabel",
    ).grid(row=1, column=1, sticky="w", pady=(0, 4))
    ttk.Checkbutton(
        basics,
        text="Automatically install missing models when I convert",
        variable=self.install,
    ).grid(row=2, column=0, columnspan=2, sticky="w", pady=3)
    ttk.Checkbutton(
        basics,
        text="Extra quality cross-check (slower: MR-MT3 + targeted DrumSep/Aria when usable)",
        variable=self.cross_check,
    ).grid(row=3, column=0, columnspan=2, sticky="w", pady=3)

    judge = ttk.Frame(basics)
    judge.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 0))
    ttk.Label(judge, text="Global music judge").pack(side="left")
    ttk.Combobox(
        judge, textvariable=self.global_model,
        values=("auto", "off", "medium", "large"), state="readonly", width=11,
    ).pack(side="left", padx=(10, 0))
    judge_note = ttk.Label(
        basics,
        text=(
            "MuScriptor Auto runs only when its weights are already accessible. Medium/Large may require "
            "authenticated Hugging Face access. Leaving Auto is safest."
        ),
        style="Hint.TLabel", justify="left", wraplength=720,
    )
    judge_note.grid(row=5, column=0, columnspan=2, sticky="w", pady=(3, 0))

    setup = ttk.LabelFrame(content, text="2 · One-click model setup", padding=10)
    setup.pack(fill="x", pady=(0, 10))
    plan = _recommended_plan(self, hardware)
    plan_names = [(_COMPONENTS.get(name, (name, "", ""))[0]) for name in plan]
    plan_text = "This will prepare: " + ", ".join(plan_names) + "."
    if not plan_names:
        plan_text = "No additional runtime is required by the current settings."
    plan_label = ttk.Label(setup, text=plan_text, justify="left", wraplength=720)
    plan_label.pack(anchor="w", fill="x")
    ttk.Label(
        setup,
        text="Downloads can be several GB. Progress appears at the bottom of the main Audio → Band window.",
        style="Hint.TLabel", justify="left", wraplength=720,
    ).pack(anchor="w", fill="x", pady=(3, 7))

    def setup_recommended():
        requested = self.device.get()
        fresh_hardware = detect_hardware()
        if requested == "cuda" and not fresh_hardware.cuda:
            messagebox.showerror(
                "CUDA is not available",
                "No usable NVIDIA CUDA device was detected. Choose Auto or CPU, then try again.",
                parent=window,
            )
            return
        names = _recommended_plan(self, fresh_hardware)
        effective = _effective_device(self, fresh_hardware)
        window.destroy()

        def work():
            total = max(1, len(names))
            for index, name in enumerate(names, 1):
                label = _COMPONENTS.get(name, (name, "", ""))[0]
                self.events.put(("progress", f"Setting up {label} ({index}/{total})…"))
                self.pipeline.runtimes.install(
                    name, device=effective, cancel=self.cancel,
                    progress=lambda value: self.events.put(("progress", value)),
                )
            self.events.put(("progress", "Recommended Audio → Band models are ready."))
            return None

        self.start(work, task="runtime setup")

    ttk.Button(
        setup, text="Set up recommended for this PC", command=setup_recommended,
    ).pack(anchor="w")

    components = ttk.LabelFrame(content, text="3 · Component status", padding=10)
    components.pack(fill="x", pady=(0, 10))
    tree = ttk.Treeview(
        components, columns=("status", "kind", "purpose"), show="tree headings",
        height=min(8, max(5, len(_COMPONENTS))), selectmode="browse",
    )
    tree.heading("#0", text="Component")
    tree.heading("status", text="Status")
    tree.heading("kind", text="Use")
    tree.heading("purpose", text="What it does")
    tree.column("#0", width=165, minwidth=125, stretch=False)
    tree.column("status", width=105, minwidth=90, stretch=False)
    tree.column("kind", width=92, minwidth=80, stretch=False)
    tree.column("purpose", width=390, minwidth=220, stretch=True)
    for key, (name, purpose, kind) in _COMPONENTS.items():
        if key not in RUNTIMES:
            continue
        tree.insert("", "end", iid=key, text=name,
                    values=(_component_status(self, key, hardware), kind, purpose))
    tree.pack(fill="x")

    drum_status = (
        "ADTOF is also installed." if self.pipeline.runtimes.available("drums")
        else "ADTOF is an optional manual add-on and is not required."
    )
    drum_note = ttk.Label(
        components,
        text=(
            "Drums are READY even without a runtime named ‘drums’: the built-in drum DSP always works, "
            "and DrumSep adds kit evidence when the quality cross-check is enabled. " + drum_status
        ),
        justify="left", wraplength=720,
    )
    drum_note.pack(anchor="w", fill="x", pady=(7, 0))

    repair_box = ttk.Frame(components)
    repair_box.pack(fill="x", pady=(8, 0))
    available_keys = [key for key in _COMPONENTS if key in RUNTIMES]
    display_to_key = {
        f"{_COMPONENTS[key][0]}  [{key}]": key for key in available_keys
    }
    default_key = next(
        (key for key in ("hq", "separator", "piano", "beat")
         if key in available_keys and not self.pipeline.runtimes.available(key)),
        available_keys[0] if available_keys else "",
    )
    selected = tk.StringVar(
        window,
        value=(f"{_COMPONENTS[default_key][0]}  [{default_key}]" if default_key else ""),
    )
    repair_combo = ttk.Combobox(
        repair_box, textvariable=selected, values=tuple(display_to_key),
        state="readonly", width=36,
    )
    repair_combo.pack(side="left")

    def repair_selected():
        key = display_to_key.get(selected.get())
        if not key:
            return
        requested = self.device.get()
        fresh_hardware = detect_hardware()
        if requested == "cuda" and not fresh_hardware.cuda:
            messagebox.showerror(
                "CUDA is not available",
                "No usable NVIDIA CUDA device was detected. Choose Auto or CPU, then try again.",
                parent=window,
            )
            return
        effective = _effective_device(self, fresh_hardware)
        if key == "aria" and effective != "cuda":
            messagebox.showinfo(
                "Aria-AMT needs NVIDIA CUDA",
                "Aria-AMT is only used as a targeted NVIDIA/CUDA piano reviewer. The normal Transkun piano path is already available without it.",
                parent=window,
            )
            return
        label = _COMPONENTS[key][0]
        window.destroy()
        self.start(
            lambda: self.pipeline.runtimes.install(
                key, device=effective, repair=True, cancel=self.cancel,
                progress=lambda value: self.events.put(("progress", value)),
            ),
            task=f"{label} setup",
        )

    ttk.Button(repair_box, text="Install / repair selected", command=repair_selected).pack(side="left", padx=(7, 0))

    playability = ttk.LabelFrame(content, text="4 · BPSR playability limits", padding=10)
    playability.pack(fill="x", pady=(0, 8))
    ttk.Label(
        playability,
        text="These categories affect the exported BPSR arrangement, not model installation.",
        style="Hint.TLabel",
    ).pack(anchor="w", pady=(0, 5))
    for part in self.tiers:
        row = ttk.Frame(playability)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=part.title() + " category", width=20).pack(side="left")
        values = (
            ("tier1", "tier2", "tier3", "tier4") if part == "piano" else
            ("tier1", "tier2", "tier3") if part == "guitar" else
            ("tier1", "tier2")
        )
        ttk.Combobox(
            row, textvariable=self.tiers[part], values=values,
            state="readonly", width=10,
        ).pack(side="left")

    ttk.Button(content, text="Drum mapping…", command=self.edit_drums).pack(anchor="w", pady=(0, 4))
    footer = ttk.Label(
        content,
        text=(
            "Suggested normal setup: Device Auto · Stem Quality Auto · automatic setup ON · extra quality cross-check OFF. "
            "Turn the cross-check on only when you want slower maximum-quality analysis."
        ),
        style="Hint.TLabel", justify="left", wraplength=760,
    )
    footer.pack(anchor="w", fill="x", pady=(4, 0))

    def reflow(event):
        width = max(280, event.width - 34)
        intro.configure(wraplength=width)
        judge_note.configure(wraplength=width)
        plan_label.configure(wraplength=width)
        drum_note.configure(wraplength=width)
        footer.configure(wraplength=width)

    content.bind("<Configure>", reflow, add="+")


def install_advanced_model_setup() -> None:
    if getattr(BandAudioTab, "_clear_advanced_model_setup", False):
        return
    BandAudioTab.advanced = _advanced
    BandAudioTab._clear_advanced_model_setup = True
